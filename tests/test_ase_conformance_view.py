"""Synthetic renderer checks plus the contract owner's empty-root fixture."""
import copy
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'app/static/ase-conformance.js'
NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='Node unavailable: renderer not executed')
HARNESS = r'''
const fs = require('fs');
const vm = require('vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.own = ''; this.parentNode = null; }
  set textContent(value) { this.own = String(value); this.children = []; }
  get textContent() { return this.own + this.children.map(c => c.textContent).join('\n'); }
  set innerHTML(value) { throw Error('innerHTML forbidden'); }
  appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
}
const sandbox = {window: {}, document: {createElement: tag => new Element(tag)}};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), sandbox, {timeout: 1000});
const before = JSON.stringify(input);
function freeze(v) {
  if (v && typeof v === 'object') { Object.values(v).forEach(freeze); Object.freeze(v); }
}
freeze(input);
sandbox.model = input;
const root = vm.runInContext('window.renderAseConformance(model)', sandbox, {timeout: 1000});
console.log(JSON.stringify({text: root.textContent, detached: root.parentNode === null,
  unchanged: before === JSON.stringify(input), exports: Object.keys(sandbox.window)}));
'''


def fixture_model():
    def evidence(path, kind='source'):
        return {'path': path, 'sha256': 'a' * 64, 'kind': kind}
    def row(name, status, items):
        return {'id': name, 'status': status, 'scope': 'Synthetic named check',
                'reason': 'Synthetic probe outcomes', 'evidence': items, 'conflicts': []}
    return {'schema_version': 'ase-narrow-v1', 'scope': 'Synthetic renderer fixture',
            'properties': [row('decomposition', 'pass', [evidence('app/complexity.py'),
                            evidence('app/complexity.py', 'behavior')]),
                           row('human_gates', 'partial', [evidence('PROJECT_CHARTER.md')]),
                           row('humane_limits', 'gap', [])],
            'limitations': ['Synthetic inputs; not observed checkout output.']}


def render(model):
    result = subprocess.run([NODE, '-e', HARNESS, str(JS)], input=json.dumps(model),
                            text=True, capture_output=True, timeout=5, check=True)
    return json.loads(result.stdout)


def test_statuses_detached_immutable_and_single_export():
    model = fixture_model()
    before = copy.deepcopy(model)
    result = render(model)
    for status in ('pass', 'partial', 'gap'):
        assert 'Status: ' + status in result['text']
    assert 'behavior was not assessed' in result['text']
    assert result['detached'] and result['unchanged'] and model == before
    assert result['exports'] == ['renderAseConformance']
    assert 'human verification or certification' in result['text']


@pytest.mark.parametrize('case', ['missing', 'malformed', 'path', 'hash', 'mismatch',
                                  'conflict', 'charter_pass', 'version', 'extra', 'order'])
def test_invalid_claims_never_pass(case):
    model = fixture_model()
    row = model['properties'][0]
    if case == 'missing':
        row['evidence'] = []
    elif case == 'malformed':
        row['evidence'] = [None]
    elif case == 'path':
        row['evidence'][0]['path'] = 'untrusted.py'
    elif case == 'hash':
        row['evidence'][0]['sha256'] = 'not-a-hash'
    elif case == 'mismatch':
        row['evidence'][1]['sha256'] = 'b' * 64
    elif case == 'conflict':
        row['conflicts'] = ['probe disagrees']
    elif case == 'charter_pass':
        row['status'] = 'gap'
        model['properties'][1]['status'] = 'pass'
    elif case == 'version':
        model['schema_version'] = 'future'
    elif case == 'extra':
        row['certified'] = True
    elif case == 'order':
        model['properties'].reverse()
    output = render(model)['text']
    assert 'Status: pass' not in output
    assert 'Status: not assessed' in output
    if case == 'conflict':
        assert 'probe disagrees' in output


def test_absent_model():
    assert 'Status: pass' not in render(None)['text']
    assert render(None)['text'].count('Status: not assessed') == 3


def test_hostile_text_is_literal():
    model = fixture_model()
    hostile = '<img src=x onerror="throw Error(1)"><script>alert(1)</script>'
    model['scope'] = hostile
    model['properties'][0]['reason'] = hostile
    model['properties'][0]['conflicts'] = [hostile]
    model['limitations'] = [hostile]
    output = render(model)['text']
    assert output.count(hostile) == 4
    assert 'Status: pass' not in output


def test_canonical_document_fixture_stays_three_gaps():
    document = (ROOT / 'docs/ase_conformance_contract.md').read_text(encoding='utf-8')
    blocks = re.findall(r'^```ase-fixture\s*\n(.*?)^```\s*$', document, re.M | re.S)
    assert len(blocks) == 1, 'Expected exactly one canonical ase-fixture JSON block'
    model = json.loads(blocks[0])
    assert [row['status'] for row in model['properties']] == ['gap'] * 3
    assert all(row['evidence'] == [] for row in model['properties'])
    output = render(model)['text']
    assert output.count('Status: gap') == 3
    assert output.count('Evidence: not assessed') == 3
    assert 'Status: pass' not in output
    assert 'Status: not assessed' not in output
