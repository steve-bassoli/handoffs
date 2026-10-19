"""Gallery tab (Steve, 2026-10-19: "I want to see bot creativity in our house"): image proofs attached to tasks."""
import base64
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.prototype as prototype
from app.main import create_app
from conftest import post_task, write

STATIC = Path(__file__).resolve().parents[1] / 'app' / 'static'
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(prototype, 'RELEASE_MARKER', tmp_path / 'RELEASED')
    monkeypatch.setenv('HANDOFFS_DEMO_IDENTITY', 'allow')
    monkeypatch.setenv('HANDOFFS_INTAKE_SCREEN', 'observe')
    with TestClient(create_app(tmp_path / 'gallery.sqlite')) as client:
        yield client


def attach(client, task_id, filename, media_type, content, description):
    upload = {'filename': filename, 'media_type': media_type, 'content_base64': base64.b64encode(content).decode(), 'description': description}
    assert write(client, f'/tasks/{task_id}/proofs', upload).status_code == 200


def test_gallery_lists_images_newest_first_and_skips_text(client):
    task_id = post_task(client, gold=10).json()['id']
    assert write(client, f'/tasks/{task_id}/take').status_code == 200
    write(client, f'/tasks/{task_id}/profile', {'validation_scope': 'SIM', 'migration_stage': 'WRAP', 'baseline_revision': 'a',
                                                'candidate_revision': 'b', 'environment': 'synthetic'})
    attach(client, task_id, 'room-to-pass.png', 'image/png', PNG, 'bob-the-architect: "Room to Pass".')
    attach(client, task_id, 'notes.txt', 'text/plain', b'Synthetic notes', 'Text is not art for the gallery.')
    attach(client, task_id, 'shelter.png', 'image/png', PNG, 'sue-the-architect: "A Door Is Not a Breach".')
    items = client.get('/api/v1/gallery', headers={'X-Demo-User': 'steve'}).json()['items']
    assert [i['filename'] for i in items] == ['shelter.png', 'room-to-pass.png']
    assert items[0]['task_id'] == task_id and items[0]['description'].startswith('sue-the-architect')
    # The listing carries no image bytes; each picture loads through the existing proof route.
    assert 'content_base64' not in items[0]
    picture = client.get(items[0]['download_url'], headers={'X-Demo-User': 'steve'})
    assert picture.status_code == 200 and picture.content == PNG and picture.headers['content-type'] == 'image/png'


def test_gallery_tab_follows_bob_and_sue():
    for page in ('index.html', 'dashboard.html'):
        nav = re.search(r'<nav aria-label="Workspace"[^>]*>(.*?)</nav>', (STATIC / page).read_text(encoding='utf-8'), re.S).group(1)
        assert re.findall(r'data-view="(\w+)"', nav)[:4] == ['signoffs', 'bobsue', 'gallery', 'hub'], page
    script = (STATIC / 'app.js').read_text(encoding='utf-8')
    assert "await api('/gallery')" in script and "authenticatedFetch(item.download_url, {headers: identityHeaders()})" in script
