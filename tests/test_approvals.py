import asyncio
from types import SimpleNamespace
import pytest
from mcp.types import Tool, CallToolResult
from agent_server import actions
from tests.fakes import FakeStore


def task():
    return {'title':'Review training', 'store_id':'TEST', 'assignee':'TEST-MANAGER', 'due_date':'2030-01-15'}


@pytest.fixture
def writer(monkeypatch):
    calls = []
    class Writer:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def list_tools(self):
            return [Tool(name='create_task', inputSchema={'type':'object', 'required':['title','store_id','assignee','due_date','idempotency_key']})]
        async def call_tool(self, name, args):
            calls.append((name, args))
            return CallToolResult(content=[], structuredContent={'task_id':'OPS-TEST'})
    monkeypatch.setattr(actions, 'McpServer', Writer)
    return calls


def test_explicit_approval_and_replay(settings, writer):
    async def run():
        store = FakeStore()
        proposal = await store.propose('employee', 'session', task())
        assert writer == []
        client = SimpleNamespace(config=SimpleNamespace(host='https://workspace.example'))
        for _ in range(2):
            result = await actions.decide_task(store, settings, client, 'employee', 'session', proposal['approval_id'], True)
            assert result['status'] == 'created'
        assert len(writer) == 1
        assert writer[0][1]['idempotency_key'] == proposal['approval_id']
    asyncio.run(run())


def test_rejection_and_cross_employee_denial(settings, writer):
    async def run():
        store = FakeStore()
        proposal = await store.propose('employee', 'session', task())
        client = SimpleNamespace(config=SimpleNamespace(host='https://workspace.example'))
        with pytest.raises(PermissionError):
            await actions.decide_task(store, settings, client, 'other', 'session', proposal['approval_id'], True)
        await actions.decide_task(store, settings, client, 'employee', 'session', proposal['approval_id'], False)
        result = await actions.decide_task(store, settings, client, 'employee', 'session', proposal['approval_id'], True)
        assert result['status'] == 'rejected'
        assert writer == []
    asyncio.run(run())


def test_ambiguous_write_is_not_retried(settings, writer, monkeypatch):
    async def fail(*args): raise TimeoutError()
    monkeypatch.setattr(actions.McpServer, 'call_tool', fail)
    async def run():
        store = FakeStore()
        proposal = await store.propose('employee', 'session', task())
        client = SimpleNamespace(config=SimpleNamespace(host='https://workspace.example'))
        with pytest.raises(RuntimeError, match='reconciliation'):
            await actions.decide_task(store, settings, client, 'employee', 'session', proposal['approval_id'], True)
        result = await actions.decide_task(store, settings, client, 'employee', 'session', proposal['approval_id'], True)
        assert result['status'] == 'needs_reconciliation'
    asyncio.run(run())


@pytest.mark.parametrize('value', [None, 'true', 1])
def test_decision_requires_boolean(settings, value):
    with pytest.raises(ValueError):
        asyncio.run(actions.decide_task(FakeStore(), settings, None, 'user', 'session', 'id', value))
