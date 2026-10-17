from pathlib import Path
import json
import shutil
import subprocess

import pytest


def test_history_drilldown_with_timeline_filters_and_dependency_deltas():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the history drilldown check')
    sources = {
        'drilldown': Path('app/static/history-drilldown.js').read_text(encoding='utf-8'),
        'history': Path('app/static/history.js').read_text(encoding='utf-8'),
    }
    checks = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const sources = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
function element(tag, text, className) {
  return {tag, textContent: text, className, children: [],
    append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = items; },
    addEventListener(name, fn) { this[name] = fn; }};
}
const walk = node => [node, ...(node.children || []).flatMap(walk)];
const text = node => walk(node).map(item => item.textContent).filter(Boolean).join(' ');
const byClass = (root, name) => walk(root).find(node => node.className === name);
const context = {window: {}};
vm.runInNewContext(sources.drilldown, context);
vm.runInNewContext(sources.history, context);
assert.equal(typeof context.window.renderHistory, 'function');
const events = Object.freeze([
  Object.freeze({kind: 'dependencies_set', created_at: '2024-01-01T00:00:00Z', data: Object.freeze({depends_on: Object.freeze(['old'])})}),
  Object.freeze({kind: 'dependencies_set', created_at: '2024-01-02T00:00:00Z', data: Object.freeze({depends_on: Object.freeze(['new'])})}),
  Object.freeze({kind: 'package_attached', created_at: '2024-01-03T00:00:00Z', data: Object.freeze({files: Object.freeze(['manifest.json']), sha256: 'abc'})}),
  Object.freeze({kind: 'posted', created_at: '2024-01-04T00:00:00Z', data: Object.freeze({via: ''})}),
  Object.freeze({kind: 'posted', created_at: '2024-01-05T00:00:00Z', data: Object.freeze({})}),
  Object.freeze({kind: 'ai_started', created_at: '2024-01-06T00:00:00Z', data: Object.freeze({})})
]);
const root = context.window.renderHistory(events, {element});
const nav = byClass(root, 'history-filters');
const rows = () => {
  const container = byClass(root, 'history-events');
  assert.ok(container, 'timeline provides a history-events container');
  return walk(container).filter(node => node.tag === 'article');
};
const hrefs = () => walk(root).filter(node => node.tag === 'a').map(node => node.href);
assert.ok(nav, 'timeline supplies filter navigation');
assert.equal(rows().length, 6, 'all events initially render as articles');
assert.match(text(root), /Change baseline unavailable/);
assert.match(text(root), /Added prerequisites/);
assert.match(text(root), /Removed prerequisites/);
assert.ok(hrefs().includes('#opp=new'), 'rendered added prerequisite links to new opportunity');
assert.ok(hrefs().includes('#opp=old'), 'rendered removed prerequisite links to old opportunity');
assert.match(text(root), /Ready for human verification/);
const buttons = Object.fromEntries(nav.children.map(button => [button.textContent, button]));
for (const name of ['All', 'Human', 'Automation', 'Evidence', 'AI']) assert.equal(typeof buttons[name].click, 'function');
buttons.Automation.click(); assert.equal(rows().length, 1, 'empty via is Automation');
buttons.Human.click(); assert.equal(rows().length, 4, 'unmarked dependencies, evidence and posted event are Human (no automation marker, not ai_)');
buttons.Evidence.click(); assert.equal(rows().length, 1, 'package evidence filter');
buttons.AI.click(); assert.equal(rows().length, 1, 'AI filter');
buttons.All.click(); assert.equal(rows().length, 6, 'All restores all rows');
assert.deepEqual(events[0].data.depends_on, ['old'], 'rendering does not mutate input');
assert.ok(context.window.historyDetail({kind: 'dependencies_set'}, {element}));
assert.equal(context.window.historyDetail({kind: 'posted', data: {}}, {element}), null);
'''
    subprocess.run([node, '-e', checks], input=json.dumps(sources), check=True,
                   capture_output=True, text=True)
