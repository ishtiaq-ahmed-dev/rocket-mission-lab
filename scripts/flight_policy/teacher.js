'use strict';
/* Classical teacher for the neural flight policy (training only, never shipped).

   Every command is a function of the vehicle's present state and its own event
   clocks, so the teacher can label any state the student reaches (DAgger).
   Expensive look-ahead (boostback targeting, entry/aero steering, landing-burn
   ignition) re-solves from the given state instead of carrying hidden plans.

   Physical choices, after Falcon 9 RTLS practice:
   - flip on cold-gas thrusters, then a three-engine boostback with horizontal
     thrust (it reverses the downrange velocity; it never pushes the booster
     toward the ground),
   - unpowered ballistic coast with the nose kept up for entry (engines leading),
   - three-engine entry burn against the airflow, unpowered grid-fin glide,
   - single-engine landing burn started at the last feasible moment. */
module.exports = function makeTeacher(FS, settings) {
  const { dot, nrm, add, sub, sc, unit, clamp, sstep, rotAbout, localBasis, lzBase, relVel, accel, boosterStep, boosterMass, upperMass, engineThrust, D2R } = FS._;
  const { V, RE, MU, G0, lzFrame, pressAt, orbitElems } = FS;
  const BP = Object.assign({
    tFlipAfterSep: 4.0, bbAfterMeco: 20.0, bbThr: 0.80, bbN: 3, bbPitch: 0, bbTol: 120,
    hEntry: 66000, entryThr: 0.80, entryN: 3, entryVend: 1000, entryMax: 40, entryKeep: 13000, entryReserve: 5200, entryTiltMax: 14 * D2R,
    aeroTiltMax: 16 * D2R, hAim: 1000, landTiltMax: 32 * D2R, vTd: 1.8,
    landThr: 0.85, landMargin: 15, aLat: 3, kLat: 0.35, fadeH: 200, aGate: 2.5, cnAlpha: 3.2, aoaBase: 0
  }, settings && settings.bp);
  const ASC = Object.assign({ ignT: -3.6, kick: 2.6 * D2R, tKick0: 8.0, kickDur: 5, gLim: 3.65, propMeco: 60000, sepDelay: 3.0 }, settings && settings.asc);
  const S2 = Object.assign({ ignDelay: 5.0, tFair: 200, deployDelay: 60, hTarget: 300000, hIns: 270000, hMin: 150000, gLim: 3.7, tgoMin: 40 },
    settings && settings.s2);
  const cache = settings && settings.cache ? {} : null;

  /* ---------------- booster mode from its own state ---------------- */
  function mode(S) {
    if (S.attached) return 'ASC';
    if (S.ign === 0) return 'COAST1';
    const burning = S.nEng > 0 && !S.cutting;
    if (S.ign === 1) return burning ? 'BB' : 'COAST2';
    if (S.ign === 2) return burning ? 'ENTRY' : 'AERO';
    return 'LAND';
  }
  /* aerodynamic acceleration on the booster at its present attitude (gravity removed) */
  function dragAcc(S) {
    const out = [0, 0, 0], m = boosterMass(S), rr = nrm(S.r);
    accel(S.r, S.v, 0, { m: m, axis: S.axis }, out);
    return add(out, sc(S.r, MU / (rr * rr * rr)));
  }
  const landProfile = (pU, vU) => Math.max(0, (vU * vU - BP.vTd * BP.vTd) / (2 * Math.max(pU, 0.3)));
  function steerVec(Bs, s) { return [Bs.E[0] * s[0] + Bs.N[0] * s[1], Bs.E[1] * s[0] + Bs.N[1] * s[1], Bs.E[2] * s[0] + Bs.N[2] * s[1]]; }
  function tilt(ret, d, ang) {
    const p = sub(d, sc(ret, dot(d, ret)));
    return nrm(p) > 1e-9 ? unit(add(sc(ret, Math.cos(ang)), sc(unit(p), Math.sin(ang)))) : ret;
  }
  function entryDir(S, s) {
    const vr = relVel(S.r, S.v), vh = nrm(vr) > 1 ? unit(vr) : unit(S.r);
    return tilt(sc(vh, -1), steerVec(localBasis(S.r), s), Math.min(1, Math.hypot(s[0], s[1])) * BP.entryTiltMax);
  }
  function aeroDir(S, t, s) {
    const Bs = localBasis(S.r), vr = relVel(S.r, S.v), vh = nrm(vr) > 1 ? unit(vr) : unit(S.r);
    /* baseline angle of attack: nose tilted away from the pad so the body lift points at it */
    const toL = sub(lzBase(t), S.r), tl = unit(sub(toL, sc(Bs.U, dot(toL, Bs.U))));
    let ex = s[0] - BP.aoaBase * dot(tl, Bs.E), ey = s[1] - BP.aoaBase * dot(tl, Bs.N);
    const em = Math.hypot(ex, ey); if (em > 1) { ex /= em; ey /= em; }
    return tilt(sc(vh, -1), steerVec(Bs, [ex, ey]), Math.min(1, em) * BP.aeroTiltMax);
  }
  /* coast attitude: engines leading, nose above the horizon (mirror the climb onto the descent) */
  function coastDir(S) {
    const Bs = localBasis(S.r), vr = relVel(S.r, S.v), vU = dot(vr, Bs.U), vH = sub(vr, sc(Bs.U, vU));
    return unit(sub(sc(Bs.U, Math.max(Math.abs(vU), 60)), vH));
  }
  /* boostback thrust: horizontal toward LZ-1 rotated by az, pitched bbPitch above the horizon */
  function bbDirFrom(S, t, az) {
    const Bs = localBasis(S.r), toL = sub(lzBase(t), S.r), h0 = unit(sub(toL, sc(Bs.U, dot(toL, Bs.U))));
    const hd = rotAbout(h0, Bs.U, az);
    return unit(add(sc(hd, Math.cos(BP.bbPitch)), sc(Bs.U, Math.sin(BP.bbPitch))));
  }
  function landCmd(S, t, predict) {
    const rr = nrm(S.r), h = rr - RE, L = lzFrame(t), d = sub(S.r, lzBase(t)), gv = relVel(S.r, S.v);
    const pE = dot(d, L.E), pN = dot(d, L.N), pU = dot(d, L.U), vE = dot(gv, L.E), vN = dot(gv, L.N), vU = dot(gv, L.U);
    const gl = MU / (rr * rr), m = boosterMass(S), q = 0.5 * FS.rhoAt(h) * dot(gv, gv);
    /* vertical: constant thrust that ends the descent at touchdown speed, drag included */
    const aT = Math.max(0.5, stopAccel(S, pU, -vU, L) + gl);
    /* lateral: approach the pad no faster than the side deceleration available near the
       ground can cancel (braking curve), then hold over it */
    const tRem = Math.max(0, 2 * (pU - 20) / (Math.abs(vU) + 3));
    const vcmd = p => -Math.sign(p) * Math.min(Math.sqrt(2 * BP.aLat * Math.abs(p)), BP.kLat * Math.abs(p), BP.aGate * tRem) * clamp(pU / BP.fadeH, 0, 1);
    const tauL = pU < 60 ? 1.0 : 1.8;
    const aE = (vcmd(pE) - vE) / tauL, aN = (vcmd(pN) - vN) / tauL;
    const aL = Math.hypot(aE, aN);
    /* Net side acceleration per radian of body tilt: the thrust component minus the
       aerodynamic normal force of an engine-first body. At high dynamic pressure the
       aero term wins and steering reverses, so the gain carries its sign. */
    const k = (m * aT - q * V.S * BP.cnAlpha) / m;
    const tl = (pU < 30 ? 5.0 : pU < 120 ? 5.0 + (pU - 30) / 90 * 11 : 16 + clamp((pU - 120) / 200, 0, 1) * (BP.landTiltMax / D2R - 16)) * D2R;
    let th = Math.abs(k) > 2 && aL > 1e-6 ? clamp(aL / Math.abs(k), 0, tl) : 0;
    const sgn = k >= 0 ? 1 : -1;
    const lat = aL > 1e-6 ? [(L.E[0] * aE + L.N[0] * aN) / aL, (L.E[1] * aE + L.N[1] * aN) / aL, (L.E[2] * aE + L.N[2] * aN) / aL] : [0, 0, 0];
    const dir = unit(add(sc(L.U, Math.cos(th)), sc(lat, sgn * Math.sin(th))));
    const cut = S.nEng === 0 || (pU < 6.0 && vU > -0.8);
    return { dir: dir, thr: clamp((m * aT / Math.cos(th) + V.merAe * pressAt(h)) / V.merTvac, V.merMin, 1), n: cut ? 0 : 1 };
  }
  /* Net upward deceleration (beyond gravity) a constant thrust must give so the descent ends at
     touchdown speed at the pad. Drag decel is taken as D0*(v/v0)^2, which gives the exact
     stopping distance d = ln((A + c v0^2)/(A + c vTd^2)) / (2c) with c = D0/v0^2. */
  function stopAccel(S, pU, v0, L) {
    const d = Math.max(pU, 0.3), vf = BP.vTd;
    if (v0 <= vf) return 0;
    const D0 = Math.max(0, dot(dragAcc(S), L.U)), c = D0 / (v0 * v0);
    if (c * d < 1e-6) return (v0 * v0 - vf * vf) / (2 * d);
    const E = Math.exp(Math.min(2 * c * d, 50));
    return Math.max(0, c * (v0 * v0 - E * vf * vf) / (E - 1));
  }

  /* Booster command law with explicit plan inputs (used directly and by the predictor). */
  function law(S, t, P) {
    const h = nrm(S.r) - RE;
    switch (mode(S)) {
      case 'COAST1': {
        if (t - S.tSep < BP.tFlipAfterSep || !P.bb) return { dir: S.axis, thr: 0, n: 0 };
        const late = t >= S.tMeco + BP.bbAfterMeco + 6, aligned = dot(S.axis, P.bb.dir) > Math.cos(10 * D2R);
        return { dir: P.bb.dir, thr: BP.bbThr, n: (t >= S.tMeco + BP.bbAfterMeco && aligned) || late ? BP.bbN : 0 };
      }
      case 'BB': return { dir: P.bb.dir, thr: BP.bbThr, n: t < P.bb.tEnd && S.prop > 9000 ? BP.bbN : 0 };
      case 'COAST2':
        if (h < BP.hEntry && dot(S.v, unit(S.r)) < 0) return { dir: entryDir(S, P.steerE || [0, 0]), thr: BP.entryThr, n: BP.entryN };
        return { dir: coastDir(S), thr: 0, n: 0 };
      case 'ENTRY': {
        /* ends once slow enough with only the landing budget left (spare propellant is spent here,
           where it buys entry margin, not at the bottom where one engine cannot throttle low enough) */
        const end = (nrm(relVel(S.r, S.v)) < BP.entryVend && S.prop <= BP.entryKeep) || t - S.tIgn > BP.entryMax || S.prop < BP.entryReserve;
        return { dir: entryDir(S, P.steerE || [0, 0]), thr: BP.entryThr, n: end ? 0 : BP.entryN };
      }
      case 'AERO':
        if (P.ignite) return Object.assign(landCmd(S, t, P.predict), { n: 1 });
        return { dir: aeroDir(S, t, P.steerA || [0, 0]), thr: 0, n: 0 };
      case 'LAND': return landCmd(S, t, P.predict);
    }
    return { dir: S.axis, thr: 0, n: 0 };
  }

  /* ---------------- forward prediction ---------------- */
  const cloneB = S => Object.assign({}, S, { r: S.r.slice(), v: S.v.slice(), axis: S.axis.slice() });
  /* fly the remaining return (burns, glide, landing burn) to touchdown; miss in LZ-1 east/north */
  function predictMiss(S0, t0, P, dtp) {
    const S = cloneB(S0);
    if (P.bbStart) { S.ign = 1; S.nEng = BP.bbN; S.thr = BP.bbThr; S.cutting = false; S.tIgn = t0; S.axis = P.bb.dir.slice(); }
    let t = t0, rp = S.r.slice(), pUp = Infinity, nextCheck = t0;
    const Pl = Object.assign({}, P, { predict: true });
    for (let guard = 0; guard < 6000; guard++) {
      const md = mode(S), h = nrm(S.r) - RE, L = lzFrame(t), pU = dot(sub(S.r, lzBase(t)), L.U);
      if (pU <= 0) {
        const f = pUp < Infinity ? clamp(pUp / Math.max(pUp - pU, 1e-9), 0, 1) : 1, rf = add(rp, sc(sub(S.r, rp), f));
        const d = sub(rf, lzBase(t)), gv = relVel(S.r, S.v);
        return { mE: dot(d, L.E), mN: dot(d, L.N), eE: dot(d, L.E), eN: dot(d, L.N), t: t, vU: dot(gv, L.U), landed: true };
      }
      if (md === 'LAND' && S.nEng === 0 && !S.cutting) break;
      Pl.ignite = false;
      if (md === 'AERO' && h < 12000 && t >= nextCheck) { Pl.ignite = landingIgnition(S, t); nextCheck = t + 0.5; }
      const dts = md === 'BB' || md === 'ENTRY' || md === 'LAND' || (md === 'AERO' && h < 12000) ? Math.min(dtp, 0.25) : h > 90000 ? dtp * 2 : dtp;
      rp = S.r.slice(); pUp = pU;
      boosterStep(S, law(S, t, Pl), t, dts, 0); t += dts;
    }
    const L = lzFrame(t), d = sub(S.r, lzBase(t));
    return { mE: dot(d, L.E), mN: dot(d, L.N), eE: dot(d, L.E), eN: dot(d, L.N), t: t, landed: false };
  }
  /* boostback: solve heading offset and remaining burn time that put the aim point over LZ-1 */
  function planBoostback(S, t) {
    const start = mode(S) === 'COAST1', m = boosterMass(S), T = BP.bbN * BP.bbThr * V.merTvac;
    const hv = relVel(S.r, S.v), Ub = unit(S.r), vhor = nrm(sub(hv, sc(Ub, dot(hv, Ub))));
    let az = 0, dur = clamp(start ? m * vhor * 0.9 / T : 10, 0, 70), last = null;
    const f = (a, du) => predictMiss(S, t, { bbStart: start, bb: { dir: bbDirFrom(S, t, a), tEnd: t + du } }, 1.0);
    for (let it = 0; it < 8; it++) {
      const m0 = f(az, dur); last = m0;
      if (Math.hypot(m0.mE, m0.mN) < BP.bbTol) break;
      const ea = 0.01, ed = 0.6, ma = f(az + ea, dur), md = f(az, dur + ed);
      const J = [[(ma.mE - m0.mE) / ea, (md.mE - m0.mE) / ed], [(ma.mN - m0.mN) / ea, (md.mN - m0.mN) / ed]];
      const det = J[0][0] * J[1][1] - J[0][1] * J[1][0];
      if (Math.abs(det) < 1e-6) break;
      const da = (J[1][1] * m0.mE - J[0][1] * m0.mN) / det, dd = (-J[1][0] * m0.mE + J[0][0] * m0.mN) / det;
      az -= clamp(da, -0.3, 0.3); dur = clamp(dur - clamp(dd, -8, 8), 0, 70);
    }
    return { dir: bbDirFrom(S, t, az), dur: dur, tEnd: t + dur, az: az, miss: last };
  }
  /* constant steering (entry: thrust tilt; aero: fin-trim) that zeroes the predicted landing error */
  function solveSteer(S, t, key) {
    let s = [0, 0];
    const P = v => key === 'E' ? { steerE: v, steerA: [0, 0] } : { steerA: v };
    for (let it = 0; it < 3; it++) {
      const m0 = predictMiss(S, t, P(s), 0.5);
      if (Math.hypot(m0.eE, m0.eN) < 3) break;
      const e = 0.25, m1 = predictMiss(S, t, P([s[0] + e, s[1]]), 0.5), m2 = predictMiss(S, t, P([s[0], s[1] + e]), 0.5);
      const J = [[(m1.eE - m0.eE) / e, (m2.eE - m0.eE) / e], [(m1.eN - m0.eN) / e, (m2.eN - m0.eN) / e]];
      const det = J[0][0] * J[1][1] - J[0][1] * J[1][0];
      if (Math.abs(det) < 50) break;
      const dE = (J[1][1] * m0.eE - J[0][1] * m0.eN) / det, dN = (-J[1][0] * m0.eE + J[0][0] * m0.eN) / det;
      s = [s[0] - 0.9 * dE, s[1] - 0.9 * dN];
      const mag = Math.hypot(s[0], s[1]); if (mag > 1) s = [s[0] / mag, s[1] / mag];
    }
    return s;
  }
  /* landing burn: light the engine at the last moment one engine at landThr can still stop at the
     pad. The stopping distance is integrated with drag growing as the air thickens on the way down
     (a constant-density estimate lights far too high after a fast entry burn). */
  function landingIgnition(S, t) {
    const h = nrm(S.r) - RE, L = lzFrame(t), gv = relVel(S.r, S.v), vU = dot(gv, L.U);
    if (h > 14000 || vU >= 0) return false;
    const pU = dot(sub(S.r, lzBase(t)), L.U) - BP.landMargin;
    const v0 = -vU, D0 = Math.max(0, dot(dragAcc(S), L.U)), rho0 = Math.max(FS.rhoAt(h), 1e-9), m = boosterMass(S);
    let v = v0, hh = h, d = 0;
    for (let i = 0; i < 2000 && v > BP.vTd; i++) {
      const dt = 0.05, g = MU / Math.pow(RE + hh, 2);
      const aT = BP.landThr * engineThrust(1, 1, V.merTvac, V.merAe, hh) / m;
      const aD = D0 * (FS.rhoAt(hh) / rho0) * (v * v) / (v0 * v0);
      v += (g - aT - aD) * dt; d += v * dt; hh -= v * dt;
      if (d >= pU) return true;
    }
    return d >= pU;
  }
  const cached = (key, t, period, fn) => {
    if (!cache) return fn();
    const c = cache[key];
    if (c && t - c.t < period && t >= c.t) return c.v;
    const v = fn(); cache[key] = { t, v }; return v;
  };

  /* ---------------- stack ascent ---------------- */
  function ascent(S, t, U) {
    const Ub = unit(S.r), vrel = relVel(S.r, S.v);
    if (S.tMeco > -1e8 || S.cutting) return { dir: unit(vrel), thr: 0, n: 0, sep: S.tMeco > -1e8 && t >= S.tMeco + ASC.sepDelay };
    if (t < ASC.ignT) return { dir: Ub, thr: 0, n: 0, sep: false };
    const h = nrm(S.r) - RE, mNow = boosterMass(S) + upperMass(U);
    let thr = t < 0 ? clamp((t - ASC.ignT) / 3.0, 0, 1) * 0.95 : 1 - 0.30 * Math.exp(-Math.pow((t - 66) / 14, 2));
    thr = Math.min(thr, ASC.gLim * G0 * mNow / (9 * V.merTvac) + V.merAe * pressAt(h) / V.merTvac);
    if (t >= 0) thr = Math.max(thr, V.merMin);
    let dir = Ub;
    if (t >= ASC.tKick0 + ASC.kickDur) dir = unit(vrel);
    else if (t >= ASC.tKick0) {
      const Bs = localBasis(S.r), hd = add(sc(Bs.E, Math.sin(V.azimuth)), sc(Bs.N, Math.cos(V.azimuth)));
      const kk = ASC.kick * sstep(0, 1, (t - ASC.tKick0) / ASC.kickDur);
      dir = unit(add(sc(Ub, Math.cos(kk)), sc(hd, Math.sin(kk))));
    }
    return { dir, thr, n: S.prop <= ASC.propMeco && t > 60 ? 0 : 9, sep: false };
  }

  /* ---------------- second stage ---------------- */
  function upperCmd(U, t) {
    const off = { dir: U.axis, thr: 0, on: false, fair: false, deploy: false };
    if (!U.separated) return off;
    const fair = U.hasFair && t >= S2.tFair;
    if (U.seco) return { dir: unit(U.v), thr: 0, on: false, fair, deploy: U.hasSat && t >= U.tSeco + S2.deployDelay };
    const thr = clamp(S2.gLim * G0 * upperMass(U) / V.mvacT, V.mvacMin, 1);
    if (!U.on) return { dir: unit(relVel(U.r, U.v)), thr, on: t - U.tSep >= S2.ignDelay, fair, deploy: false };
    /* closed-loop insertion: as horizontal speed builds toward circular, steer the vertical
       acceleration so altitude reaches hIns with zero climb rate (linear-tangent-like) */
    const rr = nrm(U.r), h = rr - RE, Ub = unit(U.r), vz = dot(U.v, Ub), vhv = sub(U.v, sc(Ub, vz)), vh = nrm(vhv);
    const aT = Math.max(U.T, 0.5 * V.mvacT * thr) / upperMass(U), g = MU / (rr * rr);
    /* time to go from the rocket equation (acceleration grows as propellant burns off), no shorter
       than the g-limited constant-acceleration time. The floor keeps the last seconds gentle: as
       tgo -> 0 the altitude term 6*dh/tgo^2 would whip the pitch to its limit. */
    const dv = Math.max(0, Math.sqrt(MU / (RE + S2.hIns)) - vh), ve = V.mvacT / V.mvacMdot;
    const tgo = clamp(Math.max(upperMass(U) / (V.mvacMdot * thr) * (1 - Math.exp(-dv / ve)), dv / (S2.gLim * G0)), S2.tgoMin, 600);
    const az = 6 * (S2.hIns - h) / (tgo * tgo) - 4 * vz / tgo;
    const pitch = Math.asin(clamp((az + g - vh * vh / rr) / aT, -0.2, 0.8));
    const Bs = localBasis(U.r), hdir = unit(vh > 80 ? vhv : add(sc(Bs.E, Math.sin(V.azimuth)), sc(Bs.N, Math.cos(V.azimuth))));
    const oe = orbitElems(U.r, U.v);
    const cut = (oe.a >= RE + S2.hTarget && h > S2.hMin) || U.prop <= 50;
    return { dir: unit(add(sc(hdir, Math.cos(pitch)), sc(Ub, Math.sin(pitch)))), thr, on: !cut, fair, deploy: false };
  }

  /* ---------------- teacher entry point ---------------- */
  function booster(ctx) {
    const S = ctx.B, t = ctx.t;
    if (S.landed) return { dir: S.axis, thr: 0, n: 0, sep: false };
    const md = mode(S);
    if (md === 'ASC') return ascent(S, t, ctx.U);
    let cmd;
    if (md === 'COAST1' || md === 'BB') {
      const plan = t - S.tSep < BP.tFlipAfterSep && md === 'COAST1' ? null : cached('bb', t, 0.5, () => planBoostback(S, t));
      cmd = law(S, t, { bb: plan });
      if (md === 'BB' && plan) cmd.n = plan.dur > 0.05 && S.prop > 9000 ? BP.bbN : 0;
    } else if (md === 'COAST2') {
      const h = nrm(S.r) - RE, go = h < BP.hEntry && dot(S.v, unit(S.r)) < 0;
      cmd = law(S, t, go ? { steerE: cached('sE', t, 0.5, () => solveSteer(S, t, 'E')) } : {});
    } else if (md === 'ENTRY') {
      cmd = law(S, t, { steerE: cached('sE', t, 0.5, () => solveSteer(S, t, 'E')) });
    } else if (md === 'AERO') {
      const steerA = cached('sA', t, nrm(S.r) - RE < 15000 ? 0.3 : 0.5, () => solveSteer(S, t, 'A'));
      cmd = law(S, t, { steerA: steerA, ignite: landingIgnition(S, t) });
    } else cmd = law(S, t, {});
    cmd.sep = false;
    return cmd;
  }
  function teacher(ctx) { return { booster: booster(ctx), upper: upperCmd(ctx.U, ctx.t) }; }
  teacher.mode = mode;
  teacher.BP = BP;
  teacher.planBoostback = planBoostback;
  teacher.solveSteer = solveSteer;
  teacher.predictMiss = predictMiss;
  return teacher;
};
