from html import escape
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main


@pytest.fixture
def research_file(tmp_path, monkeypatch):
    path = tmp_path / 'research.md'
    path.write_text('# Research\n\n## Earlier\nOriginal record.\n\n## Latest\n<script>alert("test")</script> & private.\n', encoding='utf-8')
    monkeypatch.setattr(main, 'RESEARCH_PATH', path)
    return path


def assert_privacy_headers(response):
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert response.headers['content-security-policy'] == (
        "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; form-action 'none'")


@pytest.mark.parametrize('host', ['127.0.0.1', '::1'])
def test_loopback_reads_escaped_latest_and_full_record_without_writes(research_file, host, tmp_path):
    before = research_file.read_bytes()
    database = tmp_path / 'unused.sqlite'
    with TestClient(main.create_app(database), client=(host, 50000)) as client:
        fixtures_before = {path: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
        response = client.get('/research?path=../../private.txt', headers={'X-Demo-User': 'unknown'})
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/html')
        latest, full = response.text.split('<details>', 1)
        assert '## Earlier' not in latest
        assert escape('## Latest\n<script>alert("test")</script> & private.\n') in latest
        assert escape(research_file.read_text(encoding='utf-8')) in full
        assert '<script' not in response.text
        assert 'src=' not in response.text and '<link' not in response.text
        assert '<meta http-equiv="refresh" content="30">' in response.text
        assert 'does not query the live Codex quota meter' in response.text
        assert_privacy_headers(response)
        assert {path: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()} == fixtures_before
    assert research_file.read_bytes() == before


@pytest.mark.parametrize('host', ['192.168.1.20', '10.0.0.2', '203.0.113.2', 'fd00::2', 'unknown', None])
def test_peers_unknown_and_spoofed_claims_are_denied_before_read(monkeypatch, host):
    def no_read(*args, **kwargs):
        pytest.fail('Denied clients must not read the research file')

    monkeypatch.setattr(Path, 'read_text', no_read)
    client_address = None if host is None else (host, 50000)
    client = TestClient(main.create_app(), client=client_address)
    try:
        response = client.get('/research', headers={
            'Host': '127.0.0.1:8000', 'X-Demo-User': 'steve',
            'X-Forwarded-For': '127.0.0.1', 'X-Real-IP': '::1',
        })
    finally:
        client.close()
    assert response.status_code == 403
    assert 'private' not in response.text
    assert_privacy_headers(response)


def test_each_refresh_reads_the_current_fixed_file(research_file):
    with TestClient(main.create_app(research_file.parent / 'test.sqlite'), client=('127.0.0.1', 50000)) as client:
        assert '## Latest' in client.get('/research').text
        research_file.write_text('# Research\n\n## New snapshot\nRecorded later.\n', encoding='utf-8')
        response = client.get('/research')
        assert '## New snapshot' in response.text
        assert '## Latest' not in response.text
        assert_privacy_headers(response)
