import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from contextlib import asynccontextmanager

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from conftest import FixtureProofReviewer, verified_proof
from app.main import create_app

# Deprecated aliases kept so already-connected agents keep working after the bounty -> task rename.
LEGACY_TOOLS = {'post_' + 'bounty', 'take_' + 'bounty', 'get_' + 'bounty', 'list_' + 'bounties', 'edit_' + 'bounty', 'get_' + 'bounty_context'}


def fixture_app():
    return create_app(proof_reviewer=FixtureProofReviewer())


@pytest.fixture
def live_api(tmp_path):
    with socket.socket() as socket_:
        socket_.bind(('127.0.0.1', 0))
        port = socket_.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    environment = {**os.environ, 'HANDOFFS_DB': str(tmp_path / 'isolated.sqlite'),
                   'PYTHONPATH': os.pathsep.join((str(Path(__file__).resolve().parents[1]),
                       str(Path(__file__).parent.resolve()), os.environ.get('PYTHONPATH', '')))}
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'test_mcp:fixture_app', '--factory', '--host', '127.0.0.1', '--port', str(port)],
                               cwd=tmp_path, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError('Isolated test API exited')
            try:
                if httpx.get(url + '/health', timeout=1).status_code == 200:
                    break
            except httpx.RequestError:
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError('Isolated test API did not start')
        yield url
    finally:
        process.terminate()
        process.wait(timeout=5)


@asynccontextmanager
async def session(url, user, cwd):
    parameters = StdioServerParameters(command=sys.executable, args=['-m', 'app.mcp_server'], cwd=str(cwd),
                                       env={**os.environ, 'HANDOFFS_URL': url, 'HANDOFFS_DEMO_USER': user,
                                            'PYTHONPATH': str(Path(__file__).resolve().parents[1]) + os.pathsep + os.environ.get('PYTHONPATH', '')})
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            yield client


async def call(client, name, arguments=None):
    result = await client.call_tool(name, arguments or {})
    assert not result.isError, result.content
    assert result.structuredContent is not None
    return result.structuredContent


def test_stdio_discovery_and_two_user_economy(live_api, tmp_path):
    async def scenario():
        async with session(live_api, 'steve', tmp_path) as requester, session(live_api, 'nate', tmp_path) as worker:
            tools = {tool.name: tool for tool in (await requester.list_tools()).tools}
            assert set(tools) == {'list_tasks', 'task_summary', 'get_task', 'get_task_context', 'get_my_stats', 'post_task', 'edit_task', 'checkpoint_task', 'take_task', 'deliver_pr', 'close_task_human'} | LEGACY_TOOLS
            assert tools['list_tasks'].annotations.readOnlyHint is True
            assert tools['task_summary'].annotations.readOnlyHint is True
            assert (await call(requester, 'task_summary'))['total'] == 0
            assert tools['get_task'].annotations.readOnlyHint is True
            for name in ('get_my_stats', 'post_task', 'checkpoint_task', 'take_task', 'deliver_pr'):
                assert tools[name].annotations.readOnlyHint is False
            assert 'operation_id' in tools['post_task'].inputSchema['required']
            assert {'task_id', 'notes', 'operation_id'} <= set(tools['checkpoint_task'].inputSchema['required'])
            assert (await call(requester, 'get_my_stats'))['available_gold'] == 1000
            arguments = {'title': 'MCP-only fixture task', 'goal': 'Prove the bridge',
                         'criteria': ['Return PR evidence'], 'gold': 150, 'operation_id': 'fund-once', 'complexity': 'LOW'}
            task = await call(requester, 'post_task', arguments)
            assert (await call(requester, 'post_task', arguments))['id'] == task['id']
            assert len((await call(worker, 'list_tasks'))['items']) == 1
            assert (await call(worker, 'get_task', {'task_id': task['id']}))['criteria'] == arguments['criteria']
            assert (await call(worker, 'get_task', {'task_id': task['id'][:8]}))['id'] == task['id']
            summary = await call(worker, 'task_summary')
            assert summary['counts'] == {'open': 1}
            assert summary['active'][0]['id'] == task['id']
            assert (await call(worker, 'take_task', {'task_id': task['id'], 'operation_id': 'take-once'}))['claimant'] == 'nate'
            with httpx.Client(base_url=live_api) as fixture_client:
                verified_proof(fixture_client, task['id'], 'nate')
            delivery = {'task_id': task['id'], 'pr_url': 'https://github.com/example/source/pull/18',
                        'evidence': 'MCP fixture proof; no real PR created', 'operation_id': 'deliver-once'}
            paid = await call(worker, 'deliver_pr', delivery)
            assert paid['status'] == 'settled' and paid['deliveries'][0]['simulated'] == 1
            assert (await call(worker, 'deliver_pr', delivery)) == paid
            assert (await call(worker, 'get_my_stats'))['available_gold'] == 1150
            arguments.update(gold=1100, operation_id='repost-earned-gold')
            await call(worker, 'post_task', arguments)
            stats = await call(worker, 'get_my_stats')
            assert (stats['available_gold'], stats['reserved_gold']) == (50, 1100)
            own = await call(requester, 'post_task', {**arguments, 'gold': 10, 'operation_id': 'own-work'})
            claimed = await call(requester, 'take_task', {'task_id': own['id'], 'operation_id': 'self-claim'})
            assert claimed['claimant'] == 'steve' and claimed['status'] == 'working'
            processing = claimed['processing']
            assert processing['state'] == 'context-ready'
            assert Path(processing['package_path']).is_file()
            assert processing['mode'] == 'manual' and processing['model'] == 'gpt-6.1-sol'
            assert 'no provider request' in processing['executor']
            assert 'context.md' in processing['documents']
            for operation in ['self-claim', 'another-accept-same-task']:
                replay = await call(requester, 'take_task', {'task_id': own['id'], 'operation_id': operation})
                assert replay['processing']['execution_id'] == processing['execution_id']
                assert replay['processing']['reused'] is True
                assert sum(event['kind'] == 'taken' for event in replay['events']) == 1
                assert replay['ai_run'] is None
            invalid = await worker.call_tool('list_tasks', {'limit': 0})
            assert invalid.isError
            missing = await worker.call_tool('get_task', {'task_id': 'missing'})
            assert missing.isError and '404' in missing.content[0].text
    asyncio.run(scenario())


def test_claim_reports_package_failure_and_resumes_same_claim(client, monkeypatch, tmp_path):
    from app import mcp_server
    from conftest import post_task
    monkeypatch.setenv('HANDOFFS_WORK_ROOT', str(tmp_path / 'work'))
    monkeypatch.setattr(mcp_server, 'DEMO_USER', 'steve')
    task = post_task(client).json()['id']
    def request(method, path, **kwargs):
        response = client.request(method, '/api/v1' + path, json=kwargs.get('body'),
            headers={'X-Demo-User': 'steve', 'Idempotency-Key': kwargs.get('operation_id', '')})
        if not response.is_success:
            raise RuntimeError(f'HANDOFFS {response.status_code}: {response.json()["detail"]}')
        return response.json()
    monkeypatch.setattr(mcp_server, 'request', request)
    class FailedDownload:
        def __enter__(self):
            raise httpx.ConnectError('offline')
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(mcp_server.httpx, 'stream', lambda *a, **k: FailedDownload())
    result = mcp_server.take_task(task, 'claim-without-package')
    assert result['claimant'] == 'steve' and result['processing']['state'] == 'blocked'
    assert 'download failed' in result['processing']['error']
    assert 'same operation_id' in result['processing']['next_action']
    assert not list(tmp_path.rglob('input.zip'))
    from contextlib import contextmanager
    raw = client.get(f'/api/v1/tasks/{task}/artifacts/download', headers={'X-Demo-User': 'steve'}).content
    @contextmanager
    def recovered(*args, **kwargs):
        yield httpx.Response(200, request=httpx.Request('GET', 'http://fixture'), content=raw)
    monkeypatch.setattr(mcp_server.httpx, 'stream', recovered)
    resumed = mcp_server.take_task(task, 'claim-without-package')
    assert resumed['processing']['state'] == 'context-ready'
    assert sum(event['kind'] == 'taken' for event in resumed['events']) == 1
    assert resumed['ai_run'] is None


def test_stdio_unavailable_service_returns_tool_error(tmp_path):
    with socket.socket() as closed_socket:
        closed_socket.bind(('127.0.0.1', 0))
        unavailable = f'http://127.0.0.1:{closed_socket.getsockname()[1]}'
        async def scenario():
            async with session(unavailable, 'steve', tmp_path) as client:
                result = await client.call_tool('list_tasks')
                assert result.isError and 'unreachable' in result.content[0].text
        asyncio.run(scenario())
