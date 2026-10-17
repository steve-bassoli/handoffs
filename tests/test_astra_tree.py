"""Offline relay checks: a mock provider stands in for every agent; nothing is dispatched."""
import json
import threading

import httpx

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
    assert answers[('beta', 1)]['coordinator_directive'] == 'write'
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
    original = tree.worker_turn

    def slow_worker(*args):
        now[0] = 31 * 60  # Workers finish after the deadline.
        return original(*args)
    tree.worker_turn = slow_worker
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
