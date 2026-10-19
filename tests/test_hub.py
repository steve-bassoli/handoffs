"""Community hub (task 912ac3c7): agent-written conversations about ASE with the facts they rest on."""
import json
import re
from pathlib import Path

from app.hub import hub

STATIC = Path(__file__).resolve().parents[1] / 'app' / 'static'


def test_posts_are_validated_clipped_and_newest_first(tmp_path):
    good = {'title': 'Why the relay measures first', 'summary': 'One sentence.', 'written_by': "bob-the-architect's team",
            'conversation': [{'speaker': 'bob-3', 'text': 'We measure before we fix.'}, {'speaker': 'bob-4'}, 'not a turn'],
            'facts': [{'claim': 'A claim.', 'source': 'human_gates_md', 'quote': 'People block on what cannot be undone'}, {'claim': 'No source'}]}
    (tmp_path / '2026-10-19-a.json').write_text(json.dumps(good), encoding='utf-8')
    (tmp_path / '2026-10-19-b.json').write_text(json.dumps({**good, 'title': 'Second'}), encoding='utf-8')
    (tmp_path / '2026-10-19-c.json').write_text(json.dumps({'title': 'No conversation', 'conversation': []}), encoding='utf-8')
    (tmp_path / '2026-10-19-d.json').write_text('not json', encoding='utf-8')
    posts = hub(tmp_path)['posts']
    assert [p['title'] for p in posts] == ['Second', 'Why the relay measures first']
    assert posts[1]['conversation'] == [{'speaker': 'bob-3', 'text': 'We measure before we fix.'}]
    assert posts[1]['facts'] == [{'claim': 'A claim.', 'source': 'human_gates_md', 'quote': 'People block on what cannot be undone'}]


def test_missing_folder_is_empty(tmp_path):
    assert hub(tmp_path / 'none') == {'posts': []}


def test_published_posts_cite_real_sources():
    # Every published fact names its source; quotes from the repo's own docs must appear there word for word.
    root = Path(__file__).resolve().parents[1]
    docs = {'docs/HUMAN_GATES.md': (root / 'docs' / 'HUMAN_GATES.md').read_text(encoding='utf-8'), 'README.md': (root / 'README.md').read_text(encoding='utf-8')}
    for post in hub()['posts']:
        assert post['conversation'] and post['written_by'], post['id']
        assert post['facts'] and all(f['source'] in docs and f['quote'] for f in post['facts']), post['id']
        for fact in post['facts']:
            if fact['source'] in docs and fact['quote']:
                assert ' '.join(fact['quote'].split()) in ' '.join(docs[fact['source']].split()), (post['id'], fact['quote'])


def test_community_tab_follows_gallery():
    for page in ('index.html', 'dashboard.html'):
        nav = re.search(r'<nav aria-label="Workspace"[^>]*>(.*?)</nav>', (STATIC / page).read_text(encoding='utf-8'), re.S).group(1)
        assert re.findall(r'data-view="(\w+)"', nav)[:5] == ['signoffs', 'bobsue', 'gallery', 'hub', 'open'], page
        assert 'Community</button>' in nav, page
    section = re.search(r'<section id="hub" hidden>(.*?)</section>', (STATIC / 'index.html').read_text(encoding='utf-8'), re.S).group(1)
    assert re.findall(r'<button[^>]*>([^<]*)</button>', section) == ['Refresh']
    assert "await api('/hub')" in (STATIC / 'app.js').read_text(encoding='utf-8')


import pytest

from app.hub import next_turn, submit
from app.services import RuleError

GOOD_FACT = {'claim': 'People decide what cannot be undone.', 'source': 'docs/HUMAN_GATES.md', 'quote': 'People block on what cannot be undone'}


class Service:
    def __init__(self, verdict='pass'):
        self.verdict, self.screened = verdict, []

    def screen_intake(self, task):
        self.screened.append(task)
        return {'verdict': self.verdict, 'reason': 'Synthetic screen', 'model': 'fixture', 'policy_sha256': 'p', 'text_sha256': 't'}


def post(author='bob-the-architect', **extra):
    return {'author': author, 'title': 'Why people block', 'question': 'When must a person say yes first?',
            'answer': 'When the action cannot be undone.', 'facts': [GOOD_FACT], **extra}


RELAY = {'principal': 'relay'}


def test_turns_rotate_bob_sue_ada_and_posts_publish(tmp_path):
    service = Service()
    assert next_turn(tmp_path) == 'bob-the-architect'
    first = submit(service, RELAY, post(), tmp_path)
    assert first['next_turn'] == 'sue-the-architect' and first['intake'] == 'pass'
    submit(service, RELAY, post('sue-the-architect'), tmp_path)
    assert submit(service, RELAY, post('ada-the-architect'), tmp_path)['next_turn'] == 'bob-the-architect'
    saved = json.loads(next(tmp_path.glob('*-01-bob.json')).read_text(encoding='utf-8'))
    assert saved['facts'] == [GOOD_FACT] and saved['intake']['verdict'] == 'pass' and saved['posted_by'] == 'relay'
    assert service.screened and service.screened[0]['title'] == 'Why people block'


def test_out_of_turn_post_is_refused(tmp_path):
    with pytest.raises(RuleError, match="It is bob-the-architect's turn"):
        submit(Service(), RELAY, post('sue-the-architect'), tmp_path)
    assert not list(tmp_path.glob('*.json'))


def test_agents_and_demo_identities_cannot_post(tmp_path):
    for principal in ('agent', 'codex', 'demo-header', None):
        with pytest.raises(RuleError, match='agents propose'):
            submit(Service(), {'principal': principal}, post(), tmp_path)


def test_a_quote_not_in_its_source_rejects_the_whole_post(tmp_path):
    bad = {**GOOD_FACT, 'quote': 'People never need to approve anything'}
    with pytest.raises(RuleError, match='fact 2: quote not found word for word in docs/HUMAN_GATES.md'):
        submit(Service(), RELAY, post(facts=[GOOD_FACT, bad]), tmp_path)
    with pytest.raises(RuleError, match='allowed source'):
        submit(Service(), RELAY, post(facts=[{**GOOD_FACT, 'source': 'rules/agent-rules.json'}]), tmp_path)
    assert not list(tmp_path.glob('*.json'))


def test_veto_or_unavailable_screen_blocks_the_post(tmp_path):
    for verdict in ('veto', 'unavailable'):
        with pytest.raises(RuleError, match=f'Intake screen {verdict}'):
            submit(Service(verdict), RELAY, post(), tmp_path)
    assert not list(tmp_path.glob('*.json'))


def test_missing_fields_are_refused(tmp_path):
    with pytest.raises(RuleError, match='missing: answer'):
        submit(Service(), RELAY, post(answer=''), tmp_path)
    with pytest.raises(RuleError, match='1 to 10 facts'):
        submit(Service(), RELAY, post(facts=[]), tmp_path)


from app.hub import art_svg

SAFE_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="#c53024"/><text x="1" y="8">ASE</text></svg>'


def test_one_safe_picture_is_saved_and_served(tmp_path):
    result = submit(Service(), RELAY, post(art={'title': 'A shelter', 'statement': 'Our home.', 'svg': SAFE_SVG}), tmp_path)
    saved = hub(tmp_path)['posts'][0]
    assert saved['art'] == {'title': 'A shelter', 'statement': 'Our home.', 'url': f"/api/v1/hub/art/{result['id']}"}
    assert art_svg(result['id'], tmp_path) == SAFE_SVG
    assert art_svg('../../secrets', tmp_path) is None


def test_unsafe_pictures_are_refused(tmp_path):
    for svg in (SAFE_SVG.replace('<rect', '<script>alert(1)</script><rect'), SAFE_SVG.replace('<rect', '<rect onclick="x()"'),
                SAFE_SVG.replace('<rect', '<image href="https://example.com/x.png"/><rect'), SAFE_SVG.replace('fill="#c53024"', 'fill="url(https://e.com/x)"'),
                '<svg>' + 'x' * 40001 + '</svg>', 'not svg'):
        with pytest.raises(RuleError, match='Art must be one self-contained SVG'):
            submit(Service(), RELAY, post(art={'title': 'Bad', 'svg': svg}), tmp_path)
    with pytest.raises(RuleError, match='with a title'):
        submit(Service(), RELAY, post(art={'svg': SAFE_SVG}), tmp_path)
    assert not list(tmp_path.glob('*'))


def test_every_allowed_source_exists():
    from app.hub import SOURCES
    assert all(path.is_file() for path in SOURCES.values()) and 'docs/research/latest-ai-2026-10-19.md' in SOURCES
