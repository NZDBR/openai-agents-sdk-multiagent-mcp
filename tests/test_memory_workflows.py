import asyncio
from types import SimpleNamespace
import pytest
from agent_server import memory, actions


def test_native_lakebase_session_is_identity_scoped(monkeypatch):
    calls = []
    monkeypatch.setattr(memory, 'LakebaseClient', lambda **kw: calls.append(kw) or SimpleNamespace())
    monkeypatch.setattr(memory, 'AsyncDatabricksSession', lambda **kw: calls.append(kw) or kw)
    store = memory.LakebaseStore('projects/test/branches/test/endpoints/test')
    session = store.session('employee-a','conversation')
    assert calls[0]['autoscaling_endpoint'].startswith('projects/test/')
    assert session['create_tables'] is False
    assert session['session_id'] != store.session('employee-b','conversation')['session_id']
    assert session['session_id'] == store.session('employee-a','conversation')['session_id']


def test_long_term_consent_and_owner_scoping(monkeypatch):
    store = memory.LakebaseStore.__new__(memory.LakebaseStore)
    queries = []
    async def sql(query, params=()):
        queries.append((query,params))
        return [{'id':'test-memory'}]
    store.sql = sql
    async def run():
        with pytest.raises(PermissionError):
            await store.remember('owner','preference',False)
        assert queries == []
        await store.remember('owner','preference',True)
        await store.preferences('owner')
        await store.forget('owner','test-memory')
    asyncio.run(run())
    assert queries[0][1][1] == 'owner'
    assert queries[1][1] == ('owner',)
    assert queries[2][1] == ('test-memory','owner')


def test_claim_is_single_atomic_conditional_update():
    store = memory.LakebaseStore.__new__(memory.LakebaseStore)
    queries = []
    async def sql(query, params):
        queries.append((query, params))
        return [{'payload':{}, 'status':'executing'}]
    store.sql = sql
    asyncio.run(store.claim('owner','session','proposal',True))
    assert len(queries) == 1
    assert "status='pending' RETURNING" in queries[0][0]
    assert queries[0][1] == ('executing','proposal','owner','session')


def test_workflows_sdk_submission_confirmation_and_status(settings):
    submissions, queries = [], []
    class Store:
        async def sql(self, query, params):
            queries.append((query,params))
            return [{'run_id':42}]
    def submit(**kwargs):
        submissions.append(kwargs)
        return SimpleNamespace(run_id=42)
    client = SimpleNamespace(jobs=SimpleNamespace(run_now=submit, get_run=lambda **kw: SimpleNamespace(run_id=42,state=SimpleNamespace(as_dict=lambda:{'life_cycle_state':'TERMINATED'}))))
    async def run():
        with pytest.raises(PermissionError):
            await actions.background_job(Store(),client,settings,'owner','request',False)
        assert submissions == []
        first = await actions.background_job(Store(),client,settings,'owner','request',True)
        second = await actions.background_job(Store(),client,settings,'owner','request',True)
        assert first == second == {'status':'submitted','run_id':42}
        assert submissions[0] == submissions[1]
        result = await actions.background_job(Store(),client,settings,'owner','request',False,True)
        assert result['state']['life_cycle_state'] == 'TERMINATED'
        assert queries[-1][1][1] == 'owner'
    asyncio.run(run())
