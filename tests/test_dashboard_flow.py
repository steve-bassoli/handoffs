"""Proposed v1-r2 contract checks; no server, database or network needed."""
import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from app.dashboard_flow import build_dashboard_flow

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/dashboard_flow_v1.json'
ENVELOPE = set('version observed_at current_id tickets activity coverage issues'.split())
TICKET = set('id parent_id parent_known title status assigned_agent assignment_source detail_available'.split())
ACTIVITY = set('ticket_id kind event_time source_index'.split())
COVERAGE = set('tickets_supplied tickets_shown activity_eligible activity_shown tickets_truncated activity_truncated details_missing'.split())
ISSUES = set('duplicate_id invalid_id orphan_parent cycle missing_detail tickets_truncated activity_truncated invalid_parent conflicting_evidence conflicting_assignment invalid_events'.split())

@pytest.fixture
def source():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def build(source, **kwargs):
    return build_dashboard_flow(source['lineage'], source['details'], **kwargs)


def test_schema_authority_privacy_and_nonmutation(source):
    before = copy.deepcopy(source)
    m = build(source, observed_at='observation-only', current_id='child')
    assert source == before and set(m) == ENVELOPE and m['version'] == 1
    assert m['observed_at'] == 'observation-only' and m['current_id'] == 'child'
    assert set(m['coverage']) == COVERAGE
    assert all(set(t) == TICKET for t in m['tickets'])
    assert all(set(a) == ACTIVITY for a in m['activity'])
    assert len(m['issues']) == len(set(m['issues'])) and set(m['issues']) <= ISSUES
    t = {t['id']: t for t in m['tickets']}
    assert t['child']['assigned_agent'] == 'bob-3'
    assert t['child']['assignment_source'] == 'followup_confirmed'
    assert t['child']['parent_id'] == 'root' and t['child']['status'] == 'open'
    assert t['unconfirmed']['assigned_agent'] is None
    assert t['unconfirmed']['assignment_source'] is None
    assert t['root']['parent_known'] is True and t['root']['parent_id'] is None
    assert t['unknown']['parent_known'] is False and t['unknown']['parent_id'] is None
    assert t['invalid-parent']['parent_known'] is False
    assert t['invalid-parent']['title'] == t['invalid-parent']['status'] == 'Unknown'
    assert t['orphan']['parent_id'] == 'absent' and not t['orphan']['detail_available']
    assert t['cycle-a']['parent_id'] == 'cycle-b' and t['cycle-b']['parent_id'] == 'cycle-a'
    assert {'conflicting_assignment', 'conflicting_evidence', 'duplicate_id', 'invalid_id', 'cycle', 'orphan_parent', 'missing_detail', 'invalid_parent', 'invalid_events'} <= set(m['issues'])
    a = [a for a in m['activity'] if a['ticket_id'] == 'child']
    assert [x['source_index'] for x in a] == [0, 1, 2, 3]
    assert [x['event_time'] for x in a] == [None, '2025-01-02T00:00:00Z', 'earlier-but-source-later', None]
    assert 'PRIVATE_' not in json.dumps(m) and 'not-authority' not in json.dumps(m)
    assert m['coverage'] == dict(tickets_supplied=8, tickets_shown=8, activity_eligible=6, activity_shown=6, tickets_truncated=False, activity_truncated=False, details_missing=1)
    assert build(source)['observed_at'] is None and build(source)['current_id'] is None


def test_caps_hidden_parent_and_verbatim_values(source):
    m = build(source, max_tickets=2, max_activity=1)
    assert len(m['tickets']) == 2 and len(m['activity']) == 1
    assert m['coverage']['tickets_truncated'] and m['coverage']['activity_truncated']
    assert m['coverage']['activity_eligible'] == 4
    assert {'tickets_truncated', 'activity_truncated'} <= set(m['issues'])
    assert build(source, max_tickets=-1)['tickets'] == []
    assert build(source, max_activity=0)['activity'] == []
    assert build(source, max_tickets=999) == build(source, max_tickets=100)
    s = {'items': [{'id': ' child ', 'parent_id': 'parent', 'title': 'x' * 300, 'status': ' status '}, {'id': 'parent', 'parent_id': None}]}
    m = build_dashboard_flow(s, {}, max_tickets=1)
    t = m['tickets'][0]
    assert t['id'] == ' child ' and t['parent_id'] == 'parent' and t['parent_known']
    assert t['status'] == ' status ' and len(t['title']) <= 240
    assert m['coverage']['tickets_supplied'] == 2 and m['coverage']['tickets_shown'] == 1

@pytest.mark.parametrize('value', [True, 1.5, '1', None])
def test_invalid_cap_types(source, value):
    for key in ('max_tickets', 'max_activity'):
        with pytest.raises(TypeError):
            build(source, **{key: value})

@pytest.mark.parametrize('lineage,details', [(None, {}), ({'items': 'bad'}, {}), ({'items': []}, [])])
def test_invalid_envelopes(lineage, details):
    with pytest.raises((TypeError, ValueError)):
        build_dashboard_flow(lineage, details)


def test_renderer_vm(source):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable: renderer VM checks NOT executed')
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
let doc;
class E {
 constructor(tag){this.tagName=tag.toUpperCase();this.nodeType=1;this.children=[];this.attrs={};this.listeners={};this._text='';this.parentNode=null;this.ownerDocument=doc;}
 set textContent(v){this.children.forEach(n=>n.parentNode=null);this.children=[];this._text=String(v??'');} get textContent(){return this._text+this.children.map(x=>x.textContent).join(' ');}
 set innerHTML(v){throw Error('unsafe HTML');}
 appendChild(n){return this.insertBefore(n,null);}
 insertBefore(n,ref){if(ref!==null&&!this.children.includes(ref))throw Error('NotFoundError');if(n===ref)return n;if(n.parentNode)n.parentNode.removeChild(n);this.children.splice(ref===null?this.children.length:this.children.indexOf(ref),0,n);n.parentNode=this;return n;}
 append(...ns){ns.forEach(n=>this.appendChild(n));} removeChild(n){const i=this.children.indexOf(n);if(i<0)throw Error('NotFoundError');this.children.splice(i,1);n.parentNode=null;return n;}
 replaceChildren(...ns){this.children.forEach(n=>n.parentNode=null);this.children=[];this._text='';this.append(...ns);}
 remove(){if(this.parentNode)this.parentNode.removeChild(this);} get firstChild(){return this.children[0]||null;}
 setAttribute(k,v){this.attrs[k]=String(v);} getAttribute(k){return this.attrs[k]??null;} removeAttribute(k){delete this.attrs[k];}
 addEventListener(k,f){this.listeners[k]=f;} click(){if(this.listeners.click)this.listeners.click({target:this});if(this.onclick)this.onclick({target:this});}
 focus(){doc.activeElement=this;} contains(n){return this===n||this.children.some(c=>c.contains(n));}
 querySelectorAll(s){return walk(this).filter(n=>s==='button'?n.tagName==='BUTTON':s==='li'?n.tagName==='LI':false);}
}
function walk(n){return [n,...n.children.flatMap(walk)];}
doc={createElement:t=>new E(t),activeElement:null};
const p=new E('ul'),q=new E('ul'),a=new E('li'),b=new E('li'),c=new E('li');p.append(a,b,c);
a.setAttribute('aria-current','page');a.removeAttribute('aria-current');a.removeAttribute('absent');assert.equal(a.getAttribute('aria-current'),null);assert(!Object.hasOwn(a.attrs,'aria-current'));
assert.strictEqual(p.insertBefore(c,a),c);assert.deepStrictEqual(p.children,[c,a,b]);assert.strictEqual(p.insertBefore(c,null),c);assert.deepStrictEqual(p.children,[a,b,c]);
p.insertBefore(a,c);assert.deepStrictEqual(p.children,[b,a,c]);p.insertBefore(a,a);assert.deepStrictEqual(p.children,[b,a,c]);assert(p.children.every(n=>n.parentNode===p));
q.appendChild(a);assert.deepStrictEqual(p.children,[b,c]);assert.strictEqual(a.parentNode,q);assert.strictEqual(q.firstChild,a);assert.throws(()=>p.insertBefore(a,q));assert.strictEqual(a.parentNode,q);
q.textContent='cleared';assert.strictEqual(a.parentNode,null);assert.equal(q.children.length,0);
const sandbox={window:{},document:doc,console,Node:E,HTMLElement:E};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),sandbox);
const render=sandbox.window.renderDashboardFlow,m=JSON.parse(fs.readFileSync(0,'utf8'));
const calls=[],root=render(m,{onNavigate:(...a)=>calls.push(a),renderFlow:()=>{throw Error('adapter failed');}});
assert.equal(root.getAttribute('aria-live'),'off');assert.equal(typeof root.update,'function');
assert(root.textContent.includes('You are here'));assert(root.textContent.includes('<img src=x onerror=alert(1)>'));
for(const t of m.tickets)assert(root.textContent.includes(t.id));
const buttons=walk(root).filter(n=>n.tagName==='BUTTON');assert(buttons.length);
buttons[0].click();assert.equal(calls.length,1);assert.equal(calls[0].length,1);assert(m.tickets.some(t=>t.id===calls[0][0]));
buttons[0].focus();const oldFocus=doc.activeElement,oldNodes=walk(root);
assert.strictEqual(root.update(JSON.parse(JSON.stringify(m))),root);assert.strictEqual(doc.activeElement,oldFocus);assert(root.contains(oldFocus));
const activity=oldNodes.find(n=>n.tagName==='LI'&&n.textContent.includes('taken'));
assert(activity,'activity list item expected');assert(walk(root).includes(activity),'unchanged activity should retain nodes');
const controls=new Map(m.tickets.map((t,i)=>[t.id,buttons[i]])),activityList=walk(root).find(n=>n.tagName==='OL'),activityNodes=[...activityList.children];
const ticketList=buttons[0].parentNode.parentNode,rows=[...ticketList.children];
assert.equal(controls.get('child').getAttribute('aria-current'),'page');
const changed=JSON.parse(JSON.stringify(m));changed.current_id='root';assert.strictEqual(root.update(changed),root);
assert.equal(controls.get('child').getAttribute('aria-current'),null);assert(!controls.get('child').textContent.includes('You are here'));
assert.equal(controls.get('root').getAttribute('aria-current'),'page');assert(controls.get('root').textContent.includes('You are here'));
assert.equal(walk(root).filter(n=>n.getAttribute('aria-current')==='page').length,1);assert.strictEqual(doc.activeElement,oldFocus);assert.deepStrictEqual(ticketList.children,rows);
changed.tickets.reverse();root.update(changed);assert.deepStrictEqual(ticketList.children,[...rows].reverse());assert.equal(new Set(ticketList.children).size,rows.length);
changed.tickets.forEach((t,i)=>{const control=controls.get(t.id);assert.strictEqual(ticketList.children[i].firstChild,control);assert.strictEqual(control.parentNode.parentNode,ticketList);control.click();assert.deepStrictEqual(calls[calls.length-1],[t.id]);});
assert.strictEqual(doc.activeElement,oldFocus);assert(root.contains(oldFocus));assert.deepStrictEqual(activityList.children,activityNodes);assert(activityNodes.every(n=>n.parentNode===activityList));
assert.equal(controls.get('root').getAttribute('aria-current'),'page');assert.equal(controls.get('child').getAttribute('aria-current'),null);
assert.equal(walk(render(m)).filter(n=>n.tagName==='BUTTON').length,0);
assert(walk(render(m,{renderFlow:()=>({})})).some(n=>n.tagName==='LI'));
let used=0;const graph=doc.createElement('div');graph.textContent='graph';
const good=render(m,{renderFlow:(model,options)=>{used++;assert.equal(model.version,1);assert.equal(typeof options.element,'function');return graph;}});
assert.equal(used,1);assert(good.contains(graph));assert(walk(good).some(n=>n.tagName==='LI'&&n.textContent.includes('child')));
'''
    model = build(source, current_id='child', max_activity=3)
    result = subprocess.run([node, '-e', script, str(ROOT / 'app/static/dashboard-flow.js')], input=json.dumps(model), text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
