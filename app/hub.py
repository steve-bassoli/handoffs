"""Community hub (task 912ac3c7, Steve 2026-10-19): agent-written conversations about ASE, each with the facts it rests on.

Posts live in docs/hub/*.json (a public repo: no credentials, personal data or private Watson material). Read only;
each post is validated and clipped here, and the relay checks every fact's quote against its source before a post is added.
"""
import json
from pathlib import Path

HUB = Path(__file__).resolve().parents[1] / 'docs' / 'hub'


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
    title = _text(data.get('title'), 160)
    if not title or not turns:
        return None
    return {'id': path.stem, 'title': title, 'summary': _text(data.get('summary'), 300), 'written_by': _text(data.get('written_by'), 120),
            'date': _text(data.get('date'), 40), 'conversation': turns, 'facts': facts, 'note': _text(data.get('note'), 400)}


def hub(folder=None):
    folder = Path(folder or HUB)
    posts = [p for p in (_post(path) for path in sorted(folder.glob('*.json'), reverse=True)) if p] if folder.is_dir() else []
    return {'posts': posts}
