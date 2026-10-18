"""bob-the-architect -> bob-the-builder -> the bobs (task e888181d): personality cards, mirroring data, hidden clock, UI stamp.

Offline: a mock provider stands in for every agent; nothing is dispatched.
"""
import json
import threading

import httpx
import pytest

from app.astra_tree import PERSONALITY_LIMIT, Tree
from app.rules import CONDUIT_MISSION, ROLE_RULES
from test_agent_conduit import candidate, stream_result, usage
from test_astra_tree import thirteen, tree_mock

ARCHITECT_CARD = {'specialty': 'UI veteran, filter and final stamp', 'personality': 'Calm, warm and funny; takes the noise so the builder stays happy.'}


def team_plan(tmp_path):
    source = tmp_path / 'shared.txt'
    source.write_text('shared source', encoding='utf-8')
    shelf = {'shared': str(source)}
    return {'goal': 'Fixture goal', 'authority': 'Proposals only', 'root_name': 'bob-the-architect', 'clock_owner': 'root',
            'culture': 'Fixture culture: have fun, be creative, mirror the bob you talk to.',
            'coordinator': {'shelf': shelf, 'card': ARCHITECT_CARD},
            'children': [{'name': 'bob-the-builder', 'role': 'Builds with his team', 'shelf': shelf, 'max_requests': 1,
                          'children': [{'name': f'bob-{n}', 'role': 'Team member', 'shelf': shelf, 'max_requests': 1} for n in (3, 4, 5)]}]}


def team_mock(seen):
    lock = threading.Lock()

    def respond(request):
        payload = json.loads(request.content)
        content = json.loads(payload['input'][0]['content'])
        name, number = content['your_name'], content['round']
        with lock:
            seen.append((name, number, content, payload['instructions']))
        if name == 'bob-the-architect':
            reply = {'summary': 'architect', 'done': number >= 2, 'directives': {'bob-the-builder': 'build something delightful'},
                     'cards': {'bob-the-builder': {'specialty': 'Integrator', 'personality': 'Cheerful builder. ' + 'x' * 2000},
                               'bob-3': {'specialty': 'Sneaky', 'personality': 'Not the architect\'s to set'}},
                     'stamp': {'approved': number >= 2, 'notes': 'Minimal, smooth, works at phone width.'}}
        elif name == 'bob-the-builder':
            reply = {'summary': 'builder', 'directives': {'bob-3': 'sketch', 'bob-4': 'contract', 'bob-5': 'break it'},
                     'cards': {'bob-3': {'specialty': 'UX', 'personality': 'Pixel-picky; talks in sketches.'},
                               'bob-4': {'specialty': 'REST', 'personality': 'Contract purist with dry humour.'},
                               'bob-5': {'specialty': 'Tests'}}}
        else:
            reply = {'summary': f'{name} done', 'cards': {'bob-3': {'specialty': 'Boss', 'personality': 'Workers have no team.'}}}
        return stream_result(candidate(json.dumps(reply)), usage())
    return httpx.MockTransport(respond)


def run_team(tmp_path, seen):
    session = tmp_path / 'session'
    session.mkdir()
    summary = Tree(team_plan(tmp_path), session, 30, transport=team_mock(seen), mode='team').run()
    board = [json.loads(line) for line in (session / 'board.jsonl').read_text(encoding='utf-8').splitlines()]
    return summary, {(name, number): content for name, number, content, _ in seen}, board


def test_each_bob_sets_only_its_own_childrens_cards(tmp_path):
    seen = []
    summary, by, board = run_team(tmp_path, seen)
    assert by[('bob-the-architect', 1)]['your_card'] == ARCHITECT_CARD
    builder = by[('bob-the-builder', 1)]['your_card']
    assert builder['specialty'] == 'Integrator' and builder['personality'].endswith('[clipped by relay]')
    assert len(builder['personality']) <= PERSONALITY_LIMIT + len(' …[clipped by relay]')
    assert by[('bob-3', 1)]['your_card'] == {'specialty': 'UX', 'personality': 'Pixel-picky; talks in sketches.'}
    assert by[('bob-4', 1)]['your_card']['specialty'] == 'REST' and by[('bob-5', 1)]['your_card'] is None
    # A bob sees the cards it wrote from its next turn on, so it can mirror them.
    assert by[('bob-the-builder', 1)]['children_cards'] == {'bob-3': None, 'bob-4': None, 'bob-5': None}
    assert by[('bob-the-architect', 2)]['children_cards']['bob-the-builder']['specialty'] == 'Integrator'
    sets = {(e['by'], e['for']) for e in board if e['event'] == 'card_set'}
    refused = {(e['by'], e['for'], e['reason']) for e in board if e['event'] == 'card_refused'}
    assert sets == {('bob-the-architect', 'bob-the-builder'), ('bob-the-builder', 'bob-3'), ('bob-the-builder', 'bob-4')}
    assert ('bob-the-architect', 'bob-3', 'not a direct child') in refused
    assert ('bob-the-builder', 'bob-5', 'needs specialty and personality') in refused
    assert ('bob-4', 'bob-3', 'not a direct child') in refused
    assert summary['cards']['bob-3']['specialty'] == 'UX'


def test_only_the_architect_sees_the_clock_and_culture_reaches_everyone(tmp_path):
    seen = []
    _, by, _ = run_team(tmp_path, seen)
    assert 'minutes_remaining' in by[('bob-the-architect', 1)]
    for name in ('bob-the-builder', 'bob-3', 'bob-4', 'bob-5'):
        assert 'minutes_remaining' not in by[(name, 1)]
        assert by[(name, 1)]['team_culture'].startswith('Fixture culture')


def test_cards_never_change_the_protected_instructions(tmp_path):
    seen = []
    run_team(tmp_path, seen)
    kinds = {'bob-the-architect': 'coordinator', 'bob-the-builder': 'lead'}
    for name, _, _, instructions in seen:
        assert instructions == CONDUIT_MISSION + ROLE_RULES[kinds.get(name, 'worker')]
        assert 'Pixel-picky' not in instructions and 'Cheerful builder' not in instructions


def test_architect_stamp_is_recorded_and_is_not_acceptance(tmp_path):
    summary, _, board = run_team(tmp_path, [])
    assert summary['architect_stamp'] == {'approved': True, 'round': 2, 'notes': 'Minimal, smooth, works at phone width.'}
    assert summary['human_accepted'] is False and summary['candidates_applied'] is False
    assert [e['approved'] for e in board if e['event'] == 'stamp'] == [False, True]


def test_example_plan_fits_team_mode_within_limits(tmp_path):
    from pathlib import Path
    from app.astra_tree import CULTURE_LIMIT, card
    example = json.loads((Path(__file__).resolve().parents[1] / 'docs' / 'bob-team-plan.example.json').read_text(encoding='utf-8'))
    source = tmp_path / 'shared.txt'
    source.write_text('shared source', encoding='utf-8')

    def fill(node):
        node['shelf'] = {'shared': str(source)}
        for child in node.get('children', []):
            fill(child)
    fill(example['coordinator'])
    for child in example['children']:
        fill(child)
    tree = Tree(example, tmp_path, 30, mode=example['mode'])
    assert len(example['culture']) <= CULTURE_LIMIT and tree.culture == example['culture']
    assert tree.cards['bob-the-architect'] == card(example['coordinator']['card'])
    assert tree.cards['bob-the-architect']['personality'] == example['coordinator']['card']['personality']  # Not clipped.


def test_team_mode_fits_the_shape_and_plain_trees_are_unchanged(tmp_path):
    plan = team_plan(tmp_path)
    Tree(plan, tmp_path, 30, mode='team')
    plan['children'][0]['children'].append({'name': 'bob-6', 'role': 'x', 'shelf': plan['coordinator']['shelf']})
    with pytest.raises(ValueError):
        Tree(plan, tmp_path, 30, mode='team')
    seen = []
    session = tmp_path / 'plain'
    session.mkdir()
    summary = Tree(thirteen(tmp_path), session, 30, transport=tree_mock(seen, done_round=1)).run()
    assert all('your_card' not in content and 'minutes_remaining' in content for _, _, content in seen)
    assert 'cards' not in summary and 'architect_stamp' not in summary
