'use strict';
/* Hard-example mining. The policy flies fresh dispersed seeds; on every seed where it failed (or, without
   --fails-only, nearly failed: pad offset > 15 m, sideways speed > 0.4 m/s or touchdown faster than
   2.2 m/s) the teacher labels the states the policy actually reached (every step), and also flies the
   seed itself without injected noise. Both are copied `copies` times into the training data, so the
   next fine-tune sees the rare cases often enough to learn them.

   node scripts/flight_policy/mine.js <tag> <firstSeed> <count> [--copies 5] [--fails-only] [--policy file]
*/
const fs = require('fs');
const os = require('os');
const path = require('path');
const { runSeeds, report } = require('./parallel');
const { ROOT, POLICY_FILE } = require('./sim');

const argv = process.argv.slice(2), opt = (n, d) => { const i = argv.indexOf('--' + n); return i >= 0 ? argv[i + 1] : d; };
const [tag, first, count] = argv;
if (!/^[a-z][a-z0-9]*$/i.test(tag || '') || !(+count > 0)) {
  console.error('Usage: node mine.js <tag> <firstSeed> <count> [--copies 5] [--fails-only] [--policy file]');
  process.exit(1);
}
const policyFile = path.resolve(opt('policy', POLICY_FILE)), copies = +opt('copies', 5), failsOnly = argv.includes('--fails-only');
const DATA = path.join(ROOT, 'data', 'flight-policy', 'datasets'), WORK = path.join(os.tmpdir(), 'mine-' + process.pid);
const complete = r => r.success && r.orbit && r.deploy && r.fairing;

(async () => {
  const seeds = Array.from({ length: +count }, (_, i) => +first + i);
  const rows = await runSeeds(WORK, 'scan', seeds, { fly: 'policy', policyFile });
  report(`${tag} scan`, rows);
  const hard = rows.filter(r => !complete(r) || (!failsOnly && (r.err > 15 || r.vH > 0.4 || r.vV < -2.2))).map(r => r.seed);
  console.log(`${hard.length} hard seeds`);
  if (!hard.length) return;
  report(`${tag} policy-flown`, await runSeeds(WORK, tag + 'pol', hard, { fly: 'policy', record: true, policyFile, labelEvery: 1 }));
  report(`${tag} teacher-flown`, await runSeeds(WORK, tag + 'tea', hard, { fly: 'teacher', record: true, noise: 0 }));
  fs.mkdirSync(DATA, { recursive: true });
  for (const f of fs.readdirSync(WORK).filter(f => f.endsWith('.f32') && !f.startsWith('scan')))
    for (let k = 0; k < copies; k++) fs.copyFileSync(path.join(WORK, f), path.join(DATA, f.replace(/^([a-z0-9]+)/i, `$1x${k}`)));
  fs.rmSync(WORK, { recursive: true, force: true });
  console.log(`added ${hard.length} seeds x ${copies} to ${DATA}`);
})().catch(e => { console.error(e); process.exit(1); });
