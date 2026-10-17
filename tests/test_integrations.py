import pytest
from app import integrations


def test_tool_allowlist_required(monkeypatch):
    monkeypatch.delenv('GENIE_MCP_TOOLS', raising=False)
    with pytest.raises(ValueError):
        integrations.tool_names('GENIE_MCP')
    monkeypatch.setenv('GENIE_MCP_TOOLS', 'metrics, completion')
    assert integrations.tool_names('GENIE_MCP') == ['metrics', 'completion']


@pytest.mark.parametrize('url', ['http://example.com', 'https://user:pass@example.com', 'not-a-url'])
def test_invalid_endpoint_rejected(monkeypatch, url):
    monkeypatch.setenv('TEST_URL', url)
    with pytest.raises(ValueError):
        integrations.https_url('TEST_URL')


def test_endpoint_specific_credentials(monkeypatch):
    monkeypatch.setenv('GENIE_MCP_URL', 'https://example.com/mcp')
    monkeypatch.setenv('GENIE_MCP_TOKEN', 'test-only')
    monkeypatch.setenv('STORETIME_MCP_URL', 'https://example.com/time')
    monkeypatch.delenv('STORETIME_MCP_TOKEN', raising=False)
    assert integrations.mcp_params('GENIE_MCP')['headers'] == {'Authorization': 'Bearer test-only'}
    assert integrations.mcp_params('STORETIME_MCP')['headers'] == {}


def test_workflow_and_verified_identity(monkeypatch):
    import asyncio
    import httpx
    import json
    from starlette.requests import Request
    calls = []
    def handler(request):
        calls.append(request)
        if request.method == 'GET':
            assert request.headers['Authorization'] == 'Bearer forwarded-test-token'
            return httpx.Response(200, json={'id': 'employee-42'})
        payload = json.loads(request.content)
        assert payload == {'job_id': 123, 'idempotency_token': 'request-key'}
        return httpx.Response(200, json={'run_id': 99})
    original = httpx.AsyncClient
    monkeypatch.setattr(integrations.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setenv('DATABRICKS_HOST', 'https://workspace.example.com')
    monkeypatch.setenv('DATABRICKS_WORKFLOW_JOB_ID', '123')
    monkeypatch.setenv('DATABRICKS_WORKFLOW_TOKEN', 'workflow-test-token')
    request = Request({'type': 'http', 'headers': [(b'x-forwarded-access-token', b'forwarded-test-token')]})
    assert asyncio.run(integrations.employee_id(request)) == 'employee-42'
    assert asyncio.run(integrations.run_workflow('request-key')) == 99
    assert len(calls) == 2


def test_unverified_identity_is_rejected():
    import asyncio
    from starlette.requests import Request
    with pytest.raises(ValueError):
        asyncio.run(integrations.employee_id(Request({'type': 'http', 'headers': []})))


def test_task_write_contract(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    calls = []
    class Server:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def call_tool(self, name, args):
            calls.append((name, args))
            return SimpleNamespace(isError=False, structuredContent={'task_id': 'OPS-123'})
    monkeypatch.setattr(integrations, 'MCPServerStreamableHttp', Server)
    monkeypatch.setenv('OPSTASK_WRITE_MCP_URL', 'https://example.com/mcp')
    monkeypatch.setenv('OPSTASK_WRITE_TOOL', 'approved_create')
    assert asyncio.run(integrations.create_task('Training follow-up', 'approval-1')) == 'OPS-123'
    assert calls == [('approved_create', {'title': 'Training follow-up', 'idempotency_key': 'approval-1'})]


def test_live_orchestration_isolates_specialists(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    import agents
    import agents.mcp
    from app.main import live_answer
    servers, specialists = [], []
    class Server:
        def __init__(self, **kwargs):
            servers.append(kwargs)
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
    class Agent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
        def as_tool(self, **kwargs):
            specialists.append(self.kwargs)
            return kwargs
    class Runner:
        @staticmethod
        async def run(agent, inputs):
            assert len(agent.kwargs['tools']) == 4
            assert 'mcp_servers' not in agent.kwargs
            assert inputs[-1]['content'] == 'Compare stores'
            return SimpleNamespace(final_output='comparison')
    monkeypatch.setattr(agents, 'Agent', Agent)
    monkeypatch.setattr(agents, 'Runner', Runner)
    monkeypatch.setattr(agents.mcp, 'MCPServerStreamableHttp', Server)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-only')
    monkeypatch.setenv('LAKEBASE_DSN', 'not-used-in-this-test')
    monkeypatch.delenv('MLFLOW_TRACKING_URI', raising=False)
    for prefix in ['GENIE_MCP', 'STORETIME_MCP', 'OPSTASK_READ_MCP', 'CONFLUENCE_MCP']:
        monkeypatch.setenv(prefix + '_URL', 'https://example.com/mcp')
        monkeypatch.setenv(prefix + '_TOOLS', 'read_' + prefix.lower())
    assert asyncio.run(live_answer('Compare stores', [])) == 'comparison'
    assert len(servers) == 4
    assert all(len(s['mcp_servers']) == 1 for s in specialists)
    assert servers[2]['tool_filter']['allowed_tool_names'] == ['read_opstask_read_mcp']
