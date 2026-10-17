import json
from pathlib import Path
import shutil
import subprocess

import pytest


def test_offline_matrix_renders_canonical_fixture_safely():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the browser evidence-matrix check')
    payload = json.dumps({
        'source': Path('app/static/study-evidence-matrix.js').read_text(encoding='utf-8'),
        'fixture': json.loads(Path('tests/fixtures/study_evidence_inventory_v1.json').read_text(encoding='utf-8')),
    })
    script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const forbidden = new Set(['a', 'button', 'form', 'input', 'script', 'iframe']);
function element(tag) {
  assert.equal(forbidden.has(tag), false, `forbidden element: ${tag}`);
  const node = {tag, children: [], className: '', append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = items; }};
  Object.defineProperty(node, 'textContent', {value: '', writable: true});
  Object.defineProperty(node, 'innerHTML', {set() { throw Error('HTML sink'); }});
  Object.defineProperty(node, 'outerHTML', {set() { throw Error('HTML sink'); }});
  return node;
}
function walk(node) { return [node].concat(...node.children.flatMap(walk)); }
const context = {window: {}, document: {createElement: element}};
vm.runInNewContext(input.source, context, {timeout: 1000});
assert.deepEqual(Object.keys(context.window), ['renderStudyEvidenceMatrix']);
assert.equal(/fetch\s*\(|XMLHttpRequest|WebSocket|addEventListener/.test(input.source), false);
const root = element('root');
const rendered = context.window.renderStudyEvidenceMatrix(root, input.fixture);
const nodes = walk(rendered);
const articles = nodes.filter(node => /^study-evidence-cell /.test(node.className));
assert.equal(root.children[0], rendered);
assert.equal(articles.length, 9);
assert.deepEqual(articles.map(node => node.children[0].textContent), [
  'Projects / REST', 'Projects / SOAP', 'Projects / MCP',
  'Project studies / REST', 'Project studies / SOAP', 'Project studies / MCP',
  'Study detail / REST', 'Study detail / SOAP', 'Study detail / MCP'
]);
assert.equal(nodes.filter(n => n.className === 'study-evidence-cell state-gap').length, 2);
assert.equal(nodes.filter(n => n.className === 'study-evidence-cell state-evidence').length, 4);
assert.equal(nodes.filter(n => n.className === 'study-evidence-cell state-conflict').length, 3);
assert.ok(nodes.some(n => n.textContent === 'Offline inventory — not compatibility certification'));
assert.ok(nodes.some(n => n.textContent === 'Binding: unresolved'));
['Binding:', 'Reference:', 'Outcome:', 'Verification:', 'Verification reference:', 'Provenance:', 'Synthetic:'].forEach(label =>
  assert.ok(nodes.some(n => n.textContent.startsWith(label))));
const hostile = JSON.parse(JSON.stringify(input.fixture));
hostile.cells[0].evidence[0].reference = '<img src=x onerror=alert(1)>';
const hostileNodes = walk(context.window.renderStudyEvidenceMatrix(element('root'), hostile));
assert.ok(hostileNodes.some(n => n.textContent === 'Reference: <img src=x onerror=alert(1)>; '));
const sparse = walk(context.window.renderStudyEvidenceMatrix(element('root'), {cells: []}));
assert.equal(sparse.filter(n => /^study-evidence-cell /.test(n.className)).length, 9);
assert.equal(sparse.filter(n => n.textContent === 'Evidence: none recorded (gap).').length, 9);
'''
    result = subprocess.run(
        [node, '-e', script], input=payload, text=True, capture_output=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
