import json
from pathlib import Path
import shutil
import subprocess

import pytest


def test_history_timeline_labels_order_deltas_and_attribution():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the browser history check')
    payload = json.dumps({
        'timeline': Path('app/static/history.js').read_text(encoding='utf-8'),
        'drilldown': Path('app/static/history-drilldown.js').read_text(encoding='utf-8'),
    })
    script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = JSON.parse(fs.readFileSync(0, 'utf8'));
function element(tag, text, className) {
  return {tag, textContent: text, className, children: [], listeners: {},
    append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = items; },
    addEventListener(name, fn) { this.listeners[name] = fn; }};
}
function descendants(node) {
  return [node].concat(...node.children.flatMap(descendants));
}
const context = {window: {}};
vm.runInNewContext(source.drilldown, context);
vm.runInNewContext(source.timeline, context);
const labels = {
  dependencies_set: 'Dependencies changed', posted: 'Ticket posted',
  package_attached: 'Package attached', ai_followups: 'AI follow-up',
  ai_usage: 'AI usage recorded', ai_source: 'AI source recorded',
  ai_started: 'AI run started', taken: 'Work taken', ai_failed: 'AI run failed',
  ai_model_changed: 'AI model changed', ai_retried: 'AI run retried',
  ai_answers: 'AI answers recorded', ai_ask: 'AI asked a question',
  opportunity_updated: 'Ticket updated', reopened: 'Ticket reopened',
  'legacy:assigned': 'Legacy work assigned', 'legacy:completed': 'Legacy work completed'
};
const events = Object.keys(labels).map((kind, index) => ({
  kind, actor: 'steve', created_at: `2026-01-${String(index + 1).padStart(2, '0')}T00:00:00Z`,
  data: {depends_on: ['first'], work_type: 'implementation', complexity: 'LOW',
    kind: 'proof', files: ['manifest.json'], sha256: {manifest: 'abc'}, model: 'm',
    outcome: 'done', delta: {input_tokens: 7}, code: 'failed', stage: 'review',
    previous_model: 'old', answers: ['answer'], questions: ['question'],
    updated: {title: 'Updated'}, previous_state: 'paused', revision: 'r1'}
}));
events.push(
  {kind: 'future_kind', actor: 'nate', created_at: '2026-02-01T00:00:00Z', data: {via: ''}},
  {kind: 'dependencies_set', actor: 'steve', created_at: '2026-03-01T00:00:00Z', data: {depends_on: ['second']}},
  {kind: 'taken', actor: 'human', created_at: '2026-04-01T00:00:00Z', data: {}},
  {kind: 'ai_started', actor: 'bot', created_at: '2026-05-01T00:00:00Z', data: {via: 'relay', model: 'm'}}
);
const originalKinds = events.map(event => event.kind);
const detailCalls = [];
const actualDetail = context.window.historyDetail;
context.window.historyDetail = (event, helpers) => {
  detailCalls.push([event, helpers.dependencyDelta]);
  return actualDetail(event, helpers);
};
const root = context.window.renderHistory(events, {element});
const rows = descendants(root).find(node => node.className === 'history-events');
assert.equal(rows.children[0].children[0].textContent, 'AI run started');
assert.equal(rows.children[1].children[0].textContent, 'Work taken');
assert.equal(rows.children[3].children[0].textContent, 'future_kind');
assert.equal(rows.children[3].children[2].textContent, 'nate via ');
assert.equal(rows.children[1].children[2].textContent, 'human');
assert.deepEqual(events.map(event => event.kind), originalKinds);
const renderedLabels = rows.children.map(row => row.children[0].textContent);
Object.values(labels).forEach(label => assert.ok(renderedLabels.includes(label)));
const january = detailCalls.find(([event]) => event.created_at === '2026-01-01T00:00:00Z')[1];
const march = detailCalls.find(([event]) => event.created_at === '2026-03-01T00:00:00Z')[1];
assert.equal(january.baselineAvailable, false);
assert.equal(march.baselineAvailable, true);
assert.deepEqual(Array.from(march.added), ['second']);
assert.deepEqual(Array.from(march.removed), ['first']);
'''
    result = subprocess.run(
        [node, '-e', script], input=payload, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr
