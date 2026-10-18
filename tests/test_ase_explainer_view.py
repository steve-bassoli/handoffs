"""Node-vm text-only renderer checks; no browser or host integration claimed."""
import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from app.ase_adoption import build_adoption
from app.ase_definition import build_definition

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'app/static/ase-explainer.js'
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
const root = vm.runInContext('window.renderAseExplainer(model)', sandbox, {timeout: 1000});
function tags(node) { return [node.tag].concat(...node.children.map(tags)); }
console.log(JSON.stringify({text: root.textContent, tags: tags(root),
  detached: root.parentNode === null, unchanged: before === JSON.stringify(input),
  exports: Object.keys(sandbox.window)}));
'''


def fixture_model():
    rows = []
    for identity, status, path in [('decomposition', 'pass', 'app/complexity.py'),
                                   ('human_gates', 'partial', 'PROJECT_CHARTER.md'),
                                   ('humane_limits', 'gap', 'PROJECT_CHARTER.md')]:
        evidence = [] if status == 'gap' else [dict(path=path, sha256='a' * 64, kind='source')]
        if status == 'pass':
            evidence.append(dict(path=path, sha256='a' * 64, kind='behavior'))
        rows.append(dict(id=identity, status=status, scope='Synthetic only',
                         reason='Synthetic named check', evidence=evidence, conflicts=[]))
    card = dict(schema_version='ase-narrow-v1', scope='Synthetic fixture',
                properties=rows, limitations=['Synthetic, not checkout evidence.'])
    return build_adoption(build_definition(), card)


def render(model):
    result = subprocess.run([NODE, '-e', HARNESS, str(JS)], input=json.dumps(model),
                            text=True, capture_output=True, timeout=5, check=True)
    return json.loads(result.stdout)


def test_readable_labels_gates_detached_and_immutable():
    model = fixture_model()
    before = copy.deepcopy(model)
    result = render(model)
    for label in ('Auditable Self-improving Ecosystem', 'Decomposition', 'Human Gates', 'Humane Limits'):
        assert label in result['text']
    for status in ('pass', 'partial', 'gap'):
        assert 'Status: ' + status in result['text']
    assert 'Insufficient evidence; not proof of absence' in result['text']
    assert 'Incomplete or conflicting evidence remains unresolved' in result['text']
    assert 'unresolved evidence is not human acceptance' in result['text']
    assert 'REST preserves access and recognition' in result['text']
    assert result['text'].index('Human gates') < result['text'].index('Action:')
    assert result['detached'] and result['unchanged'] and model == before
    assert result['exports'] == ['renderAseExplainer']
    assert set(result['tags']) <= {'section', 'h2', 'h3', 'p'}


@pytest.mark.parametrize('case', ['missing', 'version', 'missing_gates', 'row',
                                  'evidence', 'conflict', 'references', 'duplicate'])
def test_bad_models_cannot_show_pass(case):
    model = fixture_model()
    if case == 'missing':
        model = None
    elif case == 'version':
        model['schema_version'] = 'future'
    elif case == 'missing_gates':
        model['gates'] = []
    elif case == 'row':
        model['capabilities'][0] = None
    elif case == 'evidence':
        model['capabilities'][0]['evidence'] = []
    elif case == 'conflict':
        model['capabilities'][0]['conflicts'] = ['Unresolved conflict']
    elif case == 'references':
        model['capabilities'][0]['properties'] = []
    else:
        model['capabilities'].append(copy.deepcopy(model['capabilities'][0]))
    result = render(model)
    assert 'Status: pass' not in result['text']
    assert 'not assessed' in result['text']


def test_hostile_text_is_literal_and_all_guidance_is_supplied():
    model = fixture_model()
    hostile = '<img src=x onerror="throw Error(1)"><script>alert(1)</script>'
    model['definition'] = hostile
    model['capabilities'][1]['reason'] = hostile
    model['capabilities'][1]['conflicts'] = [hostile]
    model['limitations'].append(hostile)
    model['workflow'][0]['action'] = 'Unique supplied offline instruction'
    result = render(model)
    assert result['text'].count(hostile) == 4
    assert 'Unique supplied offline instruction' in result['text']
    assert set(result['tags']) <= {'section', 'h2', 'h3', 'p'}


def test_absent_input_properties_remain_gaps():
    result = render(build_adoption(None, None))
    assert result['text'].count('Status: gap') == 3
    assert 'Status: pass' not in result['text']
    assert 'Missing or invalid property reference' in result['text']
