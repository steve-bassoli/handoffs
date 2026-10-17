import json
from pathlib import Path
import shutil
import subprocess

import pytest


def test_ticket_flow_topology_metadata_current_navigation_and_cycles():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the ticket-flow VM contract check")

    payload = json.dumps({
        "flow": Path("app/static/flow.js").read_text(encoding="utf-8"),
        "fixture": json.loads(
            Path("tests/fixtures/ticket_flow.json").read_text(encoding="utf-8")
        ),
    })
    script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = JSON.parse(fs.readFileSync(0, 'utf8'));

function element(tag) {
  const node = {
    tagName: tag.toUpperCase(), className: '', textContent: '', children: [],
    attributes: {}, dataset: {}, listeners: {}, onclick: null,
    append(...items) { this.children.push(...items); },
    appendChild(item) { this.children.push(item); return item; },
    replaceChildren(...items) { this.children = items; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    addEventListener(name, fn) { this.listeners[name] = fn; }
  };
  Object.defineProperty(node, 'childElementCount', {
    get() { return this.children.length; }
  });
  Object.defineProperty(node, 'innerHTML', {
    set() { throw new Error('hostile text must use textContent'); }
  });
  node.classList = {
    add(...names) {
      const values = new Set(String(node.className).split(' ').filter(Boolean));
      names.forEach(name => values.add(name));
      node.className = [...values].join(' ');
    },
    contains(name) { return String(node.className).split(' ').includes(name); }
  };
  return node;
}
function descendants(node) {
  return [node].concat(...node.children.flatMap(descendants));
}
function hasClass(node, name) {
  return String(node.className).split(' ').includes(name);
}
function texts(node) {
  return descendants(node).map(item => item.textContent).filter(Boolean);
}
function cardFor(root, id) {
  return descendants(root).find(node =>
    hasClass(node, 'flow-card') && texts(node).some(text => text.startsWith(id + ' — '))
  );
}
function activate(card) {
  const event = {preventDefault() {}};
  if (typeof card.onclick === 'function') return card.onclick(event);
  assert.equal(typeof card.listeners.click, 'function', 'card has click navigation');
  return card.listeners.click(event);
}

const context = {window: {}, document: {createElement: element}};
vm.runInNewContext(source.flow, context);
assert.equal(typeof context.window.renderTicketFlow, 'function');

const navigated = [];
const root = context.window.renderTicketFlow({
  ...source.fixture,
  onNavigate: id => navigated.push(id)
});
assert.ok(hasClass(root, 'ticket-flow'));

const rootId = source.fixture.lineage.root_id;
const childIds = source.fixture.lineage.items.slice(1).map(item => item.id);
const rootCard = cardFor(root, rootId);
const childCards = childIds.map(id => cardFor(root, id));
assert.ok(rootCard && childCards.every(Boolean), 'each card visibly prefixes its raw ID');
assert.ok(descendants(root).some(node => hasClass(node, 'flow-meta')));

const rootNode = descendants(root).find(node =>
  hasClass(node, 'flow-node') && node.children.includes(rootCard)
);
assert.ok(rootNode, 'root card has a flow-node wrapper');
const childRow = rootNode.children.find(node => hasClass(node, 'flow-children'));
assert.ok(childRow, 'root has a direct flow-children row');
assert.equal(childRow.childElementCount, 3, 'MEDIUM visibly flows to three LOW children');
assert.deepEqual(childRow.children.map(node => {
  const card = node.children.find(child => hasClass(child, 'flow-card'));
  return childIds.find(id => texts(card).some(text => text.startsWith(id + ' — ')));
}), childIds, 'parent_id topology preserves lineage item order');

const current = descendants(root).filter(node => hasClass(node, 'is-current'));
assert.equal(current.length, 1);
assert.equal(current[0], childCards[0]);
assert.ok(texts(current[0]).some(text => text.trim() === 'You are here'));

const rendered = texts(root).join(' | ');
assert.match(rendered, /bob-2/);
assert.match(rendered, /bob-3/);
assert.match(rendered, /Unknown/);
assert.match(rendered, /Render <unsafe>& flow/);
assert.ok(!rendered.includes('bob-4'), 'event actor is not inferred as assignment');
activate(childCards[1]);
assert.deepEqual(navigated, [childIds[1]]);

const cyclic = {
  root_id: 'a',
  items: [
    {id: 'a', parent_id: 'b', title: 'A', status: 'open'},
    {id: 'b', parent_id: 'a', title: 'B', status: 'open'}
  ]
};
const bounded = context.window.renderTicketFlow({
  lineage: cyclic, currentId: 'a', detailsById: {}, onNavigate() {}
});
assert.ok(descendants(bounded).length <= 12, 'cyclic lineage does not recurse indefinitely');
'''
    result = subprocess.run(
        [node, "-e", script],
        input=payload,
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
