import asyncio
from types import SimpleNamespace
import pytest
from mcp.types import Tool, CallToolResult, TextContent
from databricks_openai.agents import McpServer
from agent_server.governance import Evidence, GovernedMcpServer, enforce_policy
from agent_server.agent import Answer


def server(capability, allowed=()):
    return GovernedMcpServer(capability=capability, allowed=allowed, evidence=Evidence(),
                             url='https://workspace.example/api/2.0/mcp/genie/test',
                             workspace_client=SimpleNamespace(), name=capability)


@pytest.mark.parametrize('capability,allowed,tool', [
    ('genie', (), 'create_task'),
    ('storetime', ('read_schedule',), 'update_schedule'),
    ('opstask', ('list_followups',), 'create_task'),
    ('confluence', ('search_policy',), 'invent_policy'),
])
def test_direct_dispatch_blocks_forbidden_tools(capability, allowed, tool, monkeypatch):
    async def must_not_call(*args, **kwargs):
        pytest.fail('Forbidden call reached the transport')
    monkeypatch.setattr(McpServer, 'call_tool', must_not_call)
    with pytest.raises(PermissionError):
        asyncio.run(server(capability, allowed).call_tool(tool, {}))


def test_read_allowlist_rejects_mutations():
    with pytest.raises(ValueError):
        server('storetime', ('update_schedule',))


def test_model_tool_listing_excludes_writes(monkeypatch):
    async def tools(*args, **kwargs):
        return [Tool(name='query_genie', inputSchema={}), Tool(name='create_task', inputSchema={})]
    monkeypatch.setattr(McpServer, 'list_tools', tools)
    listed = asyncio.run(server('genie').list_tools())
    assert [t.name for t in listed] == ['query_genie']


def test_missing_deployed_tool_fails_closed(monkeypatch):
    async def tools(*args, **kwargs):
        return [Tool(name='unexpected', inputSchema={})]
    monkeypatch.setattr(McpServer, 'list_tools', tools)
    with pytest.raises(ValueError):
        asyncio.run(server('storetime', ('read_schedule',)).list_tools())


def test_confluence_cannot_deliver_unsourced_policy():
    answer = Answer(answer='Company policy requires 8 hours.', citations=['https://invented.example/policy'], is_policy=True)
    evidence = Evidence()
    assert 'cannot establish' in enforce_policy(answer, evidence)
    evidence.record('genie', 'query', CallToolResult(content=[], structuredContent={'url': 'https://invented.example/policy'}))
    assert 'cannot establish' in enforce_policy(answer, evidence)
    evidence.record('confluence', 'search_policy', CallToolResult(content=[], structuredContent={'source_url': 'https://real.example/policy', 'text': 'Protected training time must follow the approved coverage policy.'}))
    assert 'cannot establish' in enforce_policy(answer, evidence)
    answer.citations = ['https://real.example/policy']
    assert 'cannot establish' in enforce_policy(answer, evidence)
    answer.policy_quotes = ['Protected training time must follow the approved coverage policy.']
    delivered = enforce_policy(answer, evidence)
    assert answer.policy_quotes[0] in delivered
    assert 'Company policy requires 8 hours.' not in delivered
    answer.policy_quotes = ['An invented mandatory eight-hour rule applies to every employee.']
    assert 'cannot establish' in enforce_policy(answer, evidence)


def test_failed_retrieval_never_establishes_policy():
    evidence = Evidence()
    evidence.record('confluence', 'search', CallToolResult(content=[], isError=True, structuredContent={'url': 'https://real.example'}))
    assert evidence.calls == []
