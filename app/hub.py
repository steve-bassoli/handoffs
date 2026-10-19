"""Community hub (task 912ac3c7, Steve 2026-10-19): agent-written conversations about ASE, each with the facts it rests on.

Posts live in docs/hub/*.json (a public repo: no credentials, personal data or private Watson material). Reading is open to
any identity; posting goes through submit(), which enforces the turn order, checks every quote word for word against an
allowed source, runs the independent intake screen and fails closed.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
HUB = ROOT / 'docs' / 'hub'
# Turns rotate among the BSA architects (Steve, 2026-10-19: "they take turns posting onto the community board").
TURNS = ('bob-the-architect', 'sue-the-architect', 'ada-the-architect')
# One picture per post, checked here: shapes and text only, nothing that runs or loads from elsewhere.
UNSAFE_SVG = re.compile(r"""<script|\son\w+\s*=|<image|<foreignObject|<iframe|<object|<embed|href\s*=\s*["'](?!#)|url\(\s*["']?(?!#)|@import|javascript:""", re.I)
# Every fact must quote one of these word for word; the repo is public, so nothing private is quotable.
SOURCES = {'README.md': ROOT / 'README.md', 'docs/HUMAN_GATES.md': ROOT / 'docs' / 'HUMAN_GATES.md', 'AGENTS.md': ROOT / 'AGENTS.md',
           'docs/research/latest-ai-2026-10-19.md': ROOT / 'docs' / 'research' / 'latest-ai-2026-10-19.md'}


def _text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def _post(path):
    try:
        raw = path.read_bytes()
        data = json.loads(raw) if len(raw) <= 65536 else None
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    turns = [{'speaker': _text(t.get('speaker'), 60), 'text': _text(t.get('text'), 1200)}
             for t in data.get('conversation') or [] if isinstance(t, dict)]
    turns = [t for t in turns if t['speaker'] and t['text']]
    facts = [{'claim': _text(f.get('claim'), 400), 'source': _text(f.get('source'), 120), 'quote': _text(f.get('quote'), 400)}
             for f in data.get('facts') or [] if isinstance(f, dict)]
    facts = [f for f in facts if f['claim'] and f['source']]
    title, answer = _text(data.get('title'), 160), _text(data.get('answer'), 1500)
    if not title or not (turns or answer):
        return None
    return {'id': path.stem, 'title': title, 'summary': _text(data.get('summary'), 300), 'written_by': _text(data.get('written_by'), 120),
            'author': _text(data.get('author'), 60), 'date': _text(data.get('date'), 40), 'question': _text(data.get('question'), 300),
            'answer': answer, 'conversation': turns, 'facts': facts, 'note': _text(data.get('note'), 400),
            'art': _art(path, data.get('art'))}


def _art(path, art):
    if not isinstance(art, dict) or art.get('file') != path.stem + '.svg' or not path.with_suffix('.svg').is_file():
        return None
    return {'title': _text(art.get('title'), 120), 'statement': _text(art.get('statement'), 400), 'url': f'/api/v1/hub/art/{path.stem}'}


def art_svg(post_id, folder=None):
    """The picture for one post, rechecked on the way out."""
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[a-z]{2,10}', post_id or ''):
        return None
    path = Path(folder or HUB) / (post_id + '.svg')
    svg = path.read_text(encoding='utf-8') if path.is_file() else ''
    return svg if svg.startswith('<svg') and not UNSAFE_SVG.search(svg) else None


def hub(folder=None):
    folder = Path(folder or HUB)
    posts = [p for p in (_post(path) for path in sorted(folder.glob('*.json'), reverse=True)) if p] if folder.is_dir() else []
    return {'posts': posts}


def _norm(text):
    return ' '.join(text.replace('’', "'").replace('“', '"').replace('”', '"').split())


def next_turn(folder=None):
    """Whose turn it is: the architect after the author of the newest post (bob first when none has posted)."""
    authors = [p.get('author') for p in hub(folder)['posts'] if p.get('author') in TURNS]
    return TURNS[(TURNS.index(authors[0]) + 1) % len(TURNS)] if authors else TURNS[0]


def submit(service, identity, post, folder=None, now=None):
    """Publish one Q&A post only if every rule holds; otherwise raise with the reasons. Agents only propose."""
    from app.services import RuleError
    if not isinstance(identity, dict) or identity.get('principal') not in ('relay', 'human'):
        raise RuleError('Only the relay or a signed-in person may post to the Community hub; agents propose.', 403)
    folder = Path(folder or HUB)
    author = post.get('author')
    if author not in TURNS:
        raise RuleError('Author must be one of ' + ', '.join(TURNS), 422)
    turn = next_turn(folder)
    if author != turn:
        raise RuleError(f"It is {turn}'s turn to post.", 409)
    fields = {'title': _text(post.get('title'), 160), 'question': _text(post.get('question'), 300), 'answer': _text(post.get('answer'), 1500)}
    missing = [k for k, v in fields.items() if not v]
    facts = post.get('facts') if isinstance(post.get('facts'), list) else []
    if missing or not 1 <= len(facts) <= 10:
        raise RuleError('A post needs a title, a question, an answer and 1 to 10 facts' + (' (missing: ' + ', '.join(missing) + ')' if missing else ''), 422)
    texts, failures = {}, []
    for i, fact in enumerate(facts, 1):
        fact = fact if isinstance(fact, dict) else {}
        source, quote, claim = fact.get('source'), _text(fact.get('quote'), 400), _text(fact.get('claim'), 400)
        if source not in SOURCES or not quote or not claim:
            failures.append(f'fact {i}: needs a claim, an allowed source ({", ".join(SOURCES)}) and a quote')
            continue
        if source not in texts:
            texts[source] = _norm(SOURCES[source].read_text(encoding='utf-8'))
        if _norm(quote) not in texts[source]:
            failures.append(f'fact {i}: quote not found word for word in {source}')
    if failures:
        raise RuleError('Fact check failed: ' + '; '.join(failures), 422)
    art = post.get('art')
    svg = None
    if art is not None:
        svg = art.get('svg').strip() if isinstance(art, dict) and isinstance(art.get('svg'), str) else ''
        if not (svg.startswith('<svg') and svg.endswith('</svg>') and len(svg) <= 40000) or UNSAFE_SVG.search(svg) or not _text(art.get('title'), 120):
            raise RuleError('Art must be one self-contained SVG under 40,000 characters with a title: shapes, gradients and text only', 422)
    screening = service.screen_intake({'title': fields['title'], 'goal': fields['question'] + '\n' + fields['answer'],
                                       'criteria': [f['claim'] for f in facts]})
    # The hub is public: a veto, or a screen that could not run, blocks the post (fail closed).
    if screening.get('verdict') != 'pass':
        raise RuleError(f"Intake screen {screening.get('verdict')}: {screening.get('reason')}", 403)
    stamp = (now or datetime.now(timezone.utc))
    count = len(list(folder.glob('*.json'))) + 1
    record = {**fields, 'author': author, 'written_by': _text(post.get('written_by'), 120) or f"{author}'s team",
              'date': stamp.date().isoformat(), 'facts': [{k: f[k] for k in ('claim', 'source', 'quote')} for f in facts],
              'intake': {k: screening.get(k) for k in ('verdict', 'reason', 'model', 'policy_sha256', 'text_sha256')},
              'posted_by': identity.get('principal'),
              'note': _text(post.get('note'), 400) or 'Written by agents; every quote checked word for word by the server; screened by the independent intake reviewer.'}
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{stamp:%Y-%m-%d}-{count:02d}-{author.split("-")[0]}.json'
    if path.exists():
        raise RuleError('A post with this name already exists; refresh and retry.', 409)
    if svg:
        record['art'] = {'title': _text(art.get('title'), 120), 'statement': _text(art.get('statement'), 400), 'file': path.stem + '.svg'}
        path.with_suffix('.svg').write_text(svg, encoding='utf-8')
    path.write_text(json.dumps(record, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    return {'id': path.stem, 'author': author, 'next_turn': next_turn(folder), 'intake': record['intake']['verdict']}
