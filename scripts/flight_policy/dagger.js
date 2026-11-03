'use strict';
/* Training loop for the neural flight policy.

   1. Teacher demonstrations with small injected pointing/throttle errors (DART),
      over dispersed and nominal flights.
   2. Behaviour cloning (train.py).
   3. DAgger: the policy flies, the teacher labels the states the policy actually
      reaches, the data is aggregated and the policy retrained, until the policy
      alone completes the mission.

   node scripts/flight_policy/dagger.js [--demos 300] [--iters 6] [--per-iter 200] [--fresh]
*/
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');
const { runSeeds, report } = require('./parallel');
const { ROOT, POLICY_FILE } = require('./sim');
const { qualify } = require('./qualify');

const arg = (name, dflt) => { const i = process.argv.indexOf('--' + name); return i > 0 ? +process.argv[i + 1] : dflt; };
const DATA = path.join(ROOT, 'data', 'flight-policy', 'datasets');
const WORK = path.join(ROOT, 'data', 'flight-policy', 'work');
const PY = fs.existsSync(path.join(ROOT, '.venv', 'Scripts', 'python.exe')) ? path.join(ROOT, '.venv', 'Scripts', 'python.exe') : 'python';
const range = (a, n) => Array.from({ length: n }, (_, i) => a + i);

function moveData(tag) {
  fs.mkdirSync(DATA, { recursive: true });
  for (const f of fs.readdirSync(WORK)) if (f.startsWith(tag + '-') && f.endsWith('.f32')) fs.renameSync(path.join(WORK, f), path.join(DATA, f));
}
function train(extra) {
  const candidate = path.join(WORK, 'candidate.js'), checkpoint = path.join(WORK, 'candidate.pt');
  const resume = fs.existsSync(POLICY_FILE) ? ['--init-policy', POLICY_FILE] : [];
  const r = spawnSync(PY, [path.join(__dirname, 'train.py'), '--output', candidate, '--checkpoint', checkpoint, ...resume, ...extra.filter(x => x !== '--init')], { stdio: 'inherit', cwd: ROOT });
  if (r.status !== 0) throw new Error('training failed');
  return candidate;
}

async function trainAndGate(extra) {
  const candidate = train(extra);
  if (fs.existsSync(POLICY_FILE)) {
    const gate = await qualify(candidate);
    if (!gate.accepted) { console.log('Candidate did not improve the incumbent; shipped policy preserved.'); return; }
  }
  // Same-directory atomic replacement: the browser can never read half a model.
  const temporary = POLICY_FILE + '.tmp';
  fs.copyFileSync(candidate, temporary); fs.renameSync(temporary, POLICY_FILE);
}

(async () => {
  const fresh = process.argv.includes('--fresh');
  if (fresh && fs.existsSync(DATA)) fs.rmSync(DATA, { recursive: true });
  fs.mkdirSync(WORK, { recursive: true });
  const haveData = fs.existsSync(DATA) && fs.readdirSync(DATA).some(f => f.endsWith('.f32'));
  if (!haveData) {
    const n = arg('demos', 300);
    console.log(`teacher demonstrations: ${n} dispersed + ${Math.round(n / 6)} nominal`);
    report('teacher demos', await runSeeds(WORK, 'demo', range(10000, n), { fly: 'teacher', record: true, noise: 1 }));
    await runSeeds(WORK, 'demonom', range(20000, Math.round(n / 6)), { fly: 'teacher', record: true, noise: 1, nominal: true });
    await runSeeds(WORK, 'demoexact', [0], { fly: 'teacher', record: true, noise: 0, nominal: true }, 1);
    moveData('demo'); moveData('demonom'); moveData('demoexact');
    await trainAndGate(['--epochs', String(arg('epochs', 40)), '--tag', 'bc']);
  } else if (!fs.existsSync(POLICY_FILE)) await trainAndGate(['--epochs', String(arg('epochs', 40)), '--tag', 'bc']);

  const iters = arg('iters', 6), per = arg('per-iter', 200), start = arg('start', 1);
  for (let it = start; it < start + iters; it++) {
    const tag = `dagger${it}`;
    const seeds = range(30000 + it * 1000, per);
    const res = await runSeeds(WORK, tag, seeds, { fly: 'policy', record: true, policyFile: POLICY_FILE, labelEvery: 5 });
    const nom = await runSeeds(WORK, tag + 'nom', [0], { fly: 'policy', record: true, policyFile: POLICY_FILE, nominal: true, labelEvery: 1 }, 1);
    const ok = report(`iteration ${it} policy (dispersed)`, res);
    report(`iteration ${it} policy (nominal)`, nom);
    moveData(tag); moveData(tag + 'nom');
    fs.writeFileSync(path.join(ROOT, 'data', 'flight-policy', `progress-${it}.json`), JSON.stringify({ it, ok, n: per, nominal: nom[0] }, null, 1));
    await trainAndGate(['--epochs', String(arg('dagger-epochs', 25)), '--lr', '1e-3', '--tag', tag]);
  }
})().catch(e => { console.error(e); process.exit(1); });
