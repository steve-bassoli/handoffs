import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/work_checkpoints_v1.json'
SOURCE = ROOT / 'app/static/work-checkpoint.js'


def render_in_node(records, hostile=None):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for browser checkpoint-view checks')
    payload = json.dumps({
        'source': SOURCE.read_text(encoding='utf-8'),
        'records': records, 'hostile': hostile,
    })
    script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const allowed = new Set(['section', 'h2', 'h3', 'p', 'strong', 'span', 'ul', 'li']);
const mappings = {
  1: ['Ready: focused pacing.', 'focused_pacing', 'continue'],
  2: ['Reduce load: checkpoint before continuing.', 'reduce_load_checkpoint', 'checkpoint'],
  3: ['Stop now: preserve a minimal authorized work-only checkpoint.', 'stop_now', 'stop']
};
function element(tag, value, className) {
  const node = {tag, className, textContent: value, children: [],
    append(...items) { this.children.push(...items); }};
  Object.defineProperty(node, 'innerHTML', {
    set() { throw new Error('innerHTML assignment is forbidden'); }
  });
  return node;
}
function descendants(node) {
  return [node].concat(...node.children.flatMap(descendants));
}
function texts(card) {
  return descendants(card).map(node => node.textContent);
}
const context = {window: {}};
vm.runInNewContext(payload.source, context);
assert.deepEqual(Object.keys(context.window), ['renderWorkCheckpoint']);
for (const record of payload.records) {
  const before = JSON.stringify(record);
  const card = context.window.renderWorkCheckpoint(record, {element});
  assert.equal(JSON.stringify(record), before);
  const nodes = descendants(card), rendered = texts(card);
  assert.equal(card.tag, 'section');
  assert.ok(nodes.every(node => allowed.has(node.tag)));
  assert.equal(nodes.some(node => Object.keys(node).some(key =>
    /^(on|href$|action$|src$|srcdoc$)/i.test(key))), false);
  assert.ok(rendered.includes('Work checkpoint'));
  assert.ok(rendered.includes(record.completed_action));
  const sections = card.children.filter(node => node.tag === 'section');
  assert.equal(sections.length, 2);
  assert.equal(sections[0].children[0].textContent, 'Completed verification');
  assert.equal(sections[1].children[0].textContent, 'Proposed checks not run');
  for (const [index, key] of ['completed', 'proposed_checks'].entries()) {
    const items = sections[index].children[1].children;
    assert.deepEqual(items.map(item => item.textContent), record.verification[key]);
  }
  assert.ok(rendered.includes(record.next_step.instruction));
  mappings[record.pressure].forEach(value => assert.ok(rendered.includes(value)));
  if (record.usage.status === 'unknown' && record.usage.reservation_retained) {
    assert.ok(rendered.includes('Unknown usage; reservation retained.'));
  }
  if (record.pressure === 3) {
    assert.ok(rendered.includes('Requires existing authority.'));
  }
}
if (payload.hostile) {
  const rendered = texts(context.window.renderWorkCheckpoint(payload.hostile, {element}));
  assert.equal(rendered.filter(value => value === payload.hostile.completed_action).length, 4);
}
'''
    result = subprocess.run(
        [node, '-e', script], input=payload, text=True, capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_canonical_checkpoint_examples_render_inertly():
    fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
    assert fixture['schema_version'] == 'work-checkpoint/v1'
    assert len(fixture['examples']) == 3
    assert {item['pressure'] for item in fixture['examples']} == {1, 2, 3}
    render_in_node(fixture['examples'])


def test_hostile_text_is_inert_in_canonical_stop_shape():
    hostile = '<img src=x onerror=alert(1)>'
    record = {
        'pressure': 3,
        'pressure_action': 'stop_now',
        'completed_action': hostile,
        'verification': {'completed': [hostile], 'proposed_checks': [hostile]},
        'usage': {'status': 'unknown', 'reservation_retained': True},
        'automatic_retry': False,
        'next_step': {'kind': 'stop', 'instruction': hostile,
                      'requires_existing_authority': True},
    }
    render_in_node([record], record)


def test_stop_with_known_usage_and_empty_verification_is_inert():
    fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
    record = next(item for item in fixture['examples'] if item['pressure'] == 3)
    record['usage'] = {'status': 'known', 'reservation_retained': False}
    record['verification'] = {'completed': [], 'proposed_checks': []}
    render_in_node([record])
