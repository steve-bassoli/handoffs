"""Offline relay checks: a mock provider stands in for every agent; nothing is dispatched."""
import json
import threading

import httpx
import pytest

from app.astra_tree import Tree, outgoing
from test_agent_conduit import candidate, stream_result, tool, usage


def plan(tmp_path):
    shelf = {}
    for name in ('catalog', 'alpha', 'beta'):
        path = tmp_path / f'{name}.txt'
        path.write_text(f'{name} source', encoding='utf-8')
        shelf[name] = {name: str(path)}
    return {'goal': 'Fixture goal', 'authority': 'Proposals only',
            'coordinator': {'shelf': shelf['catalog']},
            'workers': [{'name': 'alpha', 'role': 'reads source', 'shelf': shelf['alpha'], 'max_requests': 3},
                        {'name': 'beta', 'role': 'writes cases', 'shelf': shelf['beta'], 'max_requests': 3}]}


def mock(seen, done_round=3):
    lock = threading.Lock()

    def respond(request):
        payload = json.loads(request.content)
        content = json.loads(payload['input'][0]['content'])
        coordinator = 'TREE ROLE coordinator' in payload['instructions']
        name = 'coordinator' if coordinator else content['your_name']
        with lock:
            seen.append((name, content['round'], payload['tool_choice'], content))
        if payload['tool_choice'] == 'required':
            return stream_result([tool(payload['tools'][0]['parameters']['properties']['key']['enum'][0])], usage())
        if coordinator:
            reply = {'summary': f'round {content["round"]}', 'done': content['round'] >= done_round,
                     'directives': {'alpha': 'read', 'beta': 'write'}, 'synthesis': {'plan': ['fixture']},
                     'messages': [{'to': 'alpha', 'text': 'coordinator asks alpha'}]}
        elif name == 'alpha':
            reply = {'summary': 'alpha facts', 'messages': [{'to': 'beta', 'text': f'alpha fact r{content["round"]}'}]}
        else:
            reply = {'summary': 'beta cases', 'messages': [{'to': 'coordinator', 'text': 'beta needs review'},
                                                           {'to': 'nobody', 'text': 'dropped'}]}
        return stream_result(candidate(json.dumps(reply)), usage())
    return httpx.MockTransport(respond)


def test_messages_route_between_rounds_and_done_ends_session(tmp_path):
    seen = []
    session = tmp_path / 'session'
    session.mkdir()
    summary = Tree(plan(tmp_path), session, 30, transport=mock(seen)).run()
    turns = [(t['agent'], t['round'], t['state']) for t in summary['turns']]
    assert turns == [('coordinator', 1, 'candidate_prepared'), ('alpha', 1, 'candidate_prepared'), ('beta', 1, 'candidate_prepared'),
                     ('coordinator', 2, 'candidate_prepared'), ('alpha', 2, 'candidate_prepared'), ('beta', 2, 'candidate_prepared'),
                     ('coordinator', 3, 'candidate_prepared')]
    answers = {(name, number): content for name, number, choice, content in seen if choice != 'required'}
    assert answers[('alpha', 1)]['inbox'] == [{'from': 'coordinator', 'to': 'alpha', 'text': 'coordinator asks alpha'}]
    assert answers[('beta', 1)]['inbox'] == []
    assert answers[('beta', 2)]['inbox'] == [{'from': 'alpha', 'to': 'beta', 'text': 'alpha fact r1'}]
    assert answers[('coordinator', 2)]['inbox'] == [{'from': 'beta', 'to': 'coordinator', 'text': 'beta needs review'}]
    assert set(answers[('coordinator', 2)]['worker_reports']) == {'alpha', 'beta'}
    assert answers[('beta', 1)]['directive'] == 'write'
    assert summary['final_synthesis'] == {'plan': ['fixture']} and summary['requests'] == 14
    assert summary['candidates_applied'] is False and summary['human_accepted'] is False
    board = [json.loads(line) for line in (session / 'board.jsonl').read_text(encoding='utf-8').splitlines()]
    assert not any(event.get('to') == 'nobody' for event in board)
    assert (session / 'alpha' / 'round-02.json').exists() and (session / 'alpha' / 'request-04-receipt.json').exists()


def test_deadline_stops_new_rounds_and_requests_one_final_synthesis(tmp_path):
    seen, now = [], [0.0]
    session = tmp_path / 'session'
    session.mkdir()
    tree = Tree(plan(tmp_path), session, 30, transport=mock(seen, done_round=99), clock=lambda: now[0])
    original = tree.turn

    def slow_worker(name, *args, **kwargs):
        if name != 'coordinator':
            now[0] = 31 * 60  # Workers start after the deadline.
        return original(name, *args, **kwargs)
    tree.turn = slow_worker
    summary = tree.run()
    assert [(t['agent'], t['round'], t['final']) for t in summary['turns']] == [
        ('coordinator', 1, False), ('alpha', 1, False), ('beta', 1, False), ('coordinator', 2, True)]
    assert [t['state'] for t in summary['turns'][1:3]] == ['rest_deadline', 'rest_deadline']
    final = [content for name, number, choice, content in seen if name == 'coordinator' and number == 2]
    assert final and final[0]['final_synthesis_required'] is True


def test_outgoing_expands_all_and_never_echoes_to_sender():
    names = ['coordinator', 'alpha', 'beta']
    sent = outgoing('alpha', {'messages': [{'to': 'all', 'text': 'hi'}, {'to': 'alpha', 'text': 'self'}, 'bad']}, names)
    assert [(m['from'], m['to']) for m in sent] == [('alpha', 'coordinator'), ('alpha', 'beta')]


def thirteen(tmp_path):
    path = tmp_path / 'shared.txt'
    path.write_text('shared source', encoding='utf-8')
    shelf = {'shared': str(path)}
    return {'goal': 'Fixture goal', 'authority': 'Proposals only', 'coordinator': {'shelf': shelf},
            'children': [{'name': lead, 'role': f'{lead} lead', 'shelf': shelf, 'max_requests': 1,
                          'children': [{'name': f'{lead}{n}', 'role': 'low', 'shelf': shelf, 'max_requests': 1}
                                       for n in range(1, 4)]}
                         for lead in ('catalog', 'observe', 'judge')]}


def tree_mock(seen, done_round=2):
    lock = threading.Lock()

    def respond(request):
        payload = json.loads(request.content)
        content = json.loads(payload['input'][0]['content'])
        name, number = content['your_name'], content['round']
        with lock:
            seen.append((name, number, content))
        if name == 'coordinator':
            reply = {'summary': 'root', 'done': number >= done_round,
                     'directives': {'catalog': 'catalog it', 'observe': 'observe it', 'judge': 'judge it'}}
        elif content['complexity'] == 'MEDIUM':
            reply = {'summary': f'{name} lead', 'report': f'{name} report r{number}',
                     'directives': {f'{name}{n}': f'{name} task {n}' for n in range(1, 4)},
                     'messages': [{'to': 'siblings', 'text': f'{name} to siblings'}]}
        else:
            reply = {'summary': f'{name} done', 'messages': [{'to': 'parent', 'text': f'{name} to parent'}]}
        return stream_result(candidate(json.dumps(reply)), usage())
    return httpx.MockTransport(respond)


def test_thirteen_node_tree_runs_high_medium_low_and_routes_groups(tmp_path):
    seen = []
    session = tmp_path / 'session'
    session.mkdir()
    summary = Tree(thirteen(tmp_path), session, 30, transport=tree_mock(seen)).run()
    levels = [(t['agent'], t['level'], t['round']) for t in summary['turns']]
    assert len(levels) == 1 + 3 + 9 + 1 and levels[0] == ('coordinator', 'HIGH', 1) and levels[-1] == ('coordinator', 'HIGH', 2)
    assert {level for agent, level, _ in levels[4:13]} == {'LOW'}
    by = {(name, number): content for name, number, content in seen}
    assert by[('catalog', 1)]['complexity'] == 'MEDIUM' and by[('catalog', 1)]['directive'] == 'catalog it'
    assert by[('catalog2', 1)]['directive'] == 'catalog task 2' and by[('catalog2', 1)]['parent'] == 'catalog'
    assert {m['from'] for m in by[('catalog3', 1)]['inbox']} == set()
    assert sorted(m['from'] for m in by[('coordinator', 2)]['inbox']) == []
    assert set(by[('coordinator', 2)]['worker_reports']) == {'catalog', 'observe', 'judge'}
    board = [json.loads(line) for line in (session / 'board.jsonl').read_text(encoding='utf-8').splitlines()]
    routed = {(e['from'], e['to']) for e in board if e['event'] == 'message'}
    assert ('catalog', 'observe') in routed and ('catalog', 'judge') in routed and ('catalog', 'catalog1') not in routed
    assert ('observe2', 'observe') in routed and ('observe2', 'coordinator') not in routed


def test_tree_limits_are_enforced(tmp_path):
    plan = thirteen(tmp_path)
    plan['children'][0]['children'].append({'name': 'extra', 'role': 'low', 'shelf': plan['coordinator']['shelf']})
    with pytest.raises(ValueError):
        Tree(plan, tmp_path, 30)
    plan = thirteen(tmp_path)
    plan['children'][0]['children'][0]['children'] = [{'name': 'deep', 'role': 'x', 'shelf': plan['coordinator']['shelf']}]
    with pytest.raises(ValueError):
        Tree(plan, tmp_path, 30)


def test_luna_plan_sends_luna_with_proven_effort_and_output_ceiling(tmp_path):
    seen = []
    plan_value = {**thirteen(tmp_path), 'model': 'luna'}
    payloads = []

    def respond(request):
        payload = json.loads(request.content)
        payloads.append((payload['model'], payload['reasoning']['effort'], payload.get('max_output_tokens')))
        return tree_mock(seen, done_round=1).handler(request)
    session = tmp_path / 'session'
    session.mkdir()
    summary = Tree(plan_value, session, 30, transport=httpx.MockTransport(respond)).run()
    assert set(payloads) == {('gpt-6-luna', 'low', 12000)} and set(summary['models'].values()) == {'gpt-6-luna'}
    with pytest.raises(ValueError):
        Tree({**plan_value, 'model': 'nova'}, tmp_path, 30)


def test_every_tree_message_names_json_for_json_object_output(tmp_path):
    seen = []
    session = tmp_path / 'session'
    session.mkdir()
    Tree(thirteen(tmp_path), session, 30, transport=tree_mock(seen, done_round=2)).run()
    assert seen and all(content['reply_format'] == 'one JSON object' for _, _, content in seen)
