"""Reconstructed local evidence harness. Model/Genie/identity/memory are fixtures.

Business MCP traffic, SDK orchestration and application handlers are real.
No remote workspace requests, production mock fallback or browser automation.
"""
import asyncio
import argparse
from contextlib import ExitStack
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import mlflow
from agents import set_tracing_disabled, Runner, RunConfig
from databricks_openai.agents import McpServer
from mcp.types import Tool, CallToolResult
from mlflow.types.responses import ResponsesAgentRequest
import agent_server.agent as application
from scripts.validate_demo_stack import DemoStack, verify, client, demo_settings, WINDOW
from tests.fakes import FakeStore, ScriptedModel, call, message

ROOT=Path(__file__).resolve().parents[1]
class FixtureGenie(McpServer):
    def __init__(self,evidence):
        super().__init__(url='https://fixture.invalid/api/2.0/mcp/genie/test',name='fixture-genie',
                         workspace_client=SimpleNamespace(config=SimpleNamespace(host='https://fixture.invalid')))
        self.evidence=evidence
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    async def list_tools(self,*args,**kwargs):
        return [Tool(name='query_metrics',inputSchema={'type':'object','properties':{},'additionalProperties':False})]
    async def call_tool(self,name,arguments=None,meta=None):
        assert name=='query_metrics'
        result=CallToolResult(content=[],structuredContent={'synthetic':True,'mode':'demo','source_id':'TEST-ONLY-GENIE-METRICS',
            'store_id':'DEMO-001','scheduled_hours':6,'completed_hours':3,'completion_percent':50})
        self.evidence.record('genie',name,result);return result

def answer(text,citations=None,policy=False,quotes=None):
    return [message(json.dumps(dict(answer=text,citations=citations or [],is_policy=policy,policy_quotes=quotes or [])))]
async def invoke(outputs,store,text,conversation='demo-validation',decision=None):
    model=ScriptedModel(outputs);actual_read=application.user_mcp_client
    def read(cap,settings,user,evidence):
        return FixtureGenie(evidence) if cap=='genie' else actual_read(cap,settings,user,evidence)
    async def employee(): return 'fixture-employee',SimpleNamespace(config=SimpleNamespace(host='https://fixture.invalid'))
    actual_run=Runner.run
    async def local_run(*args,**kwargs):
        kwargs['run_config']=RunConfig(tracing_disabled=True)
        return await actual_run(*args,**kwargs)
    with ExitStack() as stack:
        stack.enter_context(patch.object(application.Runner,'run',local_run))
        stack.enter_context(patch.object(application.Settings,'load',return_value=replace(demo_settings(),model=model)))
        stack.enter_context(patch.object(application,'employee',employee))
        stack.enter_context(patch.object(application,'store_for',return_value=store))
        stack.enter_context(patch.object(application,'user_mcp_client',read))
        result=await application.invoke_handler(ResponsesAgentRequest(input=[{'role':'user','content':text}],
              custom_inputs={'session_id':conversation,**(decision or {})}))
    assert all('create_task' not in names for names in model.seen_tools)
    return {'response':result.model_dump(mode='json'),'model_tools':model.seen_tools}

async def scenarios(stack):
    with stack.agent_environment():
        async with client(stack,'storetime') as reader:
            result=await reader.call_tool('diagnose_training_gap',WINDOW)
            assert not result.isError
            diagnosis=result.structuredContent['data']['diagnostic']
        assert diagnosis['hours']['scheduled_hours']==6 and diagnosis['hours']['completed_hours']==3
        assert diagnosis['hours']['converted_hours']==2 and diagnosis['completion_gap_hours']==3
        training=await invoke([
            [call('genie_one',{'input':'Compare DEMO-001 training completion'})],[call('query_metrics',{})],
            [message('Synthetic test-only Genie metrics: six scheduled, three completed.')],
            [call('storetime',{'input':'Diagnose DEMO-001 training for 2026-01-05 through 2026-01-06'})],
            [call('diagnose_training_gap',WINDOW)],[message(json.dumps(diagnosis))],
            answer('Synthetic demo: 6 scheduled hours, 3 completed (50%), 3-hour gap; 2 hours converted to coverage. Evidence blocks B-1 and B-2; recorded reasons do not prove every incomplete hour.',['TEST-ONLY-GENIE-METRICS'])
        ],FakeStore(),'Explain the training gap','training-validation')
        assert [(c['capability'],c['tool']) for c in training['response']['custom_outputs']['tool_calls']]==[('genie','query_metrics'),('storetime','diagnose_training_gap')]
        async def tasks():
            async with client(stack,'opstask') as reader:
                result=await reader.call_tool('list_followups',{'store_id':'DEMO-001','limit':100})
                assert not result.isError
                return result.structuredContent['data']['tasks']
        payload={'title':'Review synthetic training gap','store_id':'DEMO-001','assignee':'DEMO-MANAGER','due_date':'2030-01-15'}
        store=FakeStore();baseline=await tasks()
        proposed=await invoke([[call('propose_task',payload)],answer('Synthetic task proposed. Explicit approval is required.')],store,'Propose training follow-up','task-validation')
        approval_id=proposed['response']['custom_outputs']['proposals'][0]['approval_id']
        after_proposal=await tasks();assert after_proposal==baseline
        decision={'action':'task_decision','approval_id':approval_id,'approve':True}
        approved=await invoke([],store,'Approve reviewed proposal','task-validation',decision)
        assert await tasks()==baseline  # approval only queues; worker is a separate invocation
        from agent_server.approval_worker import execute_approval
        from agent_server.config import Settings
        await execute_approval(store,demo_settings(),approval_id)
        after_approval=await tasks()
        replay=await invoke([],store,'Replay reviewed approval','task-validation',decision)
        after_replay=await tasks()
        task_id=store.approval_rows[approval_id]['task_id']
        assert len(after_approval)==len(baseline)+1 and after_approval==after_replay
        assert replay['response']['custom_outputs']['action']['execution_state']=='EXECUTED'
        assert sum(t['task_id']==task_id for t in after_replay)==1 and len(store.completed)==1
        async with client(stack,'opstask',True) as writer:
            replayed=await writer.call_tool('create_task',dict(payload,idempotency_key=approval_id))
            assert not replayed.isError and replayed.structuredContent['data']['replayed']
            assert replayed.structuredContent['data']['task_id']==task_id
        assert await tasks()==after_replay
        rejected=await store.propose('fixture-employee',application.scoped_session('fixture-employee','task-validation'),payload)
        before_reject=await tasks()
        rejection=await invoke([],store,'Reject proposal','task-validation',dict(action='task_decision',approval_id=rejected['approval_id'],approve=False))
        assert await tasks()==before_reject and len(store.completed)==1
        async with client(stack,'confluence') as reader:
            searched=await reader.call_tool('search_company_context',{'query':'protected training'})
            retrieved=await reader.call_tool('get_policy_document',{'source_id':'DEMO-TRAINING-1'})
        document=retrieved.structuredContent['data']['document']
        assert all(document[k] for k in ['source_id','document_id','title','source_url','section','text'])
        assert document['text']==(ROOT/'mcp-apps/data/policies/protected-training.md').read_text()
        assert any(d['source_id']==document['source_id'] for d in searched.structuredContent['data']['documents'])
        policy=await invoke([
            [call('confluence',{'input':'Search and retrieve protected training policy'})],
            [call('search_company_context',{'query':'protected training'})],
            [call('get_policy_document',{'source_id':'DEMO-TRAINING-1'})],[message(document['text'])],
            answer('Replace this model prose with verified policy excerpts.',[document['source_id'],document['source_url']],True,[document['text']])
        ],FakeStore(),'What is the training policy?','policy-validation')
        final=policy['response']['output'][0]['content'][0]['text']
        assert document['text'] in final and document['source_url'] in final and document['source_id'] in final
        assert final.startswith('Synthetic demo Confluence policy excerpts:')
        # Explicitly document that writer authorization is credential scope, not an approval lookup.
        async with client(stack,'opstask',True) as writer:
            direct=await writer.call_tool('create_task',dict(payload,title='Direct writer boundary probe',idempotency_key='direct-writer-probe'))
            assert not direct.isError
        return {'training':{'diagnosis':diagnosis,**training},'task':{'approval_id':approval_id,'task_id':task_id,
            'snapshots':dict(before=baseline,after_proposal=after_proposal,after_approval=after_approval,after_replay=after_replay),
            'counts':dict(before=len(baseline),after_proposal=len(after_proposal),after_approval=len(after_approval),after_replay=len(after_replay)),
            'proposed':proposed,'approved':approved,'replay':replay,'server_replay':replayed.model_dump(mode='json'),'rejection':rejection},
            'policy':{'search':searched.model_dump(mode='json'),'document':document,**policy},
            'writer_boundary':{'server_checks_application_approval':False,'direct_writer_result':direct.model_dump(mode='json'),
            'explanation':'Server trusts write credential; only the application approval handler gates its writer. Local roles simulate identities, not real OBO/SP authorization.'}}
async def run(stack):
    protocol=await verify(stack)
    return {'reconstruction':True,'recorded_at':datetime.now(timezone.utc).isoformat(),
        'scope':{'real':['local MCP HTTP processes','SDK orchestration','Responses/approval handlers','demo SQLite task storage'],
                 'fixtures':['Genie metrics transport','scripted model','employee identity','FakeStore session/approval memory'],
                 'live_databricks_verified':False},'protocol':protocol,'scenarios':await scenarios(stack),
        'contracts_sha256':hashlib.sha256((ROOT/'mcp-apps/contracts.json').read_bytes()).hexdigest()}
def main():
    mlflow.tracing.disable();set_tracing_disabled(True)
    with DemoStack() as stack: report=asyncio.run(run(stack))
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',default='docs/validation/reconstruction')
    directory=ROOT/parser.parse_args().output_dir
    directory.mkdir(parents=True,exist_ok=True)
    (directory/'demo-e2e-evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'local_validation':'passed','reconstruction':True,'live_databricks_verified':False,'task_counts':report['scenarios']['task']['counts']},indent=2))
if __name__=='__main__': main()
