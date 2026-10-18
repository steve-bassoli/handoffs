import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine

from app import digest
from app.services import RuleError


@pytest.fixture
def source():
    engine = create_engine('sqlite://')
    with engine.begin() as c:
        c.exec_driver_sql('CREATE TABLE signoffs(id TEXT, action TEXT, summary TEXT, payload_sha256 TEXT, requested_by TEXT, requested_principal TEXT, decision TEXT, created_at INTEGER)')
        c.exec_driver_sql('CREATE TABLE tasks(id TEXT, title TEXT, creator TEXT, parent_id TEXT)')
        c.exec_driver_sql('CREATE TABLE events(seq INTEGER PRIMARY KEY, task_id TEXT, kind TEXT, actor TEXT, state TEXT, data TEXT)')
        c.exec_driver_sql('CREATE TABLE recommendations(id TEXT, item_kind TEXT, item_id TEXT, item_revision TEXT, superseded_by TEXT)')
        c.exec_driver_sql('INSERT INTO signoffs VALUES (?,?,?,?,?,?,?,?)',
                          ('s', 'publish', 'Publish draft', 'a' * 64, 'bot', 'agent', None, 1))
        for task_id in ('v', 'c'):
            c.exec_driver_sql('INSERT INTO tasks VALUES (?,?,?,NULL)', (task_id, task_id, 'steve'))
        c.exec_driver_sql('INSERT INTO events VALUES (1,?,?,?,?,?)',
                          ('v', 'intake_screened', 'bot', 'blocked', json.dumps({'verdict': 'veto', 'reason': 'Review needed', 'text_sha256': 'b' * 64, 'principal': 'agent'})))
        c.exec_driver_sql('INSERT INTO events VALUES (2,?,?,?,?,?)',
                          ('c', 'taken', 'steve', 'working', json.dumps({'complexity': 'LOW', 'principal': 'human'})))
    yield SimpleNamespace(db=SimpleNamespace(engine=engine), demo_identity='allow')
    engine.dispose()


WHO = {'user_id': 'steve', 'principal': 'demo-header', 'principal_id': 'demo-header:steve'}


def test_sources_counts_and_unknown_policy(source):
    result = digest.build_digest(source, WHO)
    assert {item['kind'] for item in result['items']} == {'signoff', 'intake_veto', 'human_close'}
    assert result['counts']['total'] == len(result['items']) == 3
    assert result['counts']['by_kind'] == {'signoff': 1, 'intake_veto': 1, 'human_close': 1, 'policy_decision': None}
    assert result['coverage']['policy_decision'] == 'unsupported'
    assert result['complete'] is False
    assert len({(i['kind'], i['id']) for i in result['items']}) == 3
    for item in result['items']:
        assert item['recommendation'] == {'status': 'unavailable'}
        assert len(item['revision']) == 64
        assert item['effect'] == digest.classify(item['action'])
        assert 'requested_principal' in item['provenance']


def test_override_and_settlement_remove_items(source):
    with source.db.engine.begin() as c:
        c.exec_driver_sql('INSERT INTO events VALUES (3,?,?,?,?,?)',
                          ('v', 'intake_overridden', 'steve', 'open', json.dumps({'principal': 'human', 'text_sha256': 'b' * 64})))
        c.exec_driver_sql('INSERT INTO events VALUES (4,?,?,?,?,?)',
                          ('c', 'paid', 'steve', 'settled', '{}'))
    result = digest.build_digest(source, WHO)
    assert [(i['kind'], i['id']) for i in result['items']] == [('signoff', 's')]
    assert result['counts']['total'] == 1


def test_wrong_hash_override_does_not_clear_veto(source):
    with source.db.engine.begin() as c:
        c.exec_driver_sql('INSERT INTO events VALUES (3,?,?,?,?,?)',
                          ('v', 'intake_overridden', 'steve', 'open', json.dumps({'principal': 'human', 'text_sha256': 'd' * 64})))
    assert any(i['kind'] == 'intake_veto' for i in digest.build_digest(source, WHO)['items'])


def test_medium_requires_no_children():
    task = {'claimant': 'steve', 'status': 'blocked', 'complexity': 'MEDIUM'}
    assert digest._closable(task, [])
    assert not digest._closable(task, ['child'])
    assert not digest._closable({**task, 'claimant': None}, [])


def test_demo_gate(source):
    source.demo_identity = 'refuse'
    with pytest.raises(RuleError):
        digest.build_digest(source, WHO)
