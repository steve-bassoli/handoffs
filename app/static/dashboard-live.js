(function () {
  'use strict';
  window.createDashboard = function (root, options) {
    const o = options || {}, doc = o.document || document;
    const fetcher = o.fetch || window.fetch.bind(window);
    const later = o.setTimeout || window.setTimeout.bind(window);
    const cancel = o.clearTimeout || window.clearTimeout.bind(window);
    const now = o.now || Date.now, renderers = {}, slots = {};
    const status = root.querySelector('[data-dashboard-status]');
    const pauseButton = root.querySelector('[data-dashboard-pause]');
    const resumeButton = root.querySelector('[data-dashboard-resume]');
    let snapshot = null, received = null, timer = null, busy = false;
    let paused = false, dead = false, authentication = false, failures = 0;
    let error = null, endpoint = null;
    const known = x => x === null || x === undefined ? 'unknown' : String(x);
    const yes = x => x === true ? 'yes' : x === false ? 'no' : 'unknown';
    function line(el, text) {
      const p = doc.createElement('p'); p.textContent = text; el.appendChild(p);
    }
    function live(el, s) {
      el.textContent = '';
      if (!s) { line(el, 'No observations received.'); return; }
      line(el, 'Snapshot observed: ' + known(s.observed_at));
      if (!s.agents.length) line(el, 'No agent evidence available.');
      s.agents.forEach(a => {
        line(el, known(a.id) + ' · Reported activity: ' + known(a.reported_activity));
        line(el, 'Explicit live confirmation: ' + yes(a.live_confirmed) +
          ' · Interrupted occupied lease: ' + yes(a.interrupted_occupied_lease));
        line(el, 'Operational PRESSURE: ' + known(a.pressure) +
          (a.pressure === 3 ? ' — STOP NOW' : a.pressure === 2 ? ' — reduce load / checkpoint' : ''));
      });
    }
    function flow(el, s) {
      el.textContent = '';
      line(el, s ? 'Selected session: ' + known(s.session.id) : 'No observations received.');
      if (s) line(el, 'Plan, board and summary availability are listed under Ops. Missing summary can be normal for an unfinished session.');
    }
    function ops(el, s) {
      el.textContent = '';
      if (!s) { line(el, 'No observations received.'); return; }
      line(el, 'Reported mode: ' + known(s.mode.value) + ' · Agent count: ' + known(s.mode.agents));
      line(el, 'Reported automated writes: ' + yes(s.mode.automated_writes));
      ['roster', 'mode', 'plan', 'board', 'summary'].forEach(k => {
        const source = s.sources[k];
        line(el, k + ': ' + known(source.status) + ' · Event time: ' + known(source.event_at));
      });
    }
    function paint() {
      if (dead) return;
      const view = {stale: snapshot === null || !!error || paused || authentication,
        paused: paused, authentication: authentication, error: error, received_at: received};
      if (status) status.textContent = (authentication ? 'Authentication stopped' :
        paused ? 'Paused' : !endpoint ? 'Not configured — no requests' :
        view.stale ? 'Stale / source unavailable' : 'Polling · last-good snapshot') +
        (received === null ? '' : ' · Local receipt: ' + new Date(received).toISOString()) +
        (error ? ' · ' + error : '');
      Object.keys(renderers).forEach(k => {
        if (slots[k]) { try { renderers[k](slots[k], snapshot, Object.assign({}, view)); }
          catch (_) { if (status) status.textContent = 'Renderer unavailable'; } }
      });
    }
    function schedule() {
      if (dead || paused || authentication || busy || !endpoint || timer !== null) return;
      const delay = Math.max(doc.hidden ? 10000 : 2500,
        failures ? Math.min(60000, 2500 * Math.pow(2, Math.min(failures, 5))) : 2500);
      timer = later(function () { timer = null; refresh(); }, delay);
    }
    function visibilityChanged() {
      if (timer !== null) cancel(timer);
      timer = null;
      schedule();
    }
    function valid(s) {
      const object = x => x !== null && typeof x === 'object' && !Array.isArray(x);
      const text = x => x === null || typeof x === 'string';
      const evidence = x => x === null || typeof x === 'boolean';
      if (!object(s) || s.schema_version !== 1 || typeof s.observed_at !== 'string' ||
          !s.observed_at.trim() || !Array.isArray(s.agents) || !object(s.sources) ||
          !object(s.mode) || !object(s.session)) return false;
      if (!text(s.mode.value) || !evidence(s.mode.automated_writes) ||
          !(s.mode.agents === null || (Number.isInteger(s.mode.agents) && s.mode.agents >= 0)) ||
          !text(s.session.id)) return false;
      const ids = new Set();
      if (!s.agents.every(a => {
        if (!object(a) || typeof a.id !== 'string' || !a.id.trim() || ids.has(a.id) ||
            !text(a.reported_activity) || !evidence(a.live_confirmed) ||
            !evidence(a.interrupted_occupied_lease) ||
            !(a.pressure === null || a.pressure === 1 || a.pressure === 2 || a.pressure === 3)) return false;
        ids.add(a.id); return true;
      })) return false;
      return ['roster', 'mode', 'plan', 'board', 'summary'].every(k => {
        const source = s.sources[k];
        return object(source) && text(source.event_at) &&
          ['available', 'missing', 'invalid', 'unavailable'].includes(source.status);
      });
    }
    async function refresh() {
      if (dead || paused || authentication || busy || !endpoint) return;
      busy = true;
      try {
        const response = await fetcher(endpoint, {headers: o.headers || {},
          credentials: 'same-origin', redirect: 'error', cache: 'no-store'});
        if (dead) return;
        if (response.status === 401 || response.status === 403) {
          authentication = true; throw new Error('authentication');
        }
        if (!response.ok || response.redirected) throw new Error('read');
        const value = await response.json();
        if (dead) return;
        if (!valid(value)) throw new Error('shape');
        snapshot = value; received = now(); failures = 0; error = null;
      } catch (_) {
        if (!dead) { failures += 1; error = authentication ? 'Authorized identity required' : 'Snapshot read failed'; }
      } finally { busy = false; if (!dead) { paint(); schedule(); } }
    }
    function pause() { paused = true; if (timer !== null) cancel(timer); timer = null; paint(); }
    function resume() {
      if (dead || authentication) return;
      paused = false; if (timer !== null) cancel(timer); timer = null; paint(); refresh();
    }
    function register(slot, renderer) {
      if (!Object.prototype.hasOwnProperty.call(slots, slot) || typeof renderer !== 'function') throw new Error('Invalid renderer');
      renderers[slot] = renderer; paint();
    }
    ['live', 'flow', 'ops'].forEach(k => { slots[k] = root.querySelector('[data-dashboard-slot="' + k + '"]'); });
    Object.assign(renderers, {live: live, flow: flow, ops: ops});
    if (o.endpoint !== undefined) {
      try {
        if (typeof o.endpoint !== 'string' || !o.endpoint.trim()) throw new Error('endpoint');
        const base = new URL((doc.location || window.location).href);
        const url = new URL(o.endpoint, base);
        if (!/^https?:$/.test(url.protocol) || url.origin !== base.origin || url.username || url.password) throw new Error('origin');
        endpoint = url.href;
      } catch (_) { error = 'Endpoint configuration rejected'; }
    }
    if (pauseButton) pauseButton.addEventListener('click', pause);
    if (resumeButton) resumeButton.addEventListener('click', resume);
    doc.addEventListener('visibilitychange', visibilityChanged);
    paint(); if (endpoint) refresh();
    return {register: register, pause: pause, resume: resume, destroy: function () {
      dead = true; if (timer !== null) cancel(timer); timer = null;
      if (pauseButton) pauseButton.removeEventListener('click', pause);
      if (resumeButton) resumeButton.removeEventListener('click', resume);
      doc.removeEventListener('visibilitychange', visibilityChanged);
    }};
  };
  // The host may inject this configuration before this deferred local script.
  // No endpoint or identity is inferred when configuration is absent.
  const root = document.getElementById && document.getElementById('dashboard');
  if (root) window.dashboard = window.createDashboard(root, window.dashboardConfig || {});
}());
