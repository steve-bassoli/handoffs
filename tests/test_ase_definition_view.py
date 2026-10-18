"""Detached renderer checks; a Node skip is not JavaScript verification."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


RENDERER = Path(__file__).resolve().parents[1] / 'app/static/ase-definition.js'
URLS = ['https://arxiv.org/pdf/2508.07407', 'https://arxiv.org/pdf/2505.22954']
MODEL = {
    'schema_version': 'ASE-v1',
    'definition': 'A proposed pattern, not observed repository conformance.',
    'properties': [{'id': 'human-authority', 'text': 'Human approval gates govern integration.',
                    'status': 'proposed'}],
    'prior_work': [{
        'id': 'survey', 'url': URLS[0], 'summary': 'Not independently reviewed here.',
        'status': 'not_independently_reviewed',
        'provenance': {'source': 'ase_sources', 'sha256':
                       '24c95d2581a9e91e46b0c9ed4500a10631971cca3f05a34e6b7dc3582aff3e73',
                       'external_reviewed': False}}],
    'limits': ['No first-of-its-kind claim is established.',
               'The source hash identifies shelf content, not article verification.']}

SCRIPT = r'''
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.value = ''; }
  set textContent(value) { this.value = String(value); this.children = []; }
  get textContent() { return this.value + this.children.map(n => n.textContent).join('\n'); }
  set innerHTML(_) { throw Error('innerHTML forbidden'); }
  setAttribute(key, value) { this.attrs[key] = String(value); }
  appendChild(child) { this.children.push(child); child.parentNode = this; return child; }
}
const window = {};
const document = { createElement: tag => new Element(tag) };
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), {window, document});
assert.deepStrictEqual(Object.keys(window), ['renderAseDefinition']);
const model = JSON.parse(process.argv[2]);
const before = JSON.stringify(model);
function freeze(value) {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(freeze); Object.freeze(value);
  }
  return value;
}
freeze(model);
const render = window.renderAseDefinition;
const root = render(model);
const walk = n => [n, ...n.children.flatMap(walk)];
const links = n => walk(n).filter(x => x.tag === 'a');
assert.strictEqual(root.tag, 'section');
assert.strictEqual(root.parentNode, undefined);
assert.strictEqual(root.attrs['aria-label'], 'ASE definition');
function preserved(value) {
  if (typeof value === 'string') assert(root.textContent.includes(value), value);
  else if (typeof value === 'boolean') {
    assert(root.textContent.includes('external_reviewed: ' + String(value)));
  } else if (value && typeof value === 'object') Object.values(value).forEach(preserved);
}
preserved(model);
const urls = JSON.parse(process.argv[3]);
const expected = model.prior_work.filter(p => urls.includes(p.url)).map(p => p.url);
assert.deepStrictEqual(links(root).map(n => n.attrs.href), expected);
if (process.argv[4] === 'canonical') {
  assert.deepStrictEqual(expected, urls);
  const citations = root.children.filter(n => n.tag === 'ul')[1].children;
  const missing = model.prior_work.map((p, i) => p.url === null ? i : -1).filter(i => i >= 0);
  assert(missing.length > 0, 'Canonical fixture must retain its unresolved reference');
  missing.forEach(i => {
    assert(citations[i].textContent.includes('Evidence unavailable'));
    assert.strictEqual(links(citations[i]).length, 0);
  });
}
assert.strictEqual(JSON.stringify(model), before);
for (const absent of [undefined, null, [], false, 9, 'text', {},
  {properties: [null, 3], prior_work: [null, false], limits: [null]}]) {
  const node = render(absent);
  assert(node.textContent.includes('Unavailable'));
  assert.strictEqual(links(node).length, 0);
}
// Keep adversarial mutations isolated to the original synthetic fixture.
const fixture = JSON.parse(process.argv[5]);
const clone = () => JSON.parse(JSON.stringify(fixture));
for (const url of urls) {
  const m = clone(); m.prior_work[0].url = url;
  assert.strictEqual(links(render(m))[0].attrs.href, url);
}
for (const url of [null, 3, 'javascript:alert(1)', '<img src=x onerror=alert(1)>',
  ...urls.flatMap(u => [u + '?q=1', u + '#x', u + '/evil',
    u.replace('https:', 'http:'), u.replace('arxiv.org', 'arxiv.org:443'),
    u.replace('arxiv.org', 'user@arxiv.org'), u.replace('arxiv.org', 'arxiv.org.evil')])]) {
  const m = clone(); m.prior_work[0].url = url;
  const node = render(m);
  assert.strictEqual(links(node).length, 0);
  assert(node.textContent.includes('Evidence unavailable'));
  if (typeof url === 'string') assert(node.textContent.includes(url));
}
for (const provenance of [null, {}, [], {source: 'x', sha256: 'bad', external_reviewed: false}]) {
  const m = clone(); m.prior_work[0].provenance = provenance;
  const node = render(m);
  assert.strictEqual(links(node).length, 0);
  assert(node.textContent.includes('Evidence unavailable'));
}
const hostile = clone();
hostile.definition = '<script>alert(1)</script>';
hostile.limits = ['<img src=x onerror=alert(1)>'];
const safe = render(hostile);
assert(safe.textContent.includes(hostile.definition));
assert(safe.textContent.includes(hostile.limits[0]));
assert(!walk(safe).some(n => ['script', 'img'].includes(n.tag)));
assert.strictEqual(JSON.stringify(model), before);
'''


@pytest.mark.parametrize('kind', ['synthetic', 'canonical'])
def test_ase_definition_renderer(kind):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node unavailable; JavaScript checks not executed')
    if kind == 'canonical':
        from app.ase_definition import build_definition
        model = build_definition()
    else:
        model = MODEL
    result = subprocess.run(
        [node, '-e', SCRIPT, str(RENDERER), json.dumps(model), json.dumps(URLS),
         kind, json.dumps(MODEL)],
        capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
