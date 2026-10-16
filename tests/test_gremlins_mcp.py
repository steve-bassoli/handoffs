import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from test_gremlins import fixture


def test_real_gremlins_stdio_discovery_comparison_and_sabotage(tmp_path):
    async def scenario():
        parameters = StdioServerParameters(command=sys.executable, args=['-m', 'app.gremlins_mcp'],
                                           cwd=str(tmp_path), env={**os.environ, 'OPENAI_API_KEY': ''})
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                assert set(tools) == {'mimic', 'saboteur', 'witness_report'}
                assert all(tool.annotations.readOnlyHint and not tool.annotations.openWorldHint for tool in tools.values())
                payload = fixture()
                result = await client.call_tool('mimic', {'payload': payload})
                assert not result.isError and result.structuredContent['verdict'] == 'pass'
                result = await client.call_tool('saboteur', {'payload': payload})
                assert not result.isError and result.structuredContent['detector_verified']
                result = await client.call_tool('witness_report', {'payload': payload})
                assert not result.isError and result.structuredContent['scope'] == 'SIM'
                assert result.structuredContent['sha256']
                result = await client.call_tool('mimic', {'payload': {**payload, 'scope': 'LIVE'}})
                assert result.isError
    asyncio.run(scenario())
