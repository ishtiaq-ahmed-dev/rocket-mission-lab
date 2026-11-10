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
    n: dispersed.length,
    successes: dispersed.filter(complete).length,
    orbits: dispersed.filter(r => r.orbit).length,
    /* catastrophic outcomes: a crash or a landing off the pad complex */
    catastrophes: dispersed.filter(r => !Number.isFinite(r.vV) || Math.abs(r.vV) > 5 || !Number.isFinite(r.err) || r.err > 250).length,
    mean_offset: dispersed.reduce((sum, r) => sum + (Number.isFinite(r.err) ? r.err : 1e6), 0) / dispersed.length,
    worst_offset: Math.max(...dispersed.map(r => Number.isFinite(r.err) ? r.err : 1e6)),
    worst_speed: Math.max(...dispersed.map(r => Number.isFinite(r.vV) ? Math.abs(r.vV) : 1e6))
  };
}
function improves(candidate, incumbent) {
  /* bootstrap (training from scratch or onto a new teacher): until the incumbent flies the nominal mission
     AND completes 95 % of the development flights, ship any candidate that is further along: full
     missions, then orbits, then landing offset. The shipped network is checked on the nominal flight
     separately, before release. */
  if (!incumbent.nominal || incumbent.successes < 0.95 * (incumbent.n || 1)) {
    return candidate.nominal || candidate.successes > incumbent.successes ||
      (candidate.successes === incumbent.successes && (candidate.orbits > incumbent.orbits ||
      (candidate.orbits === incumbent.orbits && candidate.mean_offset < incumbent.mean_offset)));
  }
  /* no more catastrophic outcomes (crashes above 5 m/s, landings beyond 250 m) than the incumbent,
     counted together, so one soft near-miss cannot veto a candidate that completes more missions */
  return candidate.nominal && candidate.catastrophes <= incumbent.catastrophes &&
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
