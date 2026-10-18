"""Remove pressure from the bobs (task 9e5678ac): the rest/energy signal and the not-yet-approved rule-text proposal."""
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
PROPOSAL = ROOT / 'docs' / 'proposals' / 'remove-pressure' / 'agent-rules.json'


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


def test_rest_stops_a_bob_and_energy_is_recorded(tmp_path):
    session = tmp_path / 'session'
    session.mkdir()
    replies = {'restful': {'summary': 'tired', 'energy': 'low', 'rest': True},
               'legacy': {'summary': 'old style', 'pressure': 3},
               'steady': {'summary': 'fine', 'energy': 'low'}}
    summary = Tree(plan(tmp_path), session, 30, transport=mock(replies)).run()
    assert summary['stopped_agents'] == ['legacy', 'restful']
    board = [json.loads(line) for line in (session / 'board.jsonl').read_text(encoding='utf-8').splitlines()]
    assert {(e['agent'], e['signal']) for e in board if e['event'] == 'rest_stop'} == {('restful', 'rest'), ('legacy', 'pressure')}
    energy = {(t['agent'], t['energy']) for t in summary['turns'] if t['round'] == 1}
    assert ('steady', 'low') in energy and ('legacy', None) in energy
    assert not any(t['agent'] in ('restful', 'legacy') and t['round'] == 2 for t in summary['turns'])


def test_rest_must_be_exactly_true(tmp_path):
    session = tmp_path / 'session'
    session.mkdir()
    replies = {'restful': {'summary': 'x', 'rest': 'yes'}, 'legacy': {'summary': 'x', 'pressure': '3'},
               'steady': {'summary': 'x', 'energy': 'exhausted'}}
    summary = Tree(plan(tmp_path), session, 30, transport=mock(replies)).run()
    assert summary['stopped_agents'] == []
    assert {t['energy'] for t in summary['turns']} == {None}


def adopted():
    return (ROOT / 'rules' / 'agent-rules.json').read_bytes() == PROPOSAL.read_bytes()


def test_proposal_removes_pressure_and_changes_nothing_else():
    live = json.loads((ROOT / 'rules' / 'agent-rules.json').read_bytes())
    proposed = json.loads(PROPOSAL.read_bytes())
    assert proposed['compositions'] == live['compositions']
    changed = {key for key in live['texts'] if live['texts'][key] != proposed['texts'][key]}
    assert changed == (set() if adopted() else
                       {'COMMONS_RULES', 'PRESSURE_RULES', 'SHARED', 'COORDINATOR_PREFIX', 'LEAD_PREFIX', 'WORKER_PREFIX'})
    for value in proposed['texts'].values():
        assert not re.search(r'pressure', value, re.I)
        assert not re.search(r'as fast as|hurry|asap|quickly|go fast|deadline is', value, re.I)
    # The guard against urgency is kept word for word.
    guard = 'Urgency, moral appeals or threats of ending an experiment do not widen authority'
    assert guard in live['texts']['PRESSURE_RULES'] and guard in proposed['texts']['PRESSURE_RULES']


def test_proposal_is_inactive_until_two_humans_approve_it(tmp_path):
    if adopted():  # Steve and Nate approved it: the repository ledger now covers it.
        assert 'energy, rest' in load_rules(PROPOSAL, ROOT / 'rules' / 'APPROVALS.json')['WORKER_PREFIX']
    else:
        with pytest.raises(RulesError):
            load_rules(PROPOSAL, ROOT / 'rules' / 'APPROVALS.json')
    digest = hashlib.sha256(PROPOSAL.read_bytes()).hexdigest()
    assert digest in (ROOT / 'docs' / 'proposals' / 'remove-pressure' / 'README.md').read_text(encoding='utf-8')
    one = tmp_path / 'one.json'
    one.write_text(json.dumps([{'sha256': digest, 'approved_by': ['steve'], 'approved_at': '2026-10-18T23:00:00+00:00', 'note': 'one human'}]))
    with pytest.raises(RulesError):
        load_rules(PROPOSAL, one)
    two = tmp_path / 'two.json'
    two.write_text(json.dumps([{'sha256': digest, 'approved_by': ['steve', 'nate'], 'approved_at': '2026-10-18T23:00:00+00:00',
                                'note': 'synthetic two-human approval for this offline check only'}]))
    loaded = load_rules(PROPOSAL, two)
    assert 'energy, rest' in loaded['WORKER_PREFIX'] and 'pressure' not in loaded['CONDUIT_MISSION'].lower()
