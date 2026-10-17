import asyncio
import httpx
import pytest
from starlette.testclient import TestClient
from scripts.validate_demo_stack import client, verify, ARGUMENTS, READ_TOOLS
from tests.demo_e2e_validation import scenarios

def test_real_protocol_and_complete_application_scenarios(demo_stack):
    async def run():
        protocol=await verify(demo_stack)
        assert protocol['real_http_processes']==3
        result=await scenarios(demo_stack)
        assert result['task']['counts']==dict(before=1,after_proposal=1,after_approval=2,after_replay=2)
    asyncio.run(run())

@pytest.mark.parametrize('cap,tool',[(cap,tool) for cap,tools in READ_TOOLS.items() for tool in tools])
def test_each_http_read_tool_and_unknown_arguments(demo_stack,cap,tool):
    async def run():
        async with client(demo_stack,cap) as raw:
            assert not (await raw.call_tool(tool,ARGUMENTS[tool])).isError
            assert (await raw.call_tool(tool,dict(ARGUMENTS[tool],unexpected='rejected'))).isError
    asyncio.run(run())

def test_forbidden_tools_and_authentication(demo_stack):
    async def run():
        for cap,name in [('storetime','update_schedule'),('storetime','create_task'),('confluence','invent_policy'),('opstask','diagnose_training_gap')]:
            async with client(demo_stack,cap) as raw: assert (await raw.call_tool(name,{})).isError
    asyncio.run(run())
    with httpx.Client(trust_env=False) as http:
        assert http.post(demo_stack.urls['opstask'],json={}).status_code==401

def test_readiness_failure_is_distinct_from_liveness():
    from storetime.server import build
    class Broken:
        def ready(self): raise ValueError('broken fixture')
    _,app=build(Broken(),read_token='r'*32)
    with TestClient(app()) as http:
        assert http.get('/health').status_code==200
        assert http.get('/ready').status_code==503
