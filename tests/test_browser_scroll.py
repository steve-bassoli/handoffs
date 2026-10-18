"""Exercise the real detail refresh without a browser, network, or model calls."""
import shutil
import subprocess

import pytest


def test_detail_refresh_is_atomic_and_preserves_the_reading_position():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the JavaScript scroll regression')
    checks = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/app.js', 'utf8');
const show = source.slice(source.indexOf('async function show(id) {'), source.indexOf('async function encodeSourceZip('));
class Element {
  constructor(tag, text) { this.tag = tag; this.textContent = text; this.childNodes = []; this.hidden = false; }
  append(...nodes) { this.childNodes.push(...nodes); }
  setAttribute() {}
  querySelector(selector) {
    if (selector === 'summary') return this.childNodes.find(node => node.tag === 'summary');
    return null;
  }
  querySelectorAll(selector) {
    return this.childNodes.flatMap(node => [...(node.tag === selector ? [node] : []), ...node.querySelectorAll(selector)]);
  }
}
function disclosure(open) {
  const node = new Element('details'); node.open = open;
  node.append(new Element('summary', 'Context & constellation')); return node;
}
(async () => {
 for (const task of [
   {status: 'working', user: 'nate', claimant: 'nate'},
   {status: 'open', user: 'steve', funded: true},
   {status: 'open', user: 'steve', funded: false, parent_id: 'parent'},
   {status: 'open', user: 'steve', funded: true, target: 'nate'},
   {status: 'open', user: 'steve', funded: false}
 ]) {
  for (const same of [true, false]) {
    for (const panelVisible of [true, false]) {
      const current = new Element('section');
      const oldDetails = disclosure(true); current.append(oldDetails);
      let swaps = 0, newDetails, oldContent = true;
      current.querySelector = selector => selector === '.detail-head code' ? {textContent: same ? 'offer' : 'other'}
        : selector === '.ai-panel' ? {getBoundingClientRect: () => ({top: (oldContent ? 100 : 140), bottom: panelVisible ? 600 : -1})} : null;
      current.replaceChildren = (...nodes) => { swaps++; oldContent = false; current.childNodes = nodes; };
      const scrolls = [];
      const context = {
        aiPoll: null, proofPoll: null, selected: 'offer', user: task.user, clearTimeout() {},
        history: {replaceState() {}}, encodeURIComponent,
        window: {scrollX: 0, scrollY: 1000, innerHeight: 800, scrollTo: (x, y) => scrolls.push([x, y])},
        api: async () => ({id: 'offer', phase: 'Claimed', status: 'working', complexity: 'LOW', criteria: ['Works'],
          context_links: [], creator: 'steve', deliveries: [], events: [], ...task}),
        $: id => id === 'detail' ? current : new Element('section'),
        element: (tag, text) => new Element(tag, text),
        workflowSection: async (_data, target) => {
          assert.equal(swaps, 0, 'Visible content must remain intact during async rendering');
          assert.equal(current.childNodes[0], oldDetails);
          assert.notEqual(target, current);
          newDetails = disclosure(false); target.append(newDetails);
          context.window.scrollY = 1200; // The reader scrolls while the request is pending.
        },
        proofSection() {},
        artifactsSection: async () => assert.equal(swaps, 0),
        aiSection: async () => assert.equal(swaps, 0),
      };
      vm.runInNewContext(show, context);
      await context.show('offer');
      assert.equal(swaps, 1, 'Commit the complete view in one DOM replacement');
      assert.equal(current.hidden, false);
      assert.equal(newDetails.open, same);
      assert.deepEqual(scrolls, same ? [[0, panelVisible ? 1240 : 1200]] : []);
      const canClaim = task.status === 'open' && (task.funded || task.parent_id) && !task.target;
      const labels = current.querySelectorAll('button').map(node => node.textContent);
      assert.equal(labels.includes('Accept'), Boolean(canClaim));
      assert.equal(labels.includes('Volunteer manually'), Boolean(canClaim));
    }
  }
 }
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    subprocess.run([node, '-e', checks], check=True, capture_output=True, text=True)
