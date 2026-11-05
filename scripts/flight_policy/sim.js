'use strict';
/* Loads the flight model exactly as it ships: the simulator block embedded in
   frontend/index.html and, optionally, the trained policy weights. */
const fs = require('fs');
const path = require('path');
const { createHash } = require('crypto');

const ROOT = path.resolve(__dirname, '..', '..');
const POLICY_FILE = path.join(ROOT, 'frontend', 'public', 'flight-policy.js');

/* The simulator source (physics, actuators, policy runtime) without the renderer around it. */
function simSource() {
  const html = fs.readFileSync(path.join(ROOT, 'frontend', 'index.html'), 'utf8');
  const start = html.indexOf('(function (root) {');
  const endMarker = "})(typeof window !== 'undefined' ? window : globalThis);";
  const end = html.indexOf(endMarker, start);
  if (start < 0 || end < 0) throw new Error('flight model block not found in frontend/index.html');
  return html.slice(start, end + endMarker.length);
}

function loadSim(options) {
  const source = simSource();
  if (!options || options.policy !== false) loadPolicy();
  const mod = { exports: {} };
  new Function('module', 'exports', source)(mod, mod.exports);
  return mod.exports;
}

/* Identity of what decides the flight: evidence recorded against other hashes is stale. */
function flightHashes() {
  /* line endings are normalized so a CRLF checkout hashes the same as the LF source */
  const sha = text => createHash('sha256').update(String(text).replace(/\r\n/g, '\n')).digest('hex');
  return { simulator_sha256: sha(simSource()), policy_sha256: sha(fs.readFileSync(POLICY_FILE, 'utf8')) };
}

function loadPolicy(file) {
  const src = fs.readFileSync(file || POLICY_FILE, 'utf8');
  new Function(src)();
  return globalThis.FLIGHT_POLICY;
}

module.exports = { loadSim, loadPolicy, simSource, flightHashes, ROOT, POLICY_FILE };
