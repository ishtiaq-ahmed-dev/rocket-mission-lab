'use strict';
/* Regressions against the simulator and playback code that actually ship. */
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { loadSim, loadPolicy, ROOT } = require('./flight_policy/sim');
const { runSeeds } = require('./flight_policy/parallel');
const { score, improves } = require('./flight_policy/qualify');
const F = loadSim(), _ = F._;
const html = fs.readFileSync(path.join(ROOT, 'frontend/index.html'), 'utf8');

test('stage pushers conserve momentum and relative separation speed', () => {
  const B = _.newBooster(0), U = _.newUpper();
  B.prop = 40000;
  const mb = _.boosterMass(B), mu = _.upperMass(U), before = B.v.slice();
  _.separate(B, U, 0);
  for (let k = 0; k < 3; k++) assert.ok(Math.abs(mb * B.v[k] + mu * U.v[k] - (mb + mu) * before[k]) < 1e-6);
  assert.ok(Math.abs(_.nrm(_.sub(U.v, B.v)) - F.V.sepDv) < 1e-10);
});

test('new upper stage is not integrated a second time in its separation interval', () => {
  let checked = false;
  F.run({ tEnd: 10, quick: true,
    controller: ({ B, U, t }) => ({
      booster: { dir: B.axis, thr: 1, n: t >= 0 && t < 3 ? 9 : 0, sep: t >= 3 },
      upper: { dir: U.axis, thr: 0, on: false, fair: false, deploy: false }
    }),
    stopWhen: (B, U, t) => {
      if (!U.separated) return false;
      assert.ok(Math.abs(t - U.tSep) < 1e-10);
      assert.ok(Math.abs(_.nrm(_.sub(U.r, B.r)) - 39.2) < 1e-8);
      checked = true;
      return true;
    }
  });
  assert.ok(checked);
});

function impact(legs, sink = -10) {
  let initialized = false;
  return F.run({ tEnd: 0.04, quick: true,
    controller: ({ B, U, t }) => {
      if (t >= 0 && !initialized) {
        const L = F.lzFrame(t);
        B.r = _.add(_.lzBase(t), _.sc(L.U, 0.003));
        B.v = _.add([-F.OMEGA * B.r[1], F.OMEGA * B.r[0], 0], _.sc(L.U, sink));
        B.axis = L.U.slice(); B.attached = false; B.onPad = false; B.ign = 3; B.legs = legs;
        initialized = true;
      }
      return { booster: { dir: B.axis, thr: 0, n: 0, sep: false }, upper: { dir: U.axis, thr: 0, on: false } };
    }, stopWhen: B => B.landed
  });
}

test('impact reports contact-time velocity, then stores a stationary post-contact state', () => {
  const sim = impact(1), contact = sim.events.find(e => e.name === 'TOUCHDOWN');
  assert.ok(contact && contact.t > 0 && contact.t < 0.001);
  assert.ok(contact.vV < -10 && contact.vV > -10.01, contact.vV);
  assert.ok(_.nrm(_.relVel(sim.final.B.r, sim.final.B.v)) < 1e-10);
  assert.equal(sim.final.B.T, 0);
});

test('a soft contact without deployed legs is not a successful landing', () => {
  const sim = impact(0, -1);
  assert.ok(sim.stats.landing.vV > -3 && sim.stats.landing.tilt < 5 && sim.stats.landing.err < 43);
  assert.equal(sim.stats.landing.success, false);
  assert.ok(sim.final.B.legs < 0.99);
});

test('last partial fuel interval cannot produce a full interval of thrust', () => {
  const B = _.newBooster(0), L = F.siteFrame(0);
  B.r = _.sc(L.U, F.RE + 100000); B.v = [0, 0, 0];
  B.attached = B.onPad = false; B.prop = 0.01; B.nEng = 1; B.thr = 1;
  _.boosterStep(B, { n: 1, thr: 1, dir: L.U }, 0, F.DT, 0);
  assert.equal(B.prop, 0);
  assert.ok(Math.abs(B.T * F.DT - 0.01 * F.V.merTvac / F.V.merMdot) < 1e-8);
});

test('invalid neural weights fail before a flight can generate NaN telemetry', () => {
  const P = loadPolicy();
  for (const mutate of [
    p => { p.booster.layers[0].in--; },
    p => { p.booster.layers[0].W = ''; },
    p => { p.upper.layers.at(-1).out++; },
    p => { p.upper.activation = 'relu'; },
    p => { p.booster.std = Buffer.alloc(52 * 4).toString('base64'); }
  ]) {
    const bad = JSON.parse(JSON.stringify(P)); mutate(bad);
    assert.throws(() => F.neuralController(bad), /flight policy/);
  }
});

test('evaluation rejects empty, invalid and unsafe seed requests', async () => {
  for (const seeds of [[], [-1], [NaN], [0.5], [Number.MAX_SAFE_INTEGER + 1]]) {
    await assert.rejects(runSeeds(ROOT, 'invalid', seeds, { fly: 'policy' }), /seeds/);
  }
  await assert.rejects(runSeeds(ROOT, 'invalid', [0], { fly: 'unknown' }), /fly/);
  await assert.rejects(runSeeds(ROOT, 'invalid', [0], { fly: 'policy' }, -1), /workers/);
});

test('candidate gate rejects nominal regressions and lost missions', () => {
  const good = seed => ({seed, success:true, orbit:true, deploy:true, fairing:true, vV:-1.8, vH:0.1, tilt:1, err:1});
  const baseline = score([good(0),good(800000),good(800001)]);
  assert.equal(improves(score([good(0),good(800000),{...good(800001),success:false}]),baseline),false);
  assert.equal(improves(score([{...good(0),vV:-4},good(800000),good(800001)]),baseline),false);
  assert.equal(improves(score([good(0),{...good(800000),vV:-6},good(800001)]),baseline),false);
  assert.equal(improves(score([good(0),{...good(800000),err:300},good(800001)]),baseline),false);
  /* a weak incumbent (below 95 % of the development flights) gives way to a clearly better candidate */
  const weak = score([good(0),{...good(800000),success:false},{...good(800001),success:false}]);
  assert.equal(improves(score([{...good(0),vV:-4},good(800000),{...good(800001),success:false}]),weak),true);
  assert.equal(improves(score([good(0),{...good(800000),err:0.2},good(800001)]),baseline),true);
  assert.throws(()=>score([]),/empty/);
  assert.throws(()=>score([good(0)]),/nominal and dispersed/);
});

test('fairing and payload start at their release locations, without a birth-step jump', () => {
  let fairChecked=false,payloadChecked=false;
  // Inspect the sampled first active frame in a full trajectory. Releases are
  // deliberately aligned to the 25 Hz output period.
  const sim=F.run({tEnd:10,controller:({B,U,t})=>({
    booster:{dir:B.axis,thr:1,n:t>=0&&t<3?9:0,sep:t>=3},
    upper:{dir:U.axis,thr:1,on:U.separated&&t<5,fair:t>=4.02,deploy:t>=6.02}
  })});
  for(const [track,offset] of [[sim.FA,11.6],[sim.SAT,12.4]]){
    const i=Array.from({length:track.n},(_,i)=>i).find(i=>track.d[i*track.K+7]===1);
    assert.ok(i!==undefined);
    const o=i*track.K,u=i*sim.S2.K;
    const distance=Math.hypot(...[0,1,2].map(k=>track.d[o+k]-sim.S2.d[u+k]));
    assert.ok(Math.abs(distance-offset)<1e-7,`${distance} vs ${offset}`);
    assert.ok(Math.abs(track.d[o+8])<1e-8);
    if(track===sim.FA)fairChecked=true;else payloadChecked=true;
  }
  assert.ok(fairChecked&&payloadChecked);
});

test('visible replay time follows wall time through slow frames; hidden tabs pause', () => {
  const start = html.indexOf('function frame(now){'), end = html.indexOf('window.__sim=', start);
  const listeners = {}, context = {
    requestAnimationFrame() {}, performance: { now: () => 11000 },
    document: { hidden: false, addEventListener: (name, fn) => { listeners[name] = fn; } },
    window: {}, lastNow: 1000, frameCount: 0, emaDt: 1 / 60, pr: 1, PR_MAX: 1,
    realT: 0, playing: true, scrubbing: false, speed: 2, simT: 0, T_END: 660,
    drawFrame() {}, setPlaying(p) { context.playing = p; }
  };
  vm.createContext(context);
  vm.runInContext(html.slice(start, end), context);
  context.frame(1250);
  assert.equal(context.simT, 0.5); // Old 100 ms clamp gave 0.2 s.
  context.document.hidden = true; context.frame(9000);
  assert.equal(context.simT, 0.5);
  listeners.visibilitychange(); context.document.hidden = false; context.frame(11050);
  assert.ok(Math.abs(context.simT - 0.6) < 1e-12);
  context.scrubbing = true; context.frame(11100);
  assert.ok(Math.abs(context.simT - 0.6) < 1e-12);
});

test('camera/focus shortcuts work after clicking buttons without double-activating Space', () => {
  const start=html.indexOf("window.addEventListener('keydown',e=>{"),end=html.indexOf("window.addEventListener('resize'",start);
  let listener,focus=0,played=0;
  const context={window:{addEventListener:(_name,fn)=>{listener=fn;}},
    $:()=>({classList:{contains:()=>false}}),focusMode:0,
    setFocus:()=>focus++,setPlaying:()=>played++,playing:false,simT:0,T_END:660};
  vm.createContext(context);vm.runInContext(html.slice(start,end),context);
  const button={matches:selector=>selector==='button',isContentEditable:false};
  listener({target:button,key:'f',code:'KeyF'});
  assert.equal(focus,1);
  listener({target:button,key:' ',code:'Space'});
  assert.equal(played,0);
  listener({target:{matches:()=>false},key:' ',code:'Space',preventDefault(){}});
  assert.equal(played,1);
});

test('camera controls retain names and selection when compact labels are hidden', () => {
  const markup = [...html.matchAll(/<button data-cam="(\d)"([^>]*)>/g)];
  assert.equal(markup.length, 7);
  for (const [, number, attributes] of markup) {
    assert.match(attributes, /aria-label="[^"]*[A-Za-z][^"]*"/);
    assert.match(attributes, /title="[^"]+"/);
  }
  const buttons = markup.map(([, number]) => ({
    dataset: {cam: number}, attributes: {},
    classList: {toggle() {}}, setAttribute(name, value) {this.attributes[name] = String(value);}
  }));
  const context = {document: {querySelectorAll: () => buttons}, camMode: 1, camSnap: false,
    labEl: {}, obEl: {style: {}}, CAMS: {1:'Orbit', 4:'Booster Top Cam'}, orb: {}, defaultDist: () => 100};
  vm.createContext(context);
  vm.runInContext(html.slice(html.indexOf('function setCam(n){'), html.indexOf('function setFocus(m){')), context);
  context.setCam(4);
  assert.deepEqual(buttons.map(b => b.attributes['aria-pressed']), ['false','false','false','true','false','false','false']);
  context.setCam(1);
  assert.equal(buttons[0].attributes['aria-pressed'], 'true');
  assert.equal(buttons[3].attributes['aria-pressed'], 'false');
});

test('the teacher recovers from an engine cutoff or a wrong engine count in the landing burn', () => {
  /* the teacher once labelled an engine-off landing burn "stay off" and kept thrusting while rising, which
     taught the network to fall, or to climb away after a brief three-engine pulse near the ground */
  for (const [hAt, n, dur] of [[1500, 0, 1], [140, 3, 0.8]]) {
    const T = require('./flight_policy/teacher')(F, { cache: true });
    let until = -Infinity, relit = false;
    const sim = F.run({ quick: true, stopWhen: B => B.landed, controller: ctx => {
      const c = T(ctx), B = ctx.B, h = _.nrm(B.r) - F.RE - F.V.baseAboveFoot;
      if (until < 0 && B.ign === 3 && B.nEng > 0 && h < hAt) until = ctx.t + dur;
      if (ctx.t < until) c.booster.n = n;
      relit = relit || B.ign === 4;
      return c;
    } });
    assert.ok(relit && sim.stats.landing.success, `${n} engines at ${hAt} m: ${JSON.stringify(sim.stats.landing)}`);
  }
});
