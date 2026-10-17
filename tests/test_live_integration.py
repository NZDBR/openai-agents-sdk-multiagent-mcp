"""Opt-in, read-only or cleanup-scoped workspace checks. Never create external tasks."""
import asyncio
import os
from uuid import uuid4
import pytest


def configured(*names):
    return os.getenv('RUN_DATABRICKS_INTEGRATION') == '1' and all(os.getenv(n) and '<' not in os.getenv(n) for n in names)


@pytest.mark.integration
@pytest.mark.skipif(not configured('DATABRICKS_HOST','GENIE_SPACE_ID'),reason='Live workspace/Genie settings absent or integration tests not opted in')
def test_live_managed_genie_discovery():
    from databricks.sdk import WorkspaceClient
    from databricks_openai.agents import McpServer
    async def run():
        client = WorkspaceClient()
        client.current_user.me()
        async with McpServer(url=client.config.host.rstrip('/') + '/api/2.0/mcp/genie/' + os.environ['GENIE_SPACE_ID'],workspace_client=client) as server:
            assert await server.list_tools()
    asyncio.run(run())


@pytest.mark.integration
@pytest.mark.skipif(not configured('DATABRICKS_HOST','LAKEBASE_ENDPOINT'),reason='Live Lakebase settings absent or integration tests not opted in')
def test_live_lakebase_session_roundtrip():
    from databricks_openai.agents import AsyncDatabricksSession
    async def run():
        session = AsyncDatabricksSession(session_id='integration-'+uuid4().hex,autoscaling_endpoint=os.environ['LAKEBASE_ENDPOINT'])
        try:
            await session.add_items([{'role':'user','content':'Integration session persistence probe'}])
            assert (await session.get_items())[-1]['content'] == 'Integration session persistence probe'
        finally:
            await session.clear_session()
    asyncio.run(run())
