"""Proposed renderer checks; Node absence is explicitly unverified."""
import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'app/static/decomposition-teaching.js'
HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.text = ''; }
  set textContent(value) { this.text = String(value); this.children = []; }
  get textContent() { return this.text + this.children.map(c => c.textContent).join(''); }
  set innerHTML(value) { throw new Error('Unsafe HTML assignment'); }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  appendChild(child) { this.children.push(child); return child; }
}
const window = {};
const sandbox = {window, document: {createElement: tag => new Element(tag)}};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), sandbox, {timeout: 1000});
const before = JSON.stringify(input);
function freeze(value) {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
}
freeze(input);
const panel = window.renderDecompositionTeaching(input.options);
const again = window.renderDecompositionTeaching(input.options);
console.log(JSON.stringify({panel, text: panel.textContent,
  exports: Object.keys(window), globals: Object.keys(sandbox),
  unchanged: before === JSON.stringify(input), reusable: panel !== again}));
"""


def render(options):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node unavailable: renderer checks unverified')
    result = subprocess.run(
        [node, '-e', HARNESS, str(SCRIPT)],
        input=json.dumps({'options': options}), text=True,
        capture_output=True, check=True, timeout=10,
    )
    return json.loads(result.stdout)


def arbitrary_teaching():
    return {
        'version': 19, 'source': 'custom source', 'min_children': 7,
        'rules': {'OTHER': ['DIFFERENT']}, 'explanation': 'Supplied explanation',
        'fingerprint': 'untrusted supplied fingerprint',
        'examples': [{'id': 'custom', 'explanation': 'Supplied example',
                      'splits': [{'parent': 'OTHER', 'children': ['DIFFERENT']}],
                      'valid': False}],
    }


def test_producer_content_and_order():
    from app.decomposition_teaching import build_teaching

    teaching = build_teaching()
    result = render({'teaching': teaching})
    text = result['text']
    for value in (teaching['source'], teaching['fingerprint'], teaching['explanation']):
        assert value in text
    positions = []
    for example in teaching['examples']:
        positions.append(text.index(example['id']))
        assert example['explanation'] in text
        assert 'Supplied outcome: ' + ('valid' if example['valid'] else 'invalid') in text
        for split in example['splits']:
            assert split['parent'] + ' -> [' + ', '.join(split['children']) + ']' in text
    assert positions == sorted(positions)
    assert 'Teaching reference malformed.' not in text


def test_arbitrary_content_single_export_and_no_mutation():
    teaching = arbitrary_teaching()
    result = render({'teaching': teaching})
    assert 'OTHER -> [DIFFERENT]' in result['text']
    assert 'Supplied outcome: invalid' in result['text']
    assert teaching['fingerprint'] in result['text']
    assert result['exports'] == ['renderDecompositionTeaching']
    assert sorted(result['globals']) == ['document', 'window']
    assert result['unchanged'] and result['reusable']
    assert result['panel']['attrs']['aria-label']
    assert result['panel']['children'][0]['tag'] == 'h2'


def test_hostile_strings_are_text_not_elements():
    teaching = arbitrary_teaching()
    hostile = '<img src=x onerror=alert(1)><script>bad()</script>'
    teaching.update(source=hostile, explanation=hostile, fingerprint=hostile)
    teaching['examples'][0].update(id=hostile, explanation=hostile)
    teaching['examples'][0]['splits'] = [{'parent': hostile, 'children': [hostile]}]
    teaching['rules'] = {hostile: [hostile]}
    result = render({'teaching': teaching})
    assert hostile in result['text']
    def tags(node):
        return [node['tag']] + [tag for child in node['children'] for tag in tags(child)]
    assert not {'img', 'script'} & set(tags(result['panel']))


@pytest.mark.parametrize('options', [None, {}, {'teaching': None}])
def test_absent(options):
    assert 'Teaching reference unavailable.' in render(options)['text']


@pytest.mark.parametrize('field,value', [
    ('version', True), ('min_children', False), ('source', 3),
    ('rules', {'HIGH': 'LOW'}), ('examples', [{}]), ('fingerprint', None),
])
def test_malformed(field, value):
    teaching = copy.deepcopy(arbitrary_teaching())
    teaching[field] = value
    assert 'Teaching reference malformed.' in render({'teaching': teaching})['text']
