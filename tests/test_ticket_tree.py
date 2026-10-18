import json
from pathlib import Path
import shutil
import subprocess

import pytest


def test_ticket_tree_assembly_routing_readonly_and_renderer():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the ticket-tree VM contract check')
    payload = json.dumps({
        'app': Path('app/static/app.js').read_text(encoding='utf-8'),
        'flow': Path('app/static/flow.js').read_text(encoding='utf-8'),
    })
    script = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
function element(tag) {
  const n = {tagName: tag.toUpperCase(), children: [], textContent: '', className: '',
    attributes: {}, listeners: {}, hidden: true,
    append(...items) { this.children.push(...items); },
    appendChild(item) { this.children.push(item); return item; },
    replaceChildren(...items) { this.children = items; },
    setAttribute(k, v) { this.attributes[k] = String(v); },
    addEventListener(k, f) { this.listeners[k] = f; }};
  Object.defineProperty(n, 'childNodes', {get() { return this.children; }});
  Object.defineProperty(n, 'childElementCount', {get() { return this.children.length; }});
  Object.defineProperty(n, 'innerHTML', {set() { throw Error('Use textContent'); }});
  n.classList = {add(s) { n.className += ' ' + s; }};
  return n;
}
const nodes = new Map();
const document = {createElement: element, getElementById(id) {
  if (!nodes.has(id)) nodes.set(id, element('section'));
  return nodes.get(id);
}};
const context = vm.createContext({window: {}, document, URLSearchParams,
  localStorage: {getItem() { return null; }}, clearTimeout() {},
  history: {replaceState(...args) { context.lastHash = args[2]; }}});
vm.runInContext(source.flow, context);
// Exclude DOM event wiring and startup; evaluate the actual application functions.
const boundary = source.app.indexOf("$('gremlins-example').onclick");
assert.ok(boundary > 0);
vm.runInContext(source.app.slice(0, boundary), context);
function evaluate(code) { return vm.runInContext(code, context); }
const all = n => [n, ...n.children.flatMap(all)];
const text = n => all(n).map(x => x.textContent).join(' | ');
(async () => {
  evaluate(`globalThis.assembly = assembleTicketTree({root_id:'r', items:[
    {id:'r',parent_id:null,title:'Root',status:'open'},
    {id:'m',parent_id:'r',title:'Medium',status:'working'},
    {id:'l',parent_id:'m',title:'<unsafe>&',status:'open'}]}, 'l')`);
  assert.equal(context.assembly.lineage.items.length, 3);
  assert.equal(context.assembly.warnings.length, 0);
  assert.match(evaluate(`assembleTicketTree({root_id:'a',items:[{id:'a',parent_id:'b'},{id:'b',parent_id:'a'}]},'a').warnings.join(' ')`), /Cycle detected/);
  assert.match(evaluate(`assembleTicketTree({root_id:'absent',items:[{id:'x',parent_id:'missing'}]},'gone').warnings.join(' ')`), /Missing root.*Missing requested.*Missing parent/);
  assert.match(evaluate(`assembleTicketTree({items:[null,{id:'x'},{id:'x'}]},'x').warnings.join(' ')`), /Missing node ID.*Duplicate node/);
  assert.equal(evaluate(`evidencePackageCount({items:[{path:'task.json'},{path:'packages/4-response/a'},{path:'packages/4-response/b'},{path:'packages/7-support/a'}]})`), 2);
  assert.equal(evaluate(`evidencePackageCount({items:[]})`), 0);
  assert.equal(evaluate(`evidencePackageCount({})`), null);
  assert.equal(evaluate(`ticketHash('#tree=a%2Fb').id`), 'a/b');
  assert.equal(evaluate(`ticketHash('#task=x').kind`), 'task');
  assert.equal(evaluate(`ticketHash('#agents')`), null);
  // Startup and subsequent hash changes both use the tested dispatcher.
  assert.ok(source.app.includes("const linkedTree = link.get('tree')"));
  assert.ok(source.app.includes('if (linkedTree) await showTree(linkedTree)'));
  assert.ok(source.app.includes("window.addEventListener('hashchange'"));
  assert.ok(source.app.includes('openTicketHash(ticketHash(location.hash))'));
  assert.ok(source.app.includes("treeLink.href = '#tree=' + encodeURIComponent(id)"));
  const requests = [];
  context.stubApi = async (...args) => {
    requests.push(args);
    assert.equal(args.length, 1, 'tree supplies no POST body');
    const path = args[0];
    if (path.endsWith('/lineage')) return context.assembly.lineage;
    if (path.endsWith('/artifacts')) return {items:[{path:'packages/1-response/a'},{path:'packages/1-response/b'}]};
    return {complexity: path.endsWith('/r') ? 'HIGH' : path.endsWith('/m') ? 'MEDIUM' : 'LOW', status:'open'};
  };
  evaluate('api = stubApi');
  await evaluate(`openTicketHash(ticketHash('#tree=l'))`);
  assert.equal(context.lastHash, '#tree=l');
  assert.equal(requests.length, 7);
  const page = nodes.get('detail');
  assert.match(text(page), /<unsafe>&/);
  assert.match(text(page), /Complexity: HIGH/);
  assert.match(text(page), /Evidence packages: 1/);
  const cards = all(page).filter(n => n.className.includes('flow-card'));
  assert.equal(cards.length, 3);
  assert.ok(cards.every(n => n.tagName === 'A' && n.href.startsWith('#task=')));
  const rootNode = all(page).find(n => n.className === 'flow-node' && n.children.includes(cards[0]));
  assert.ok(rootNode.children.some(n => n.className === 'flow-children'));
  context.stubApi = async path => {
    if (path.endsWith('/lineage')) return {root_id:'a',items:[{id:'a',parent_id:'b',title:'A'},{id:'b',parent_id:'a',title:'B'},{id:'x',parent_id:'absent',title:'X'}]};
    throw Error('fixture unavailable');
  };
  evaluate('api = stubApi');
  await evaluate(`openTicketHash(ticketHash('#tree=a'))`);
  assert.match(text(page), /Cycle detected/);
  assert.match(text(page), /Missing parent node/);
  assert.match(text(page), /Task details unavailable/);
  assert.match(text(page), /Evidence packages: Unknown/);
  context.stubApi = async () => { throw Error('lineage unavailable'); };
  evaluate('api = stubApi');
  await evaluate(`showTree('a')`);
  assert.match(text(page), /Hierarchy unavailable: lineage unavailable/);
  // A late tree response cannot replace another navigation's content.
  context.stubApi = () => new Promise(resolve => { context.release = resolve; });
  evaluate('api = stubApi');
  const pending = evaluate(`showTree('a')`);
  evaluate('treeEpoch++');
  page.replaceChildren(element('p'));
  page.children[0].textContent = 'New view';
  context.release({root_id:'a',items:[]});
  await pending;
  assert.equal(text(page).includes('New view'), true);
  const visited = [];
  context.navigateTask = id => visited.push(id);
  evaluate('show = navigateTask');
  await evaluate(`openTicketHash(ticketHash('#task=l'))`);
  assert.deepEqual(visited, ['l']);
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
    result = subprocess.run([node, '-e', script], input=payload, text=True,
                            capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
