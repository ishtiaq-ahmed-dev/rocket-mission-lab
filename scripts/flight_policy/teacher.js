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
    tFlipAfterSep: 6.0, bbAfterMeco: 20.0, bbThr: 0.80, bbN: 3, bbPitch: 0, bbApoRef: 120000, bbApoScale: 65000, bbPitchMax: 25 * D2R, bbTol: 120,
    hEntry: 66000, entryThr: 0.80, entryN: 3, entryVend: 1000, entryMax: 40, entryKeep: 13000, entryReserve: 5200, entryTiltMax: 14 * D2R,
    aeroTiltMax: 16 * D2R, landTiltMax: 20 * D2R, vTd: 1.4, hGate: 20, aEnd: 2.5, hLat: 150, kFade: 8, aLatMax: 5, tauHold: 2.0, kpHold: 0.2, landSteerMax: 20 * D2R,
    landThr: 0.85, landMargin: 15, cnAlpha: 3.2, aoaBase: 0
  }, settings && settings.bp);
  const ASC = Object.assign({ ignT: -3.6, kick: 2.2 * D2R, tKick0: 8.0, kickDur: 5, gLim: 3.65, propMeco: 60000, sepDelay: 3.0, bucketT: 48, bucketW: 10, bucketDepth: 0.35 }, settings && settings.asc);
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
    /* an engine that is out above the pad during the landing burn glides on its fins and relights at the
       ignition point; the teacher used to say "stay off" there, so one early cutoff became a crash */
    if (S.nEng === 0 && !S.cutting && nrm(S.r) - RE - V.baseAboveFoot > 6) return 'AERO';
    return 'LAND';
  }
  /* aerodynamic acceleration on the booster at its present attitude (gravity removed) */
  function dragAcc(S) {
    const out = [0, 0, 0], m = boosterMass(S), rr = nrm(S.r);
    accel(S.r, S.v, 0, { m: m, axis: S.axis }, out);
    return add(out, sc(S.r, MU / (rr * rr * rr)));
  }
  /* terminal gate: the hoverslam ends hGate above the pad at vGate; below it the booster decelerates
     gently (aEnd, just above what minimum throttle forces) to vTd at touchdown, which leaves a few
     seconds to trim the last sideways drift */
  const vGate = Math.sqrt(BP.vTd * BP.vTd + 2 * BP.aEnd * BP.hGate);
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
  /* boostback thrust: horizontal toward LZ-1 rotated by az. On a low trajectory (dispersed thrust,
     drag, wind) the booster has little time aloft and would need a very fast return; there the
     thrust is pitched above the horizon to loft the return arc, which costs far less propellant.
     It never points below the horizon. */
  function bbDirFrom(S, t, az) {
    const Bs = localBasis(S.r), toL = sub(lzBase(t), S.r), h0 = unit(sub(toL, sc(Bs.U, dot(toL, Bs.U))));
    const hd = rotAbout(h0, Bs.U, az), h = nrm(S.r) - RE, vU = dot(relVel(S.r, S.v), Bs.U);
    const apo = h + Math.max(vU, 0) * vU / (2 * MU / Math.pow(nrm(S.r), 2));
    const pitch = BP.bbPitch + clamp((BP.bbApoRef - apo) / BP.bbApoScale, 0, BP.bbPitchMax);
    return unit(add(sc(hd, Math.cos(pitch)), sc(Bs.U, Math.sin(pitch))));
  }
  function landCmd(S, t, P) {
    const rr = nrm(S.r), h = rr - RE, L = lzFrame(t), d = sub(S.r, lzBase(t)), gv = relVel(S.r, S.v);
    const pE = dot(d, L.E), pN = dot(d, L.N), pU = dot(d, L.U), vE = dot(gv, L.E), vN = dot(gv, L.N), vU = dot(gv, L.U);
    const gl = MU / (rr * rr), m = boosterMass(S), q = 0.5 * FS.rhoAt(h) * dot(gv, gv), sink = -vU;
    /* vertical: constant thrust to the gate (drag included), then the gentle terminal profile */
    let aT;
    if (pU > BP.hGate) aT = gl + Math.max(BP.aEnd, stopAccel(S, pU - BP.hGate, sink, L, vGate));
    else {
      const vRef = Math.sqrt(BP.vTd * BP.vTd + 2 * BP.aEnd * Math.max(pU, 0));
      aT = gl + BP.aEnd + (sink - vRef) / 0.6;
    }
    aT = Math.max(0.5, aT);
    const tl = (pU < 30 ? 4.0 : pU < 120 ? 4.0 + (pU - 30) / 90 * 12 : 16 + clamp((pU - 120) / 200, 0, 1) * (BP.landTiltMax / D2R - 16)) * D2R;
    let dir;
    if (pU > BP.hLat) {
      /* Above hLat: two leans, each constant in the pad's frame (upper and lower half of the burn), solved
         so the booster reaches hLat over the pad with no sideways speed (re-solved twice a second). While
         the air dominates a lean makes body lift that carries the booster sideways; once the engine
         dominates the same lean puts thrust into braking, so the booster accelerates toward the pad and
         then brakes without rocking from one side to the other. noDivert (glide and boostback
         predictions) flies the burn with no lean at all. */
      const SL = P && P.steerL && !P.noDivert ? P.steerL : null;
      const sv = SL ? (pU > SL.hMid ? SL.a : SL.b) : [0, 0], sm = Math.min(1, Math.hypot(sv[0], sv[1]));
      /* the lean fades out over the last 50 m above hLat, so the command meets the near-vertical hold law
         without a step (a step there taught the network a sharp edge that also upset its engine choice) */
      const th = Math.min(sm * BP.landSteerMax, tl) * clamp((pU - BP.hLat) / 50, 0, 1);
      dir = sm > 1e-6 ? unit(add(sc(L.U, Math.cos(th)), sc(unit(add(sc(L.E, sv[0]), sc(L.N, sv[1]))), Math.sin(th)))) : L.U;
    } else {
      /* Below hLat the booster comes down nearly vertical: sideways speed is nulled first and the pull
         toward the pad centre fades with height, because the last metres allow only a few degrees. */
      const kp = BP.kpHold * clamp((pU - BP.hGate) / (BP.hLat - BP.hGate), 0, 1);
      const aE = -(vE + kp * pE) / BP.tauHold, aN = -(vN + kp * pN) / BP.tauHold;
      const aL = Math.min(BP.aLatMax, Math.hypot(aE, aN));
      /* side acceleration per radian of tilt: thrust minus the aerodynamic normal force; near the
         crossover the tilt fades to zero instead of flipping sides */
      const k = (m * aT - q * V.S * BP.cnAlpha) / m;
      const thS = aL * k / Math.max(k * k, BP.kFade * BP.kFade);
      const th = clamp(Math.abs(thS), 0, tl), sgn = thS >= 0 ? 1 : -1;
      const lat = aL > 1e-6 ? unit(add(sc(L.E, aE), sc(L.N, aN))) : [0, 0, 0];
      dir = unit(add(sc(L.U, Math.cos(th)), sc(lat, sgn * Math.sin(th))));
    }
    const cosT = Math.max(dot(dir, L.U), 0.5);
    /* rising above the gate means the burn overshot: one engine cannot hover (minimum thrust exceeds the
       weight), so it cuts, falls and relights at the ignition point instead of climbing away; a shutdown
       above the gate runs to completion, so the relight comes from the ignition test, not a flicker */
    const cut = S.nEng === 0 || (pU < 6.0 && vU > -0.8) || (pU > BP.hGate && (vU > 0 || S.cutting));
    return { dir: dir, thr: clamp((m * aT / cosT + V.merAe * pressAt(h)) / V.merTvac, V.merMin, 1), n: cut ? 0 : 1 };
  }
  /* Net upward deceleration (beyond gravity) a constant thrust must give so the descent ends at
     speed vf at distance pU. Drag decel is taken as D0*(v/v0)^2, which gives the exact
     stopping distance d = ln((A + c v0^2)/(A + c vTd^2)) / (2c) with c = D0/v0^2. */
  function stopAccel(S, pU, v0, L, vf) {
    const d = Math.max(pU, 0.3);
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
        if (P.ignite) return Object.assign(landCmd(S, t, P), { n: 1 });
        return { dir: aeroDir(S, t, P.steerA || [0, 0]), thr: 0, n: 0 };
      case 'LAND': return landCmd(S, t, P);
    }
    return { dir: S.axis, thr: 0, n: 0 };
  }

  /* ---------------- forward prediction ---------------- */
  const cloneB = S => Object.assign({}, S, { r: S.r.slice(), v: S.v.slice(), axis: S.axis.slice() });
  /* fly the remaining return (burns, glide, landing burn) to touchdown; miss in LZ-1 east/north */
  function predictMiss(S0, t0, P, dtp) {
    const S = cloneB(S0);
    if (P.bbStart) { S.ign = 1; S.nEng = BP.bbN; S.thr = BP.bbThr; S.cutting = false; S.tIgn = t0; S.axis = P.bb.dir.slice(); }
    let t = t0, rp = S.r.slice(), tp = t0, pUp = Infinity, nextCheck = t0, gate = null;
    const Pl = Object.assign({}, P, { predict: true });
    for (let guard = 0; guard < 6000; guard++) {
      const md = mode(S), h = nrm(S.r) - RE, L = lzFrame(t), pU = dot(sub(S.r, lzBase(t)), L.U);
      if (pU <= 0) {
        /* touchdown point interpolated within the last step, compared with the pad AT THAT MOMENT: the
           pad moves ~400 m/s with the Earth's rotation, so using the pad at the end of the step put a
           step-size-dependent east-west error of up to ~100 m into every prediction */
        const f = pUp < Infinity ? clamp(pUp / Math.max(pUp - pU, 1e-9), 0, 1) : 1, rf = add(rp, sc(sub(S.r, rp), f));
        const tf = tp + f * (t - tp), Lf = lzFrame(tf), d = sub(rf, lzBase(tf)), gv = relVel(S.r, S.v);
        return { mE: dot(d, Lf.E), mN: dot(d, Lf.N), eE: dot(d, Lf.E), eN: dot(d, Lf.N), t: tf, vU: dot(gv, Lf.U), landed: true, gate };
      }
      if (!gate && md === 'LAND' && pU <= BP.hLat) { const gv = relVel(S.r, S.v), dd = sub(S.r, lzBase(t)); gate = { pE: dot(dd, L.E), pN: dot(dd, L.N), vE: dot(gv, L.E), vN: dot(gv, L.N) }; }
      if (md === 'LAND' && S.nEng === 0 && !S.cutting) break;
      Pl.ignite = false;
      if (md === 'AERO' && h < 12000 && t >= nextCheck) { Pl.ignite = landingIgnition(S, t); nextCheck = t + 0.5; }
      const dts = md === 'BB' || md === 'ENTRY' || md === 'LAND' || (md === 'AERO' && h < 12000) ? Math.min(dtp, 0.25) : h > 90000 ? dtp * 2 : dtp;
      rp = S.r.slice(); tp = t; pUp = pU;
      boosterStep(S, law(S, t, Pl), t, dts, 0); t += dts;
    }
    const L = lzFrame(t), d = sub(S.r, lzBase(t));
    return { mE: dot(d, L.E), mN: dot(d, L.N), eE: dot(d, L.E), eN: dot(d, L.N), t: t, landed: false };
  }
  /* boostback: solve heading offset and remaining burn time that put the aim point over LZ-1 */
  function planBoostback(S, t) {
    const start = mode(S) === 'COAST1', m = boosterMass(S), T = BP.bbN * BP.bbThr * V.merTvac;
    const hv = relVel(S.r, S.v), Ub = unit(S.r), vhor = nrm(sub(hv, sc(Ub, dot(hv, Ub))));
    let az = 0, dur = clamp(start ? m * vhor * 0.9 / T : 10, 0, 70), best = null;
    const f = (a, du) => predictMiss(S, t, { bbStart: start, bb: { dir: bbDirFrom(S, t, a), tEnd: t + du }, noDivert: true }, 1.0);
    for (let it = 0; it < 8; it++) {
      const m0 = f(az, dur), e = Math.hypot(m0.mE, m0.mN);
      /* keep the best plan actually predicted: near cutoff the heading has almost no lever, and the last
         untested Newton step once meant 4 s more burn 50 degrees off course (a 12 km miss) */
      if (!best || e < best.e) best = { e, az, dur, m: m0 };
      if (e < BP.bbTol) break;
      const ea = 0.01, ed = 0.6, ma = f(az + ea, dur), md = f(az, dur + ed);
      const J = [[(ma.mE - m0.mE) / ea, (md.mE - m0.mE) / ed], [(ma.mN - m0.mN) / ea, (md.mN - m0.mN) / ed]];
      const det = J[0][0] * J[1][1] - J[0][1] * J[1][0];
      if (Math.abs(det) < 1e-6) break;
      const da = (J[1][1] * m0.mE - J[0][1] * m0.mN) / det, dd = (-J[1][0] * m0.mE + J[0][0] * m0.mN) / det;
      az -= clamp(da, -0.3, 0.3); dur = clamp(dur - clamp(dd, -8, 8), 0, 70);
    }
    return { dir: bbDirFrom(S, t, best.az), dur: best.dur, tEnd: t + best.dur, az: best.az, miss: best.m };
  }
  /* constant steering that zeroes the predicted landing error: entry (thrust tilt) and glide (fin trim)
     aim for a landing burn flown with no lean, as Falcon 9's grid fins line the booster up; the landing
     burn then solves its own constant lean ('L') for what is left */
  /* landing burn: two leans (4 unknowns) that put the booster over the pad with no sideways speed at hLat */
  function solveLand(S, t) {
    const pU0 = dot(sub(S.r, lzBase(t)), lzFrame(t).U), hMid = BP.hLat + 0.5 * Math.max(pU0 - BP.hLat, 0);
    const P = x => ({ steerL: { a: [x[0], x[1]], b: [x[2], x[3]], hMid } });
    const resid = m => { const g = m.gate || { pE: m.eE, pN: m.eN, vE: 0, vN: 0 }; return [g.pE, g.pN, 4 * g.vE, 4 * g.vN]; };
    let x = [0, 0, 0, 0];
    for (let it = 0; it < 6; it++) {
      const r0 = resid(predictMiss(S, t, P(x), 0.5));
      if (Math.hypot(r0[0], r0[1]) < 1.5 && Math.hypot(r0[2], r0[3]) < 2) break;
      const e = 0.2, J = [[], [], [], []];
      for (let j = 0; j < 4; j++) {
        const xp = x.slice(); xp[j] += e;
        const rj = resid(predictMiss(S, t, P(xp), 0.5));
        for (let i = 0; i < 4; i++) J[i][j] = (rj[i] - r0[i]) / e;
      }
      /* damped least squares (stays well behaved when a lean has little lever left) */
      const A = [[], [], [], []], b = [0, 0, 0, 0], lam = 25;
      for (let i = 0; i < 4; i++) { for (let j = 0; j < 4; j++) { let sum = i === j ? lam : 0; for (let k = 0; k < 4; k++) sum += J[k][i] * J[k][j]; A[i][j] = sum; } for (let k = 0; k < 4; k++) b[i] += J[k][i] * r0[k]; }
      const dx = solve4(A, b);
      x = x.map((v, j) => v - clamp(dx[j], -0.5, 0.5));
      for (const o of [0, 2]) { const mag = Math.hypot(x[o], x[o + 1]); if (mag > 1) { x[o] /= mag; x[o + 1] /= mag; } }
    }
    return { a: [x[0], x[1]], b: [x[2], x[3]], hMid };
  }
  function solve4(A, b) {
    const M = A.map((row, i) => row.concat([b[i]]));
    for (let c = 0; c < 4; c++) {
      let piv = c; for (let r = c + 1; r < 4; r++) if (Math.abs(M[r][c]) > Math.abs(M[piv][c])) piv = r;
      [M[c], M[piv]] = [M[piv], M[c]];
      if (Math.abs(M[c][c]) < 1e-12) return [0, 0, 0, 0];
      for (let r = c + 1; r < 4; r++) { const f = M[r][c] / M[c][c]; for (let k = c; k < 5; k++) M[r][k] -= f * M[c][k]; }
    }
    const x = [0, 0, 0, 0];
    for (let r = 3; r >= 0; r--) { let sum = M[r][4]; for (let k = r + 1; k < 4; k++) sum -= M[r][k] * x[k]; x[r] = sum / M[r][r]; }
    return x;
  }
  function solveSteer(S, t, key) {
    let s = [0, 0];
    const P = v => key === 'E' ? { steerE: v, steerA: [0, 0], noDivert: true } : key === 'A' ? { steerA: v, noDivert: true } : { steerL: v };
    /* the landing lean keeps solving as its lever shrinks near hLat (small but real sensitivity), with
       bounded Newton steps; glide and entry keep their original settings */
    const land = key === 'L', iters = land ? 6 : 3, detMin = land ? 1 : 50, stepMax = land ? 0.5 : 1e9;
    for (let it = 0; it < iters; it++) {
      const m0 = predictMiss(S, t, P(s), 0.5);
      if (Math.hypot(m0.eE, m0.eN) < (land ? 1.5 : 3)) break;
      const e = 0.25, m1 = predictMiss(S, t, P([s[0] + e, s[1]]), 0.5), m2 = predictMiss(S, t, P([s[0], s[1] + e]), 0.5);
      const J = [[(m1.eE - m0.eE) / e, (m2.eE - m0.eE) / e], [(m1.eN - m0.eN) / e, (m2.eN - m0.eN) / e]];
      const det = J[0][0] * J[1][1] - J[0][1] * J[1][0];
      if (Math.abs(det) < detMin) break;
      const dE = clamp((J[1][1] * m0.eE - J[0][1] * m0.eN) / det, -stepMax, stepMax), dN = clamp((-J[1][0] * m0.eE + J[0][0] * m0.eN) / det, -stepMax, stepMax);
      s = [s[0] - 0.9 * dE, s[1] - 0.9 * dN];
      const mag = Math.hypot(s[0], s[1]); if (mag > 1) s = [s[0] / mag, s[1] / mag];
    }
    return s;
  }
  /* landing burn: light the engine at the last moment one engine at landThr can still reach the
     terminal gate. The stopping distance is integrated with drag growing as the air thickens on the way down
     (a constant-density estimate lights far too high after a fast entry burn). */
  function landingIgnition(S, t) {
    const h = nrm(S.r) - RE, L = lzFrame(t), gv = relVel(S.r, S.v), vU = dot(gv, L.U);
    if (h > 14000 || vU >= 0) return false;
    const hp = dot(sub(S.r, lzBase(t)), L.U), pU = hp - BP.landMargin - BP.hGate;
    const v0 = -vU, D0 = Math.max(0, dot(dragAcc(S), L.U)), rho0 = Math.max(FS.rhoAt(h), 1e-9), m = boosterMass(S);
    /* never light slower than the gentlest stopping profile (aEnd to the gate, then to touchdown): after a
       hop the booster falls until it is that fast, or the burn stalls into a hover that empties the tanks.
       A normal landing burn lights far faster than this (about 300 m/s against 130 m/s at 3.8 km). */
    if (v0 < Math.sqrt(hp > BP.hGate ? vGate * vGate + 2 * BP.aEnd * (hp - BP.hGate) : BP.vTd * BP.vTd + 2 * BP.aEnd * Math.max(hp, 0))) return false;
    let v = v0, hh = h, d = 0;
    for (let i = 0; i < 2000 && v > vGate; i++) {
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
    let thr = t < 0 ? clamp((t - ASC.ignT) / 3.0, 0, 1) * 0.95 : 1 - ASC.bucketDepth * Math.exp(-Math.pow((t - ASC.bucketT) / ASC.bucketW, 2));
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
      /* cut off at the planned end time: the plan is up to 0.5 s old, and at ~7 km of landing error per
         second of boostback its remaining duration must not be read as if it were fresh */
      if (md === 'BB' && plan) cmd.n = t < plan.tEnd && plan.dur > 0.05 && S.prop > 9000 ? BP.bbN : 0;
    } else if (md === 'COAST2') {
      const h = nrm(S.r) - RE, go = h < BP.hEntry && dot(S.v, unit(S.r)) < 0;
      cmd = law(S, t, go ? { steerE: cached('sE', t, 0.5, () => solveSteer(S, t, 'E')) } : {});
    } else if (md === 'ENTRY') {
      cmd = law(S, t, { steerE: cached('sE', t, 0.5, () => solveSteer(S, t, 'E')) });
    } else if (md === 'AERO') {
      const steerA = cached('sA', t, nrm(S.r) - RE < 15000 ? 0.3 : 0.5, () => solveSteer(S, t, 'A'));
      const ignite = landingIgnition(S, t);
      cmd = law(S, t, { steerA: steerA, ignite, steerL: ignite ? cached('sL', t, 0.5, () => solveLand(S, t)) : null });
    } else if (md === 'LAND') {
      cmd = law(S, t, { steerL: cached('sL', t, 0.5, () => solveLand(S, t)) });
    } else cmd = law(S, t, {});
    cmd.sep = false;
    return cmd;
  }
  function teacher(ctx) { return { booster: booster(ctx), upper: upperCmd(ctx.U, ctx.t) }; }
  teacher.mode = mode;
  teacher.BP = BP;
  teacher.planBoostback = planBoostback;
  teacher.solveSteer = solveSteer;
  teacher.solveLand = solveLand;
  teacher.predictMiss = predictMiss;
  teacher.law = law;
  return teacher;
};
