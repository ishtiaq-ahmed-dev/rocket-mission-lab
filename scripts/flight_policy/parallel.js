'use strict';
/* Runs rollout jobs across worker processes and collects their summaries. */
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

function runSeeds(dir, tag, seeds, job, workers) {
  fs.mkdirSync(dir, { recursive: true });
  const n = Math.max(1, Math.min(workers || Math.max(1, os.cpus().length - 2), seeds.length));
  const parts = Array.from({ length: n }, () => []);
  seeds.forEach((s, i) => parts[i % n].push(s));
  return Promise.all(parts.map((part, i) => new Promise((resolve, reject) => {
    const file = path.join(dir, `${tag}-${i}`);
    const spec = Object.assign({}, job, { seeds: part, result: file + '.json', out: job.record ? file + '.f32' : null });
    fs.writeFileSync(file + '.job.json', JSON.stringify(spec));
    const child = spawn(process.execPath, [path.join(__dirname, 'rollout.js'), file + '.job.json'], { stdio: ['ignore', 'inherit', 'inherit'] });
    child.on('exit', code => code === 0 ? resolve(JSON.parse(fs.readFileSync(file + '.json', 'utf8'))) : reject(new Error(`worker ${i} exited ${code}`)));
  }))).then(r => [].concat(...r).sort((a, b) => a.seed - b.seed));
}

function report(label, results) {
  const n = results.length, k = f => results.filter(f).length;
  const ok = k(r => r.success && r.orbit && r.deploy);
  const vals = results.filter(r => r.landed);
  const worst = (key, sign) => vals.length ? Math.max(...vals.map(r => sign * r[key])) : NaN;
  console.log(`${label}: full-mission success ${ok}/${n}  landing ${k(r => r.success)}/${n}  orbit ${k(r => r.orbit)}/${n}  deploy ${k(r => r.deploy)}/${n}` +
    `  worst |vV| ${worst('vV', -1).toFixed(2)} m/s  worst err ${worst('err', 1).toFixed(1)} m  worst tilt ${worst('tilt', 1).toFixed(2)} deg`);
  return ok;
}

module.exports = { runSeeds, report };

/* CLI: node parallel.js <fly: teacher|policy> <firstSeed> <count> [policyFile] */
if (require.main === module) {
  const [fly, first, count, policyFile] = process.argv.slice(2);
  const seeds = Array.from({ length: +count }, (_, i) => +first + i);
  const dir = path.join(require('./sim').ROOT, 'data', 'flight-policy', 'eval');
  runSeeds(dir, fly, seeds, { fly, bp: process.env.BP ? JSON.parse(process.env.BP) : undefined, policyFile: policyFile || (fly === 'policy' ? require('./sim').POLICY_FILE : null) })
    .then(res => {
      report(fly, res);
      res.filter(r => !(r.success && r.orbit && r.deploy)).slice(0, 12).forEach(r => console.log('  fail', JSON.stringify(r)));
    })
    .catch(e => { console.error(e); process.exit(1); });
}
