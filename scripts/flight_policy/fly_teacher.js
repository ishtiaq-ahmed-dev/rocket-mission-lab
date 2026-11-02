'use strict';
/* Fly the classical teacher alone (diagnostic). Usage: node fly_teacher.js [dispersionJSON] */
const { loadSim } = require('./sim');
const makeTeacher = require('./teacher');
const FS = loadSim({ policy: false });
const arg = process.argv.slice(2).find(a => a.startsWith('{')), disp = arg ? JSON.parse(arg) : {};
const t0 = Date.now();
const sim = FS.run({ controller: makeTeacher(FS, { cache: true, bp: process.env.BP ? JSON.parse(process.env.BP) : {} }), dispersion: disp, quick: process.argv.includes('--quick') });
console.log(sim.events.map(e => `${e.name}@${e.t.toFixed(1)}${e.alt != null ? '/' + (e.alt / 1000).toFixed(1) + 'km' : ''}`).join(' '));
console.log('landing', JSON.stringify(sim.stats.landing), 'apogee', (sim.stats.apogee / 1000).toFixed(1));
const o = sim.stats.orbit; if (o) console.log('orbit', ((o.rp - FS.RE) / 1000).toFixed(1), ((o.ra - FS.RE) / 1000).toFixed(1), o.inc.toFixed(2));
console.log('ms', Date.now() - t0);
