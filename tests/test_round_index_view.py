import json
import shutil
import subprocess
from pathlib import Path

import pytest


NODE = shutil.which('node')
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'app/static/round-index.js'
FIXTURE = ROOT / 'tests/fixtures/round_index_v1.json'


def run_view(envelope):
    if not NODE:
        pytest.skip('Node is required for the browser-view contract test')
    payload = json.dumps({'source': SOURCE.read_text(encoding='utf-8'), 'envelope': envelope})
    script = r'''
const vm = require('node:vm');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
class Node {
  constructor(tag) { this.tagName = tag; this.children = []; this.textContent = ''; this.value = ''; this.listeners = {}; }
  append(...nodes) { this.children.push(...nodes); return nodes[nodes.length - 1]; }
  removeChild(node) { this.children.splice(this.children.indexOf(node), 1); }
  get firstChild() { return this.children[0] || null; }
  setAttribute() {}
  addEventListener(name, fn) { this.listeners[name] = fn; }
  set innerHTML(value) { throw Error('unsafe innerHTML'); }
  set outerHTML(value) { throw Error('unsafe outerHTML'); }
  insertAdjacentHTML() { throw Error('unsafe HTML insertion'); }
  insertAdjacentText() { throw Error('unexpected adjacent insertion'); }
}
function walk(node) { return [node].concat(...node.children.flatMap(walk)); }
const context = {window: {}, document: {createElement: tag => new Node(tag)},
  fetch: () => { throw Error('network forbidden'); },
  XMLHttpRequest: function () { throw Error('network forbidden'); }};
vm.runInNewContext(input.source, context);
const root = new Node('root');
const section = context.window.renderRoundIndex(root, input.envelope);
const search = walk(section).find(node => node.tagName === 'input');
const anchors = () => walk(section).filter(node => node.tagName === 'a').length;
const text = node => node.textContent + node.children.map(text).join('');
const before = text(section);
const initialAnchors = anchors();
search.value = 'needle'; search.listeners.input();
const filtered = text(section);
const filteredAnchors = anchors();
search.value = 'absent'; search.listeners.input();
const empty = text(section);
console.log(JSON.stringify({before, filtered, empty, initialAnchors, filteredAnchors,
  emptyAnchors: anchors(), attached: root.children[0] === section}));
'''
    result = subprocess.run([NODE, '-e', script], input=payload, text=True,
                            capture_output=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_empty_contract_fixture_renders_availability_and_empty_result():
    result = run_view(json.loads(FIXTURE.read_text(encoding='utf-8')))
    assert result['attached']
    assert result['initialAnchors'] == 0
    assert result['emptyAnchors'] == 0
    assert 'Source availability: source_unavailable' in result['before']
    assert 'No matching round records are available.' in result['before']


def test_hostile_records_are_inert_text_and_filter_locally():
    envelope = {'schema_version': 1, 'issues': [],
                'provenance': {'source_ref': 'round-one-report', 'availability': 'available'},
                'records': [{'round_id': '<img src=x>', 'recorded_date': None,
                  'artifacts': [{'reference': '<b>needle</b>', 'resolution': 'resolved'}],
                  'lesson': '<script>bad()</script>', 'evidence_state': 'unknown_state',
                  'provenance': {'source_ref': 'round-one-report', 'attribution': 'reported',
                                 'verification': 'unverified'}}]}
    result = run_view(envelope)
    assert result['initialAnchors'] == 0
    assert result['filteredAnchors'] == 0
    assert result['emptyAnchors'] == 0
    assert 'Envelope source reference: round-one-report' in result['before']
    assert '<script>bad()</script>' in result['before']
    assert 'Evidence state: unknown_state' in result['before']
    assert 'Attribution: reported' in result['before']
    assert 'Verification: unverified' in result['before']
    assert 'Artifact reference: <b>needle</b> (resolution: resolved)' in result['filtered']
    assert 'No matching round records are available.' in result['empty']
