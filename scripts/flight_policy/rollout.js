'use strict';
/* Episode runner shared by data generation (teacher demos, DAgger) and evaluation.

   Each control step (10 Hz) records the features the policy sees and the
   teacher's command for that exact state. A dataset row is:
     booster: valid, features[NB], dirENU[3], thr, engineIndex, sep, mode
     upper:   valid, features[NU], dirENU[3], thr, on, fair, deploy */
const fs = require('fs');
const { loadSim } = require('./sim');
const makeTeacher = require('./teacher');

const NB = 52, NU = 26, ROW = 1 + NB + 7 + 1 + NU + 7;
const MODES = ['ASC', 'COAST1', 'BB', 'COAST2', 'ENTRY', 'AERO', 'LAND'];

function rng(seed) {
  let a = seed >>> 0;
  return () => { a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
/* Seeded run-to-run dispersions; seed 0 is the nominal replay. */
function dispersion(seed, scale) {
  if (!seed) return {};
  const r = rng(seed * 7919 + 17), u = (a, b) => a + (b - a) * r(), k = scale == null ? 1 : scale;
  return { wind: u(0, 1.0), windRot: u(-Math.PI, Math.PI), thrust: 1 + k * u(-0.01, 0.01), mvac: 1 + k * u(-0.01, 0.01),
    drag: 1 + k * u(-0.05, 0.05), s1Dry: k * u(-300, 300), sat: k * u(-1000, 1000) };
}

function enu(FS, r, d) { const L = FS._.localBasis(r), dot = FS._.dot; return [dot(d, L.E), dot(d, L.N), dot(d, L.U)]; }

/* Fly one episode. `fly` chooses who acts: 'teacher', 'policy', or 'mix' (policy acts,
   teacher labels). `noise` perturbs executed teacher commands (DART demonstrations). */
function episode(FS, opts) {
  const teacher = makeTeacher(FS, { cache: opts.fly === 'teacher', bp: opts.bp });
  const policy = opts.fly !== 'teacher' ? FS.neuralController(opts.policy) : null;
  const r = rng((opts.seed || 0) * 104729 + 7), rows = opts.record ? [] : null;
  const noise = opts.noise || 0, D2R = Math.PI / 180;
  let nE = 0, nN = 0, thrN = 0;
  const _ = FS._;
  const EXPENSIVE = { COAST1: 1, BB: 1, COAST2: 1, ENTRY: 1, AERO: 1 };
  let step = 0;
  const controller = ctx => {
    /* look-ahead labels are costly: on policy-flown episodes label them every `labelEvery` steps */
    const md = teacher.mode(ctx.B), want = !!rows && (!policy || !EXPENSIVE[md] || ctx.B.landed || step % (opts.labelEvery || 1) === 0);
    step++;
    const labels = want || !policy ? teacher(ctx) : null;
    if (want) {
      const B = ctx.B, U = ctx.U, row = new Float32Array(ROW);
      let o = 0;
      const bValid = !B.landed;
      row[o++] = bValid ? 1 : 0;
      FS.boosterFeatures(B, ctx.t).forEach(v => { row[o++] = v; });
      const lb = labels.booster, de = enu(FS, B.r, lb.dir);
      row[o++] = de[0]; row[o++] = de[1]; row[o++] = de[2]; row[o++] = lb.thr; row[o++] = FS.ENGINES.indexOf(lb.n); row[o++] = lb.sep ? 1 : 0;
      row[o++] = MODES.indexOf(teacher.mode(B));
      row[o++] = U.separated ? 1 : 0;
      FS.upperFeatures(U, ctx.t).forEach(v => { row[o++] = v; });
      const lu = labels.upper, du = enu(FS, U.r, lu.dir);
      row[o++] = du[0]; row[o++] = du[1]; row[o++] = du[2]; row[o++] = lu.thr; row[o++] = lu.on ? 1 : 0; row[o++] = lu.fair ? 1 : 0; row[o++] = lu.deploy ? 1 : 0;
      rows.push(row);
    }
    if (policy) return policy(ctx);
    if (noise > 0) {
      /* slowly varying pointing and throttle errors the teacher must correct (gentler on the stack) */
      const k = ctx.B.attached ? 0.3 * noise : noise;
      nE += (-nE * 0.05 + (r() - 0.5) * 0.6 * k); nN += (-nN * 0.05 + (r() - 0.5) * 0.6 * k); thrN += (-thrN * 0.1 + (r() - 0.5) * 0.04 * k);
      const B = ctx.B, L = _.localBasis(B.r), b = labels.booster, u = labels.upper;
      const off = _.add(_.sc(L.E, nE * D2R), _.sc(L.N, nN * D2R));
      /* discrete commands (ignition, cutoff, staging, jettison) execute after a random delay, so the
         demonstrations also show the teacher's command in states just past each switching point */
      const t = ctx.t, xb = Object.assign({}, b, { dir: _.unit(_.add(b.dir, off)), thr: _.clamp(b.thr + thrN, 0, 1) }), xu = Object.assign({}, u);
      xb.n = lag('n', b.n, t, ctx.B.ign === 2 ? 0.5 : 1.5); xb.sep = lag('sep', b.sep, t, 1.5);
      xu.on = lag('on', u.on, t, 1.0); xu.fair = lag('fair', u.fair, t, 3); xu.deploy = lag('deploy', u.deploy, t, 3);
      return { booster: xb, upper: xu };
    }
    return labels;
  };
  const held = {};
  function lag(key, want, t, maxDelay) {
    const h = held[key] || (held[key] = { v: want, due: null, to: want });
    if (want === h.v) { h.due = null; return h.v; }
    if (h.due === null || h.to !== want) { h.to = want; h.due = t + (r() < 0.5 ? 0 : r() * maxDelay); }
    if (t >= h.due) { h.v = want; h.due = null; }
    return h.v;
  }
  const stopWhen = (B, U, t) => B.landed && !U.hasSat && U.seco && t > U.tSeco + 62;
  const sim = FS.run({ controller, dispersion: opts.nominal ? {} : dispersion(opts.seed, opts.dispScale), quick: true, stopWhen });
  return { rows, summary: summarize(FS, sim) };
}

function summarize(FS, sim) {
  const L = sim.stats.landing, o = sim.stats.orbit, E = Object.fromEntries(sim.events.map(e => [e.name, e]));
  const orbitOk = !!o && (o.rp - FS.RE) > 150000 && o.ecc < 0.05;
  return {
    landed: !!L, success: !!(L && L.success), orbit: orbitOk,
    vV: L ? L.vV : null, vH: L ? L.vH : null, err: L ? L.err : null, tilt: L ? L.tilt : null, prop: L ? L.prop : null,
    perigee: o ? (o.rp - FS.RE) / 1000 : null, apogee: o ? (o.ra - FS.RE) / 1000 : null,
    fairing: !!E.FAIRING_SEP, deploy: !!E.SAT_DEPLOY, events: sim.events.map(e => e.name)
  };
}

/* worker entry: node rollout.js <job.json> */
if (require.main === module) {
  const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const FS = loadSim({ policy: false });
  const policy = job.policyFile ? require('./sim').loadPolicy(job.policyFile) : null;
  const out = job.out ? fs.openSync(job.out, 'w') : null, results = [];
  for (const seed of job.seeds) {
    const fly = job.fly === 'mix' ? (rng(seed * 31 + 3)() < (job.beta || 0) ? 'teacher' : 'policy') : job.fly;
    const res = episode(FS, { seed, fly, policy, record: !!out, noise: fly === 'teacher' ? (job.noise || 0) : 0, dispScale: job.dispScale, bp: job.bp, nominal: job.nominal, labelEvery: job.labelEvery });
    if (out) for (const row of res.rows) fs.writeSync(out, Buffer.from(row.buffer));
    results.push(Object.assign({ seed, fly }, res.summary));
  }
  if (out) fs.closeSync(out);
  fs.writeFileSync(job.result, JSON.stringify(results));
}

module.exports = { episode, dispersion, summarize, NB, NU, ROW, MODES };
