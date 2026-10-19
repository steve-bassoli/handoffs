import io
import sys
from pathlib import Path
from urllib.error import HTTPError

import httpx
import pytest

from app import mcp_server
from scripts import relay_client

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('token', ['fixture-bearer', None])
def test_mcp_request_identity(monkeypatch, token):
    if token:
        monkeypatch.setenv('HANDOFFS_TOKEN', token)
    else:
        monkeypatch.delenv('HANDOFFS_TOKEN', raising=False)
    captured = {}
    def request(method, url, **kwargs):
        captured.update(kwargs)
        return httpx.Response(200, json={'ok': True})
    monkeypatch.setattr(mcp_server.httpx, 'request', request)
    assert mcp_server.request('POST', '/fixture', body={}, operation_id='op') == {'ok': True}
    headers = captured['headers']
    if token:
        assert headers['Authorization'] == 'Bearer ' + token
        assert 'X-Demo-User' not in headers
    else:
        assert headers['X-Demo-User'] == mcp_server.DEMO_USER
        assert 'Authorization' not in headers
    assert headers['Idempotency-Key'] == 'op'
    assert headers['X-Action-Intent'] == 'user-directed'


@pytest.mark.parametrize('error_response', [False, True])
def test_relay_token_file_stays_out_of_argv_and_output(monkeypatch, tmp_path, capsys, error_response):
    token = 'private-fixture-token'
    token_file = tmp_path / 'token.txt'
    token_file.write_text(token + '\n', encoding='utf-8')
    monkeypatch.setenv('HANDOFFS_TOKEN', 'overridden-env-token')
    argv = ['relay_client.py', 'http://127.0.0.1:8000/api/v1/fixture',
            '--user', 'steve', '--intent', 'user-directed',
            '--idempotency-key', 'fixture-op', '--token-file', str(token_file)]
    monkeypatch.setattr(sys, 'argv', argv)
    monkeypatch.setattr(sys, 'stdin', io.StringIO('{}'))
    captured = {}
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return ('echo ' + token).encode()
    class Opener:
        def open(self, request, **kwargs):
            captured.update({key.lower(): value for key, value in request.header_items()})
            if error_response:
                raise HTTPError(request.full_url, 401, 'Unauthorized', {}, io.BytesIO(token.encode()))
            return Response()
    monkeypatch.setattr(relay_client, 'build_opener', lambda *args: Opener())
    assert relay_client.main() == (1 if error_response else 0)
    assert captured['authorization'] == 'Bearer ' + token
    assert 'x-demo-user' not in captured
    assert token not in ' '.join(sys.argv)
    output = capsys.readouterr()
    assert token not in output.out + output.err
    assert 'overridden-env-token' not in output.out + output.err


def test_relay_demo_fallback_warns(monkeypatch, capsys):
    monkeypatch.delenv('HANDOFFS_TOKEN', raising=False)
    monkeypatch.setattr(sys, 'argv', ['relay_client.py', 'http://localhost/api/v1/fixture',
        '--user', 'steve', '--intent', 'user-directed', '--idempotency-key', 'op'])
    monkeypatch.setattr(sys, 'stdin', io.StringIO('{}'))
    class Opener:
        def open(self, request, **kwargs):
            headers = {key.lower(): value for key, value in request.header_items()}
            assert headers['x-demo-user'] == 'steve'
            assert 'authorization' not in headers
            raise OSError('offline')
    monkeypatch.setattr(relay_client, 'build_opener', lambda *args: Opener())
    assert relay_client.main() == 2
    assert 'WARNING' in capsys.readouterr().err


def test_browser_session_authorization_static():
    source = (ROOT / 'app/static/app.js').read_text(encoding='utf-8')
    assert "return session ? {Authorization: 'Bearer ' + session.access_token} : {'X-Demo-User': user};" in source
    assert 'const headers = identityHeaders();' in source
    # Every raw fetch that sends identity is counted; the fourth is the Gallery's picture load, which goes through
    # authenticatedFetch (same-origin only) to the existing proof route.
    # The fifth loads a Community post's picture the same way.
    assert source.count('{headers: identityHeaders()}') == 5
    assert source.count('authenticatedFetch(post.art.url, {headers: identityHeaders()})') == 1
    assert source.count('authenticatedFetch(item.download_url, {headers: identityHeaders()})') == 1
    assert "sessionStorage.setItem(SESSION_KEY," in source
    assert "sessionStorage.removeItem(SESSION_KEY)" in source
    assert 'localStorage.setItem(SESSION_KEY' not in source
    assert "response.status === 401" in source
    assert "$('user').disabled = !!session ||" in source


def test_mcp_download_uses_shared_identity_headers():
    source = (ROOT / 'app/mcp_server.py').read_text(encoding='utf-8')
    assert 'headers=identity_headers(), timeout=30, follow_redirects=False' in source
