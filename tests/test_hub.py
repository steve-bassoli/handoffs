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
