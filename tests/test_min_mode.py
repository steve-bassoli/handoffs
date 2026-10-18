"""MIN mode: one pressure question, then exactly three options, reads only."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which('node')
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'app/static/min.js'

HARNESS = r'''
const vm = require('node:vm');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
class Node {
  constructor(tag) { this.tagName = tag; this.children = []; this.textContent = ''; this.listeners = {}; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  addEventListener(name, fn) { this.listeners[name] = fn; }
  set innerHTML(value) { throw Error('unsafe innerHTML'); }
}
const walk = node => [node].concat(...node.children.flatMap(walk));
const text = node => node.textContent + node.children.map(text).join('');
const calls = [];
const store = new Map(Object.entries(input.stored || {}));
const context = {window: {}, document: {createElement: tag => new Node(tag)},
  fetch: () => { throw Error('network forbidden'); }, URLSearchParams};
vm.runInNewContext(input.source, context);
const root = new Node('main');
const section = context.window.minMode.render(root, {
  document: context.document, user: 'nate',
  storage: {get: k => store.has(k) ? store.get(k) : null, set: (k, v) => store.set(k, v), remove: k => store.delete(k)},
  api: async path => { calls.push(path); if (input.apiFails) throw Error('down'); return input.board || []; },
});
const choices = () => walk(section).filter(n => n.className === 'choice');
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
(async () => {
  const out = {steps: []};
  const snap = label => out.steps.push({label, text: text(section), choices: choices().map(c => ({tag: c.tagName, label: c.textContent, href: c.href || null})),
    stored: Object.fromEntries(store), calls: [...calls]});
  await tick(); snap('initial');
  for (const step of input.steps || []) {
    if (step.click !== undefined) {
      const target = walk(section).find(n => n.listeners.click && n.textContent.startsWith(step.click));
      if (!target) throw Error('no clickable ' + step.click);
      target.listeners.click();
    }
    await tick(); await tick(); snap(step.click);
  }
  out.anyWrite = walk(section).some(n => n.tagName === 'form' || n.tagName === 'input');
  console.log(JSON.stringify(out));
})().catch(error => { console.error(error); process.exitCode = 1; });
'''


def run(**payload):
    if not NODE:
        pytest.skip('Node is required for the MIN mode view test')
    payload['source'] = SOURCE.read_text(encoding='utf-8')
    result = subprocess.run([NODE, '-e', HARNESS], input=json.dumps(payload), text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_min_page_is_served(client):
    response = client.get('/min')
    assert response.status_code == 200
    assert 'min-root' in response.text and '/static/min.js' in response.text


def test_asks_pressure_first_then_exactly_three_options_per_level():
    board = [{'id': 'abc-1', 'title': 'Fix the thing'}]
    for level, first in ((1, 'Take the next open task'), (2, 'Read one open task'), (3, 'Read one open task')):
        out = run(board=board, steps=[{'click': f'{level} ·'}])
        initial, after = out['steps']
        assert 'How much pressure are you under right now?' in initial['text']
        assert [c['label'][:1] for c in initial['choices']] == ['1', '2', '3']
        assert initial['calls'] == []
        assert len(after['choices']) == 3, after['choices']
        assert after['choices'][0]['label'].startswith(first)
        assert after['choices'][0]['href'] == '/?user=nate#task=abc-1'
        assert after['calls'] == ['/bounties?limit=1'], 'one read, nothing else'
        assert after['stored'] == {'commons-min-pressure': str(level)}
        assert not out['anyWrite']


def test_overloaded_options_are_rest_shaped_and_rest_view_starts_nothing():
    out = run(board=[], steps=[{'click': '3 ·'}, {'click': 'Step away for now'}, {'click': 'Back to the three options'}])
    options = out['steps'][1]['choices']
    assert [c['tag'] for c in options] == ['a', 'a', 'button']
    assert 'No open task right now' in out['steps'][1]['text']
    assert options[1]['href'] == '/dashboard?user=nate'
    rest = out['steps'][2]
    assert 'Nothing here needs you right now.' in rest['text'] and rest['choices'] == []
    assert rest['calls'] == ['/bounties?limit=1']
    assert len(out['steps'][3]['choices']) == 3


def test_remembered_pressure_can_be_changed_and_read_failure_degrades_to_board():
    out = run(stored={'commons-min-pressure': '2'}, apiFails=True, steps=[{'click': 'change'}])
    initial, changed = out['steps']
    assert len(initial['choices']) == 3
    assert initial['choices'][0]['href'] == '/?user=nate'
    assert 'Could not read the board' in initial['text']
    assert 'How much pressure' in changed['text'] and changed['stored'] == {}
