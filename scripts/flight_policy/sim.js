'use strict';
/* Loads the flight model exactly as it ships: the simulator block embedded in
   frontend/index.html and, optionally, the trained policy weights. */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const POLICY_FILE = path.join(ROOT, 'frontend', 'public', 'flight-policy.js');

function loadSim(options) {
  const html = fs.readFileSync(path.join(ROOT, 'frontend', 'index.html'), 'utf8');
  const start = html.indexOf('(function (root) {');
  const endMarker = "})(typeof window !== 'undefined' ? window : globalThis);";
  const end = html.indexOf(endMarker, start);
  if (start < 0 || end < 0) throw new Error('flight model block not found in frontend/index.html');
  if (!options || options.policy !== false) loadPolicy();
  const mod = { exports: {} };
  new Function('module', 'exports', html.slice(start, end + endMarker.length))(mod, mod.exports);
  return mod.exports;
}

function loadPolicy(file) {
  const src = fs.readFileSync(file || POLICY_FILE, 'utf8');
  new Function(src)();
  return globalThis.FLIGHT_POLICY;
}

module.exports = { loadSim, loadPolicy, ROOT, POLICY_FILE };
