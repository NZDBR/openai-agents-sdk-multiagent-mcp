import asyncio
import json
from contextlib import AsyncExitStack
from dataclasses import replace
from types import SimpleNamespace
import pytest
from agents import Runner, RunConfig
from databricks_openai.agents import McpServer
from mcp.types import Tool, CallToolResult
from agent_server.agent import build_agent, Turn, Answer
from tests.fakes import FakeStore, ScriptedModel, call, message


@pytest.fixture
def transports(monkeypatch):
    names = {'genie':'query_metrics', 'storetime':'read_schedule', 'opstask':'list_followups', 'confluence':'search_policy'}
    calls = []
    async def enter(self): return self
    async def exit(self, *args): pass
    async def tools(self, *args, **kwargs):
        return [Tool(name=names[self.capability], inputSchema={'type':'object','properties':{},'additionalProperties':False})]
    async def invoke(self, name, arguments, meta=None):
        calls.append((self.capability, name))
        return CallToolResult(content=[], structuredContent={'fixture':'test-only store evidence','source_url':'https://test.example/source'})
    monkeypatch.setattr(McpServer, '__aenter__', enter)
    monkeypatch.setattr(McpServer, '__aexit__', exit)
    monkeypatch.setattr(McpServer, 'list_tools', tools)
    monkeypatch.setattr(McpServer, 'call_tool', invoke)
    return calls


def test_real_sdk_routes_to_scoped_mcp_specialist(settings, transports):
    model = ScriptedModel([
        [call('genie_one', {'input':'Compare training completion'})],
        [call('query_metrics', {})],
        [message('Test-only metrics from the governed source.')],
        [message(json.dumps({'answer':'Comparison from governed metrics.', 'citations':['https://test.example/source'], 'is_policy':False}))],
    ])
    async def run():
        turn = Turn()
        store = FakeStore()
        async with AsyncExitStack() as stack:
            agent = await build_agent(stack, replace(settings, model=model), SimpleNamespace(config=SimpleNamespace(host='https://workspace.example')), store, 'employee', 'conversation', turn)
            assert [t.name for t in agent.tools] == ['genie_one','storetime','opstask_lookup','confluence','propose_task']
            result = await Runner.run(agent, 'Compare training completion', session=store.history, run_config=RunConfig(tracing_disabled=True))
        assert result.final_output_as(Answer).answer == 'Comparison from governed metrics.'
        assert transports == [('genie','query_metrics')]
        assert turn.evidence.calls[0]['capability'] == 'genie'
        assert store.history.items  # Actual SDK persisted the turn through its Session protocol.
        assert model.seen_tools[1] == ['query_metrics']
    asyncio.run(run())


def test_model_can_only_propose_never_mutate(settings, transports):
    payload = {'title':'Review training', 'store_id':'TEST', 'assignee':'TEST-MANAGER', 'due_date':'2030-01-15'}
    model = ScriptedModel([
        [call('propose_task', payload)],
        [message(json.dumps({'answer':'Task proposed; review and approve it before creation.', 'citations':[], 'is_policy':False}))],
    ])
    async def run():
        turn, store = Turn(), FakeStore()
        async with AsyncExitStack() as stack:
            agent = await build_agent(stack, replace(settings, model=model), SimpleNamespace(config=SimpleNamespace(host='https://workspace.example')), store, 'employee', 'conversation', turn)
            await Runner.run(agent, 'Create a task', run_config=RunConfig(tracing_disabled=True))
        assert len(turn.proposals) == 1
        assert turn.proposals[0]['status'] == 'pending'
        assert transports == []
        assert not any('create_task' in tools for tools in model.seen_tools)
    asyncio.run(run())


def test_unsupported_policy_is_replaced_in_response_and_session(settings, transports, monkeypatch):
    import agent_server.agent as module
    from mlflow.types.responses import ResponsesAgentRequest
    model = ScriptedModel([[message(json.dumps({'answer':'Invented company policy.', 'citations':[], 'is_policy':False}))]])
    store = FakeStore()
    client = SimpleNamespace(config=SimpleNamespace(host='https://workspace.example'))
    async def employee(): return 'verified-employee', client
    monkeypatch.setattr(module,'employee',employee)
    monkeypatch.setattr(module.Settings,'load',lambda: replace(settings,model=model))
    monkeypatch.setattr(module,'store_for',lambda _:store)
    # The actual SDK run is retained; disable only external OpenAI trace export.
    original = Runner.run
    async def run(*args,**kwargs):
        kwargs['run_config'] = RunConfig(tracing_disabled=True)
        return await original(*args,**kwargs)
    monkeypatch.setattr(module.Runner,'run',run)
    result = asyncio.run(module.invoke_handler(ResponsesAgentRequest(input=[{'role':'user','content':'What is the company policy?'}])))
    assert 'cannot establish' in result.output[0].content[0]['text']
    assert 'cannot establish' in store.history.items[-1]['content']
    assert not any('Invented company policy.' in str(item) for item in store.history.items)
