"""Offline synthetic regressions; do not import app initialization."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import types
import uuid
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/dashboard_live_v1.json'

@pytest.fixture
def modules():
    name = '_dashboard_test_' + uuid.uuid4().hex
    package = types.ModuleType(name)
    package.__path__ = [str(ROOT / 'app')]
    sys.modules[name] = package
    loaded = []
    try:
        for short in ('dashboard_session_source', 'dashboard_live'):
            key = name + '.' + short
            spec = importlib.util.spec_from_file_location(key, ROOT / 'app' / (short + '.py'))
            module = importlib.util.module_from_spec(spec)
            sys.modules[key] = module
            spec.loader.exec_module(module)
            loaded.append(module)
        yield loaded
    finally:
        for key in list(sys.modules):
            if key == name or key.startswith(name + '.'):
                del sys.modules[key]

@pytest.fixture
def canonical():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))

def test_complete_envelope(modules, canonical, tmp_path):
    reader, builder = modules
    selected = tmp_path / canonical['session']['id']
    selected.mkdir()
    (selected / 'plan.json').write_text(json.dumps(canonical['session']['plan']), encoding='utf-8')
    session = reader.read_session_metadata(selected.name, base_dir=tmp_path)
    items = [{**{k: a[k] for k in ('id', 'resting', 'event_at', 'live_confirmed',
              'interrupted_occupied_lease')}, 'state': a['reported_activity']} for a in canonical['agents']]
    actual = builder.build_snapshot(roster={'available': True, 'items': items},
                                   session=session, observed_at=canonical['observed_at'])
    assert actual == canonical  # Required on supported Windows too; never capability-skip.

def test_reader_validation_and_bound(modules, tmp_path):
    reader, _ = modules
    for unsafe in ('', '..', '../outside', '/absolute', 'a/b', 'a\\b'):
        with pytest.raises(ValueError):
            reader.read_session_metadata(unsafe, base_dir=tmp_path)
    for size in (True, 0, -1, 65537, 10**100):
        with pytest.raises(ValueError):
            reader.read_session_metadata('safe', base_dir=tmp_path, max_bytes=size)
    selected = tmp_path / 'safe'
    selected.mkdir()
    (selected / 'plan.json').write_bytes(b' ' * 65)
    result = reader.read_session_metadata('safe', base_dir=tmp_path, max_bytes=64)
    assert result['sources']['plan']['status'] == 'invalid'
    assert result['sources']['summary']['status'] == 'missing'
    assert result['plan'] is None

@pytest.mark.parametrize('directory', [False, True])
def test_symlink_confinement(modules, tmp_path, directory):
    reader, _ = modules
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'plan.json').write_text('{"agents":[]}', encoding='utf-8')
    selected = tmp_path / 'safe'
    if not directory:
        selected.mkdir()
    target, link = (outside, selected) if directory else (outside / 'plan.json', selected / 'plan.json')
    try:
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip('Symlink privileges unavailable; affected confinement check unverified: ' + str(exc))
    result = reader.read_session_metadata('safe', base_dir=tmp_path)
    assert result['sources']['plan']['status'] == 'invalid'
    assert result['plan'] is None

def test_metadata_allowlist_and_event_time(modules, tmp_path):
    reader, _ = modules
    selected = tmp_path / 'safe'
    selected.mkdir()
    plan = {'agents': [{'name': 'a', 'level': 'LOW', 'parent': None, 'prompt': 'SECRET'}], 'directive': 'SECRET'}
    (selected / 'plan.json').write_text(json.dumps(plan), encoding='utf-8')
    events = [{'event': 'pressure_stop', 'at_utc': '2026-10-17T16:00:00Z'}, {'event': 'pressure_stop_extra'}]
    (selected / 'board.jsonl').write_text('\n'.join(map(json.dumps, events)) + '\n', encoding='utf-8')
    (selected / 'summary.json').write_text('{"unknown_usage":0,"requests":2,"message":"SECRET","health":"SECRET","api_key":"SECRET"}', encoding='utf-8')
    result = reader.read_session_metadata('safe', base_dir=tmp_path)
    assert result['plan'] == {'agents': [{'name': 'a', 'level': 'LOW', 'parent': None}]}
    assert result['board'] == {'event_count': 2, 'last_event_at': None, 'pressure_stop_count': 1}
    assert result['sources']['board']['event_at'] is None
    assert result['summary']['unknown_usage'] is None
    assert result['summary']['requests'] == 2
    assert 'SECRET' not in json.dumps(result)

def test_malformed_status_and_unknowns(modules, canonical):
    _, builder = modules
    session = {'id': 'x', 'sources': {k: {'status': [], 'event_at': None}
               for k in ('plan', 'board', 'summary')}, 'plan': None, 'board': None, 'summary': None}
    result = builder.build_snapshot(session=session, observed_at=canonical['observed_at'])
    assert all(result['sources'][k]['status'] == 'invalid' for k in session['sources'])
    result = builder.build_snapshot(roster={'available': True, 'items': [{'id': 'a', 'state': 'active'}]},
                                   mode={'mode': 'light', 'agents': 10**1000, 'automated_writes': False},
                                   observed_at=canonical['observed_at'])
    assert result['agents'][0]['live_confirmed'] is None
    assert result['agents'][0]['interrupted_occupied_lease'] is None
    json.dumps(result, allow_nan=False)

NODE = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const good=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),code=fs.readFileSync(process.argv[1],'utf8');
function harness(endpoint,boot=false){
 const calls=[],pending=[],timers=new Map(),listeners=new Map();let seq=0;
 function element(){let text='',children=[];return {dataset:{},addEventListener(){},removeEventListener(){},setAttribute(){},
  querySelector(){return null},querySelectorAll(){return []},appendChild(c){children.push(c);return c},
  get textContent(){return text+children.map(c=>c.textContent).join('')},set textContent(v){text=String(v);children=[]},
  set innerHTML(v){throw Error('unsafe innerHTML write')},get innerHTML(){throw Error('unexpected innerHTML read')}}}
 const slots={live:element(),flow:element(),ops:element()},status=element(),root=element(),pause=element(),resume=element();
 root.querySelector=s=>s.includes('data-dashboard-status')?status:s.includes('data-dashboard-pause')?pause:
  s.includes('data-dashboard-resume')?resume:Object.keys(slots).map(k=>s.includes('"'+k+'"')?slots[k]:null).find(Boolean)||null;
 const document={hidden:false,location:{href:'https://example.test/',origin:'https://example.test'},
  addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:(name,fn)=>{if(listeners.get(name)===fn)listeners.delete(name)},
  createElement:element,getElementById:()=>boot?root:null,activeElement:pause};
 const context={window:{},document,URL,console};vm.createContext(context);
 const options={document,headers:{'X-Test-Identity':'authorized'},now:()=>123,
  fetch:(url,opts)=>{calls.push({url,opts});return new Promise(resolve=>pending.push(resolve))},
  setTimeout:(fn,delay)=>{const id=++seq;timers.set(id,{fn,delay});return id},clearTimeout:id=>timers.delete(id)};
 if(endpoint!==undefined)options.endpoint=endpoint;
 if(boot)context.window.dashboardConfig=options;
 vm.runInContext(code,context);
 const api=boot?context.window.dashboard:context.window.createDashboard(root,options);
 return {api,calls,timers,slots,status,document,listeners,pause,reply(value=good,status=200){assert(pending.length);pending.shift()({ok:status===200,status,json:async()=>value})},
  tick(){assert.equal(timers.size,1);const [id,t]=timers.entries().next().value;timers.delete(id);t.fn();return t.delay}};
}
(async()=>{
 const settle=async()=>{for(let i=0;i<16;i++)await Promise.resolve()},plain=x=>JSON.parse(JSON.stringify(x));
 for(const endpoint of [undefined,'','https://other.test/live']){const h=harness(endpoint);await settle();assert.equal(h.calls.length,0);h.api.destroy()}
 const h=harness('/api/dashboard/live');h.api.resume();h.api.resume();assert.equal(h.calls.length,1);assert.equal(h.timers.size,0);
 h.reply();await settle();assert.equal(h.calls[0].opts.headers['X-Test-Identity'],'authorized');
 assert.equal(h.calls[0].opts.headers['X-Demo-User'],undefined);assert.equal(h.calls[0].opts.redirect,'error');assert.equal(h.calls[0].opts.credentials,'same-origin');
 assert(h.slots.live.textContent.includes(good.agents[0].id));assert(h.slots.live.textContent.includes(good.agents[0].reported_activity));
 assert(h.slots.live.textContent.includes('Asked to rest: yes'));assert(!h.status.textContent.includes('Renderer unavailable'));
 const seen=[];h.api.register('live',(_,data,state)=>seen.push({data,state}));assert.deepStrictEqual(plain(seen.at(-1).data),good);
 assert.equal(h.tick(),2500);h.api.resume();assert.equal(h.calls.length,2);
 const bad=plain(good);bad.session=[];h.reply(bad);await settle();
 assert.deepStrictEqual(plain(seen.at(-1).data),good);assert.equal(seen.at(-1).state.stale,true);assert(seen.at(-1).state.error);
 assert([...h.timers.values()].every(t=>t.delay>=2500&&t.delay<=60000));
 h.document.hidden=true;h.tick();h.reply();await settle();assert([...h.timers.values()].every(t=>t.delay>=10000));
 h.api.pause();assert.equal(h.timers.size,0);assert.equal(seen.at(-1).state.paused,true);h.api.destroy();
 // The actual deferred page script initializes the same controller and never guesses configuration.
 for(const endpoint of [undefined,'/api/dashboard/live']){const b=harness(endpoint,true);
  assert(b.api);assert.equal(b.calls.length,endpoint?1:0);b.api.destroy()}
 const v=harness('/api/dashboard/live');v.reply();await settle();
 assert.equal(v.document.activeElement,v.pause);
 v.document.hidden=true;v.listeners.get('visibilitychange')();
 assert.equal([...v.timers.values()][0].delay,10000);assert.equal(v.calls.length,1);
 v.document.hidden=false;v.listeners.get('visibilitychange')();
 assert.equal([...v.timers.values()][0].delay,2500);
 v.tick();v.document.hidden=true;v.listeners.get('visibilitychange')();
 assert.equal(v.timers.size,0);assert.equal(v.calls.length,2);
 v.api.pause();v.reply();await settle();assert.equal(v.timers.size,0);
 assert(v.status.textContent.includes('Paused'));assert.equal(v.document.activeElement,v.pause);
 v.api.resume();v.api.destroy();const retained=v.status.textContent;v.reply();await settle();
 assert.equal(v.status.textContent,retained);assert.equal(v.timers.size,0);assert.equal(v.listeners.size,0);
 const f=harness('/api/dashboard/live');
 for(const delay of [5000,10000,20000,40000,60000,60000]){
  f.reply(null,500);await settle();assert.equal(f.tick(),delay);
 }
 f.reply();await settle();assert.equal(f.tick(),2500);f.api.destroy();
 for(const status of [401,403]){const a=harness('/api/dashboard/live');const states=[];a.api.register('live',(_,d,s)=>states.push(s));
  a.reply(null,status);await settle();assert.equal(states.at(-1).authentication,true);assert.equal(a.timers.size,0);
  a.api.resume();await settle();assert.equal(a.calls.length,1);a.api.destroy()}
})().catch(e=>{console.error(e);process.exitCode=1});
'''

def test_browser_vm():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable; browser checks unverified, not passed')
    result = subprocess.run([node, '-e', NODE, str(ROOT / 'app/static/dashboard-live.js'),
                             str(FIXTURE)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
