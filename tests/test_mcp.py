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
            assert set(tools) == {'list_bounties', 'get_bounty', 'get_bounty_context', 'get_my_stats', 'post_bounty', 'take_bounty', 'deliver_pr'}
            assert tools['list_bounties'].annotations.readOnlyHint is True
            assert tools['get_bounty'].annotations.readOnlyHint is True
            for name in ('get_my_stats', 'post_bounty', 'take_bounty', 'deliver_pr'):
                assert tools[name].annotations.readOnlyHint is False
            assert 'operation_id' in tools['post_bounty'].inputSchema['required']
            assert (await call(requester, 'get_my_stats'))['available_gold'] == 1000
            arguments = {'title': 'MCP-only fixture bounty', 'goal': 'Prove the bridge',
                         'criteria': ['Return PR evidence'], 'gold': 150, 'operation_id': 'fund-once', 'complexity': 'LOW'}
            bounty = await call(requester, 'post_bounty', arguments)
            assert (await call(requester, 'post_bounty', arguments))['id'] == bounty['id']
            assert len((await call(worker, 'list_bounties'))['items']) == 1
            assert (await call(worker, 'get_bounty', {'bounty_id': bounty['id']}))['criteria'] == arguments['criteria']
            assert (await call(worker, 'take_bounty', {'bounty_id': bounty['id'], 'operation_id': 'take-once'}))['claimant'] == 'nate'
            with httpx.Client(base_url=live_api) as fixture_client:
                verified_proof(fixture_client, bounty['id'], 'nate')
            delivery = {'bounty_id': bounty['id'], 'pr_url': 'https://github.com/example/source/pull/18',
                        'evidence': 'MCP fixture proof; no real PR created', 'operation_id': 'deliver-once'}
            paid = await call(worker, 'deliver_pr', delivery)
            assert paid['status'] == 'settled' and paid['deliveries'][0]['simulated'] == 1
            assert (await call(worker, 'deliver_pr', delivery)) == paid
            assert (await call(worker, 'get_my_stats'))['available_gold'] == 1150
            arguments.update(gold=1100, operation_id='repost-earned-gold')
            await call(worker, 'post_bounty', arguments)
            stats = await call(worker, 'get_my_stats')
            assert (stats['available_gold'], stats['reserved_gold']) == (50, 1100)
            own = await call(requester, 'post_bounty', {**arguments, 'gold': 10, 'operation_id': 'own-work'})
            claimed = await call(requester, 'take_bounty', {'bounty_id': own['id'], 'operation_id': 'self-claim'})
            assert claimed['claimant'] == 'steve' and claimed['status'] == 'working'
            invalid = await worker.call_tool('list_bounties', {'limit': 0})
            assert invalid.isError
            missing = await worker.call_tool('get_bounty', {'bounty_id': 'missing'})
            assert missing.isError and '404' in missing.content[0].text
    asyncio.run(scenario())


def test_stdio_unavailable_service_returns_tool_error(tmp_path):
    with socket.socket() as closed_socket:
        closed_socket.bind(('127.0.0.1', 0))
        unavailable = f'http://127.0.0.1:{closed_socket.getsockname()[1]}'
        async def scenario():
            async with session(unavailable, 'steve', tmp_path) as client:
                result = await client.call_tool('list_bounties')
                assert result.isError and 'unreachable' in result.content[0].text
        asyncio.run(scenario())
