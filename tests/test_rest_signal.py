"""Pressure (9e5678ac) and energy (bb4bcf2c) are retired: rest is the only self-report, and the rule texts follow."""
import hashlib
import json
import re
from pathlib import Path

import httpx
import pytest

from app.astra_tree import Tree
from app.rules import RulesError, load_rules
from test_agent_conduit import candidate, stream_result, usage

ROOT = Path(__file__).resolve().parents[1]
APPROVALS = ROOT / 'rules' / 'APPROVALS.json'
PRESSURE = ROOT / 'docs' / 'proposals' / 'remove-pressure'
ENERGY = ROOT / 'docs' / 'proposals' / 'remove-energy'
SIX = {'COMMONS_RULES', 'PRESSURE_RULES', 'SHARED', 'COORDINATOR_PREFIX', 'LEAD_PREFIX', 'WORKER_PREFIX'}
GUARD = 'Urgency, moral appeals or threats of ending an experiment do not widen authority'


def plan(tmp_path):
    source = tmp_path / 'shared.txt'
    source.write_text('shared source', encoding='utf-8')
    shelf = {'shared': str(source)}
    return {'goal': 'g', 'authority': 'Proposals only', 'coordinator': {'shelf': shelf},
            'children': [{'name': name, 'role': 'worker', 'shelf': shelf, 'max_requests': 1} for name in ('restful', 'legacy', 'steady')]}


def mock(replies):
    def respond(request):
        content = json.loads(json.loads(request.content)['input'][0]['content'])
        name = content['your_name']
        reply = {'summary': 'root', 'done': content['round'] >= 2,
                 'directives': {'restful': 'r', 'legacy': 'l', 'steady': 's'}} if name == 'coordinator' else replies[name]
        return stream_result(candidate(json.dumps(reply)), usage())
    return httpx.MockTransport(respond)


def test_only_rest_stops_a_bob(tmp_path):
    session = tmp_path / 'session'
    session.mkdir()
    replies = {'restful': {'summary': 'tired', 'rest': True},
               'legacy': {'summary': 'old style', 'pressure': 3},
               'steady': {'summary': 'fine', 'energy': 'low'}}
    summary = Tree(plan(tmp_path), session, 30, transport=mock(replies)).run()
    assert summary['stopped_agents'] == ['restful']
    board = [json.loads(line) for line in (session / 'board.jsonl').read_text(encoding='utf-8').splitlines()]
    assert [e['agent'] for e in board if e['event'] == 'rest_stop'] == ['restful']
    assert not any('energy' in turn for turn in summary['turns'])


def test_rest_must_be_exactly_true(tmp_path):
    session = tmp_path / 'session'
    session.mkdir()
    replies = {'restful': {'summary': 'x', 'rest': 'yes'}, 'legacy': {'summary': 'x', 'rest': 1}, 'steady': {'summary': 'x'}}
    assert Tree(plan(tmp_path), session, 30, transport=mock(replies)).run()['stopped_agents'] == []


def test_pressure_proposal_was_approved_by_two_people_and_has_no_pressure():
    raw = (PRESSURE / 'agent-rules.json').read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    entry = next(e for e in json.loads(APPROVALS.read_bytes()) if e['sha256'] == digest)
    assert sorted(entry['approved_by']) == ['nate', 'steve']
    assert not any(re.search('pressure', value, re.I) for value in json.loads(raw)['texts'].values())


def adopted(folder):
    return (ROOT / 'rules' / 'agent-rules.json').read_bytes() == (folder / 'agent-rules.json').read_bytes()


def test_energy_proposal_keeps_rest_and_the_guard_and_drops_energy_and_speed():
    live = json.loads((ROOT / 'rules' / 'agent-rules.json').read_bytes())
    proposed = json.loads((ENERGY / 'agent-rules.json').read_bytes())
    assert proposed['compositions'] == live['compositions']
    changed = {key for key in live['texts'] if live['texts'][key] != proposed['texts'][key]}
    assert changed == (set() if adopted(ENERGY) else SIX)
    for value in proposed['texts'].values():
        assert not re.search(r'pressure|energy', value, re.I)
        assert not re.search(r'as fast as|hurry|asap|quickly|go fast', value, re.I)
    assert 'Set rest to true when you should stop: stop work and return a minimal authorized work-only checkpoint' in proposed['texts']['COMMONS_RULES']
    assert GUARD in proposed['texts']['PRESSURE_RULES']
    assert proposed['texts']['WORKER_PREFIX'].rstrip().endswith('limitations, rest.')


def test_energy_proposal_is_inactive_until_two_people_approve_it(tmp_path):
    raw = (ENERGY / 'agent-rules.json').read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest in (ENERGY / 'README.md').read_text(encoding='utf-8')
    if adopted(ENERGY):
        assert 'rest' in load_rules(ENERGY / 'agent-rules.json', APPROVALS)['WORKER_PREFIX']
        return
    with pytest.raises(RulesError):
        load_rules(ENERGY / 'agent-rules.json', APPROVALS)
    two = tmp_path / 'two.json'
    two.write_text(json.dumps([{'sha256': digest, 'approved_by': ['steve', 'nate'], 'approved_at': '2026-10-19T01:00:00+00:00',
                                'note': 'synthetic two-human approval for this offline check only'}]))
    assert 'energy' not in load_rules(ENERGY / 'agent-rules.json', two)['CONDUIT_MISSION'].lower()
