'use strict';
/* Compare a candidate with the incumbent before replacing shipped weights.
   These fixed development seeds are separate from the held-out evaluation. */
const path = require('path');
const fs = require('fs');
const { runSeeds, report } = require('./parallel');
const { ROOT, POLICY_FILE } = require('./sim');

const complete = r => r.success && r.orbit && r.deploy && r.fairing;
function score(rows) {
  if (!rows.length) throw new Error('Cannot qualify an empty flight sample');
  const nominal = rows.find(r => r.seed === 0);
  const dispersed = rows.filter(r => r.seed !== 0);
  if (!nominal || !dispersed.length) throw new Error('Qualification requires nominal and dispersed flights');
  return {
    nominal: !!(complete(nominal) && nominal.vV > -2.1 && nominal.vV < 0 && nominal.vH < 0.5 && nominal.err <= 5 && nominal.tilt < 5),
    successes: dispersed.filter(complete).length,
    orbits: dispersed.filter(r => r.orbit).length,
    mean_offset: dispersed.reduce((sum, r) => sum + (Number.isFinite(r.err) ? r.err : 1e6), 0) / dispersed.length,
    worst_offset: Math.max(...dispersed.map(r => Number.isFinite(r.err) ? r.err : 1e6)),
    worst_speed: Math.max(...dispersed.map(r => Number.isFinite(r.vV) ? Math.abs(r.vV) : 1e6))
  };
}
function improves(candidate, incumbent) {
  /* bootstrap (training from scratch): until the incumbent flies the nominal mission, ship any
     candidate that is further along: full missions, then orbits, then landing offset */
  if (!incumbent.nominal) {
    return candidate.nominal || candidate.successes > incumbent.successes ||
      (candidate.successes === incumbent.successes && (candidate.orbits > incumbent.orbits ||
      (candidate.orbits === incumbent.orbits && candidate.mean_offset < incumbent.mean_offset)));
  }
  /* envelope floors block catastrophic misses (a crash, a landing off the pad complex) without
     letting one soft near-miss veto a candidate that completes more missions */
  return candidate.nominal && candidate.worst_speed <= Math.max(5, incumbent.worst_speed) &&
    candidate.worst_offset <= Math.max(250, incumbent.worst_offset) &&
    (candidate.successes > incumbent.successes ||
    (candidate.successes === incumbent.successes && candidate.mean_offset < incumbent.mean_offset));
}

async function qualify(candidate, incumbent = POLICY_FILE, directory = path.join(ROOT, 'data/flight-policy/gate'), count = 256) {
  if (!Number.isInteger(count) || count < 1 || count > 100000) throw new Error('Development gate count must be from 1 to 100000');
  const seeds = [0, ...Array.from({ length: count }, (_, i) => 800000 + i)];
  const baseline = await runSeeds(directory, 'incumbent', seeds, { fly: 'policy', policyFile: incumbent }, 6);
  const trial = await runSeeds(directory, 'candidate', seeds, { fly: 'policy', policyFile: candidate }, 6);
  report('incumbent development gate', baseline); report('candidate development gate', trial);
  const before = score(baseline), after = score(trial);
  const result = { schema: 'rocket-lab.policy-gate/1', candidate, incumbent, seeds,
    scope: 'Matched development comparison, not held-out qualification',
    accepted: improves(after, before), before, after };
  fs.writeFileSync(path.join(directory, 'comparison.json'), JSON.stringify(result, null, 2) + '\n');
  return result;
}
module.exports = { qualify, score, improves };

if (require.main === module) {
  const candidate = process.argv[2];
  if (!candidate) { console.error('Usage: node qualify.js <candidate.js> [incumbent.js]'); process.exit(1); }
  qualify(path.resolve(candidate), process.argv[3] ? path.resolve(process.argv[3]) : POLICY_FILE)
    .then(result => console.log(JSON.stringify(result, null, 2)))
    .catch(error => { console.error(error); process.exitCode = 1; });
}
