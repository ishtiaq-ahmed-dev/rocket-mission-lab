'use strict';
/* Held-out evaluation of the shipped policy against the teacher on the same dispersed seeds.
   node scripts/flight_policy/evaluate.js [firstSeed=900000] [count=300]
   Writes data/flight-policy-validation.json. */
const fs = require('fs');
const path = require('path');
const { runSeeds, report } = require('./parallel');
const { ROOT, POLICY_FILE, loadPolicy } = require('./sim');

(async () => {
  const first = +(process.argv[2] || 900000), count = +(process.argv[3] || 300);
  const seeds = Array.from({ length: count }, (_, i) => first + i), work = path.join(ROOT, 'data', 'flight-policy', 'eval');
  const policy = await runSeeds(work, 'policy', seeds, { fly: 'policy', policyFile: POLICY_FILE });
  const teacher = await runSeeds(work, 'teacher', seeds, { fly: 'teacher' });
  const nominal = (await runSeeds(work, 'nominal', [0], { fly: 'policy', policyFile: POLICY_FILE }, 1))[0];
  const summary = rs => {
    const landed = rs.filter(r => r.landed);
    return { flights: rs.length, full_mission: rs.filter(r => r.success && r.orbit && r.deploy).length, landing: rs.filter(r => r.success).length,
      orbit: rs.filter(r => r.orbit).length, worst_touchdown_m_s: Math.max(...landed.map(r => -r.vV)), worst_pad_offset_m: Math.max(...landed.map(r => r.err)) };
  };
  const out = {
    schema: 'rocket-lab.flight-policy-validation/1', policy_tag: loadPolicy().tag, seeds: [first, first + count - 1],
    success: 'orbit (perigee > 150 km, e < 0.05), payload deployed, touchdown vertical > -3 m/s, horizontal < 1.5 m/s, tilt < 5 deg, within 43 m of LZ-1',
    dispersions: 'wind 0-100% any direction, Merlin and MVac thrust +/-1%, drag +/-5%, booster dry mass +/-300 kg, payload +/-1000 kg',
    policy: summary(policy), teacher: summary(teacher), nominal, failures: policy.filter(r => !(r.success && r.orbit && r.deploy))
  };
  fs.writeFileSync(path.join(ROOT, 'data', 'flight-policy-validation.json'), JSON.stringify(out, null, 1) + '\n');
  report('policy', policy); report('teacher', teacher);
})().catch(e => { console.error(e); process.exit(1); });
