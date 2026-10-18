"""Sandboxed board result and recovery regressions; no browser or network."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_board_result_states():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the pure JavaScript board check')
    checks = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/app.js', 'utf8');
const slice = source.slice(source.indexOf('let boardRequest = 0;'), source.indexOf('async function transactions()'));
function node(tag, text) { return {tag, text, textContent: text || '', value: '', checked: false, disabled: false, children: [], classList: {add() {}}, append(...items) { this.children.push(...items); }, replaceChildren(...items) { this.children = items; }}; }
const nodes = {}, pending = [];
const context = {view: 'open', offset: 0, pageSize: 12,
  $: id => nodes[id] || (nodes[id] = node()), element: node,
  Option: function(text, value) { this.text = text; this.value = value; },
  api: path => new Promise((resolve, reject) => pending.push({path, resolve, reject})),
  run: f => f(), show() {}};
vm.runInNewContext(slice + '\nthis.board = board;', context);
const card = {id: 'one', title: 'One', phase: 'Posted', status: 'open', complexity: 'LOW', creator: 'steve'};
const text = n => [n.textContent, ...n.children.map(text)].join(' ');
const button = label => { const find = n => n.tag === 'button' && n.text === label ? n : n.children.map(find).find(Boolean); return find(nodes.cards); };
async function finish(promise, items = []) { pending.at(-1).resolve({items, creators: []}); await promise; }
(async () => {
  await finish(context.board(), [card]);
  assert.match(nodes['board-note'].textContent, /Browse · 1 open shown · closed hidden · this page/);
  nodes.search.value = 'missing';
  await finish(context.board());
  assert.match(nodes['board-note'].textContent, /search: missing/);
  let p = button('Clear filters').onclick();
  assert.equal(nodes.search.value, '');
  assert.match(pending.at(-1).path, /view=open/);
  await finish(p, [card]);
  context.view = 'mine'; nodes.search.value = 'missing'; context.$('assigned-by').value = 'nate'; context.$('show-closed').checked = true;
  await finish(context.board());
  p = button('Clear filters').onclick();
  assert.equal(nodes.search.value, '');
  assert.equal(nodes['assigned-by'].value, '');
  assert.equal(nodes['show-closed'].checked, false);
  assert.match(pending.at(-1).path, /status=open,pending,working,blocked,delivered,awaiting_approval/);
  assert.doesNotMatch(pending.at(-1).path, /creator=/);
  await finish(p);
  context.offset = 12;
  await finish(context.board());
  assert.doesNotMatch(text(nodes.cards), /Nothing open|will appear here/);
  assert.equal(nodes.previous.disabled, false);
  p = button('Previous').onclick();
  assert.equal(context.offset, 0);
  await finish(p, [card]);
  p = context.board();
  assert.doesNotMatch(text(nodes.cards), /One/);
  pending.at(-1).reject(new Error('offline')); await p;
  assert.match(text(nodes.cards), /Could not load tasks.*offline/);
  assert.doesNotMatch(text(nodes.cards), /Nothing open|No tasks match|One/);
  assert.match(nodes['board-note'].textContent, /count unavailable/);
  p = button('Retry').onclick(); await finish(p, [card]);
  assert.match(nodes['board-note'].textContent, /My tasks/);
  assert.equal(nodes.cards.children[0].tag, 'article');
  const old = context.board(), latest = context.board();
  pending.at(-1).resolve({items: [card], creators: []}); await latest;
  pending.at(-2).reject(new Error('stale failure')); await old;
  assert.equal(nodes.cards.children[0].tag, 'article');
  assert.doesNotMatch(nodes['board-note'].textContent, /failed/);
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([node, '-e', checks], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
