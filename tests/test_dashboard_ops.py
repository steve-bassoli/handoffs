"""Proposed R2 contract checks; no live resources or chargeable operations."""
import copy
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
from types import SimpleNamespace
import pytest
from app.dashboard_ops import normalize_ops
from app.dashboard_ops_source import read_ledger, read_git

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'tests/fixtures/dashboard_ops_v1.json').read_text())


def merge(base, patch):
    out = copy.deepcopy(base)
    for key, value in patch.items():
        out[key] = merge(out.get(key, {}), value) if isinstance(value, dict) else copy.deepcopy(value)
    return out


def materialize():
    previous, cases = {}, []
    for case in FIXTURE['cases']:
        raw = merge(FIXTURE['base'], case['raw'])
        old = previous.get(case['previous_from'])
        snapshot = normalize_ops(raw, old)
        previous[case['id']] = snapshot
        cases.append((case, raw, old, snapshot))
    return cases


def test_fixture_cases_and_purity():
    for case, raw, previous, snapshot in materialize():
        original = copy.deepcopy((raw, previous))
        assert normalize_ops(raw, previous) == snapshot
        assert (raw, previous) == original
        expected, ledger = case['expected'], snapshot['sources']['ledger']
        for key, value in expected.get('ledger', {}).items():
            assert ledger['data'][key] == value, case['id']
        for key in ('status', 'observed_at', 'last_attempt_at', 'data'):
            if key in expected:
                assert ledger[key] == expected[key], case['id']
        for field, source, key in [('gold', 'wallet', 'gold'), ('codex_amount', 'codex', 'amount'), ('usage_upper', 'session_usage', 'reported_upper_cents'), ('commit', 'git', 'commit')]:
            if field in expected:
                assert snapshot['sources'][source]['data'][key] == expected[field]


@pytest.mark.parametrize('value', [True, 1.5, -1, 9007199254740992])
def test_invalid_cents(value):
    raw = merge(FIXTURE['base'], {'sources': {'ledger': {'data': {'baseline_cents': value}}}})
    assert normalize_ops(raw)['sources']['ledger']['data']['guarded_headroom_cents'] is None


def test_no_invented_proof_or_missing_sources():
    snapshot = normalize_ops({'tests': {'status': 'passed'}, 'policy': {'protected_cents': 0}})
    assert snapshot['version'] == 1
    assert snapshot['tests'] == {'status': 'not_recorded', 'provenance': None}
    assert snapshot['policy'] == {'protected_cents': 100, 'sponsor_guard_cents': 199800, 'tests_gated_before_commit': True}
    assert set(snapshot['sources']) == {'ledger', 'session_usage', 'wallet', 'codex', 'leases', 'git'}
    assert all(s['status'] == 'unavailable' and s['data'] is None for s in snapshot['sources'].values())


def test_ledger_readonly_errors_and_missing(tmp_path):
    missing = tmp_path / 'missing.sqlite'
    assert read_ledger(missing, adapter=lambda query: {})['status'] == 'unavailable'
    assert not missing.exists()
    path = tmp_path / 'ledger.sqlite'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE probe(value INTEGER)')
        conn.execute('INSERT INTO probe VALUES(7)')
    ledger = FIXTURE['base']['sources']['ledger']['data']
    def adapter(query):
        assert len(list(query('SELECT value FROM probe LIMIT ?', (1,)))) == 1
        for sql in ('DELETE FROM probe', 'PRAGMA user_version=7', 'WITH x AS (SELECT 1) DELETE FROM probe'):
            with pytest.raises(Exception):
                query(sql)
        return copy.deepcopy(ledger)
    # A swallowed forbidden-query failure poisons the whole read, despite valid returned data.
    assert read_ledger(path, adapter=adapter)['status'] == 'unavailable'
    def good(query):
        assert len(list(query('SELECT value FROM probe LIMIT 1'))) == 1
        return copy.deepcopy(ledger)
    assert read_ledger(path, adapter=good)['status'] == 'ok'
    def swallowed(query):
        try:
            query('SELECT value FROM nonexistent LIMIT 1')
        except Exception:
            pass
        return copy.deepcopy(ledger)
    assert read_ledger(path, adapter=swallowed)['status'] == 'unavailable'
    assert read_ledger(path)['status'] == 'unavailable'
    assert read_ledger(path, adapter=lambda q: dict(ledger, reservations_complete=False))['status'] == 'unavailable'
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT value FROM probe').fetchall() == [(7,)]


def test_git_fixed_invocation_and_failures(tmp_path):
    calls = []
    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        assert argv == ['git', '--no-pager', 'log', '-1', '--format=%H%x09%cI', '--no-decorate']
        assert kwargs['shell'] is False and kwargs['timeout'] == 2
        return SimpleNamespace(returncode=0, stdout='a' * 40 + '\t2026-01-01T00:00:00+00:00\n', stderr='')
    result = read_git(tmp_path, runner=runner)
    assert result['status'] == 'ok' and result['data']['commit']['hash'] == 'a' * 40
    assert len(calls) == 1
    for output in ('', 'bad\ttime', 'a' * 40 + '\t2026-01-01T00:00:00Z\nextra'):
        assert read_git(tmp_path, runner=lambda *a, **k: SimpleNamespace(returncode=0, stdout=output, stderr=''))['status'] == 'unavailable'
    assert read_git(tmp_path, runner=lambda *a, **k: SimpleNamespace(returncode=1, stdout='', stderr='private detail'))['data'] is None


def test_renderer_node_vm():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable: renderer behavior not verified')
    snapshot = materialize()[8][3]
    snapshot['sources']['ledger']['data']['provenance'] = '<img src=x onerror=evil()>'
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const input=JSON.parse(fs.readFileSync(0,'utf8')), code=fs.readFileSync(process.argv[1],'utf8');
class E { constructor(tag){this.tagName=tag;this.children=[];this._text='';this.style={};this.dataset={};}
 set innerHTML(v){throw Error('innerHTML forbidden');} set textContent(v){this._text=String(v);this.children=[];}
 get textContent(){return this._text+this.children.map(x=>x.textContent||'').join(' ');}
 appendChild(v){this.children.push(v);return v;} append(...v){this.children.push(...v);}
 setAttribute(k,v){this[k]=String(v);} }
const document={createElement:t=>new E(t),createTextNode:t=>({textContent:String(t)})};
const context={window:{},document};vm.createContext(context);vm.runInContext(code,context);
const helpers={element:(t,text='',cls='')=>{const e=new E(t);e.textContent=text;e.className=cls;return e;}};
const render=s=>context.window.renderDashboardOps(s,helpers).textContent;
const stale=render(input);assert(/stale/i.test(stale));assert(stale.includes('<img src=x onerror=evil()>'));
assert(/not recorded/i.test(stale));assert(/policy/i.test(stale));
input.sources.ledger={status:'unavailable',source_id:null,observed_at:null,last_attempt_at:null,error_code:null,data:null};
assert(/unknown|unavailable/i.test(render(input)));
'''
    result = subprocess.run([node, '-e', script, str(ROOT / 'app/static/dashboard-ops.js')], input=json.dumps(snapshot), text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
