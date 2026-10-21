"""Local HTTP-handler semantics; SQL durability/concurrency are tested separately."""
import asyncio
import pytest
from agent_server import actions
from tests.fakes import FakeStore


def task():
    return dict(title='Review training',store_id='TEST',assignee='TEST-MANAGER',due_date='2030-01-15')


def test_explicit_approval_and_replay():
    async def run():
        store=FakeStore();p=await store.propose('employee','session',task())
        for _ in range(2):
            result=await actions.decide_task(store,None,'employee','session',p['approval_id'],True)
            assert result['approval_state']=='APPROVED' and result['execution_state']=='QUEUED'
        assert store.completed==[]
    asyncio.run(run())


def test_rejection_and_cross_employee_denial():
    async def run():
        store=FakeStore();p=await store.propose('employee','session',task())
        for owner,session in [('other','session'),('employee','other')]:
            with pytest.raises(PermissionError):
                await actions.decide_task(store,None,owner,session,p['approval_id'],True)
        await actions.decide_task(store,None,'employee','session',p['approval_id'],False)
        result=await actions.decide_task(store,None,'employee','session',p['approval_id'],True)
        assert result['approval_state']=='REJECTED' and store.completed==[]
    asyncio.run(run())


@pytest.mark.parametrize('value',[None,'true',1])
def test_decision_requires_boolean(settings,value):
    with pytest.raises(ValueError):
        asyncio.run(actions.decide_task(FakeStore(),settings,'user','session','id',value))
