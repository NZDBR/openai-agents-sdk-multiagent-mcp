"""Real local MCP smoke test. No model, Genie or Databricks calls."""
import asyncio
import contextlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import httpx
import jsonschema
from agents.mcp import MCPServerStreamableHttp
from agent_server.config import Settings
from agent_server.connections import read_client
from agent_server.governance import Evidence
READ_TOOLS={
 'storetime':{'get_schedules','get_training_blocks','get_training_hours','get_coverage_reasons','diagnose_training_gap'},
 'opstask':{'list_followups','get_task'},'confluence':{'search_company_context','get_policy_document'}}
WINDOW={'store_id':'DEMO-001','start_date':'2026-01-05','end_date':'2026-01-06'}
ARGUMENTS={name:WINDOW for name in READ_TOOLS['storetime']}
ARGUMENTS.update(list_followups={'store_id':'DEMO-001'},get_task={'task_id':'DEMO-SEED-001'},
 search_company_context={'query':'protected training'},get_policy_document={'source_id':'DEMO-TRAINING-1'})
class DemoStack:
    def __enter__(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='store-reconstructed-mcp-')
        self.processes=[];self.logs=[];self.urls={};self.tokens={};used=set()
        try:
            for cap in READ_TOOLS:
                while True:
                    with socket.socket() as probe:
                        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
                    if port not in used: used.add(port);break
                self.urls[cap]=f'http://127.0.0.1:{port}/mcp'
                self.tokens[cap]={'read':secrets.token_urlsafe(32),'write':secrets.token_urlsafe(32) if cap=='opstask' else None}
                env={k:v for k,v in os.environ.items() if not k.startswith(('DATABRICKS_','OPENAI_','MLFLOW_','MCP_','DEMO_'))}
                env.update(MCP_READ_TOKEN=self.tokens[cap]['read'],MCP_TASK_DB=str(Path(self.tmp.name)/'tasks.db'))
                if cap=='opstask': env['MCP_WRITE_TOKEN']=self.tokens[cap]['write']
                log=open(Path(self.tmp.name)/(cap+'.log'),'w+');self.logs.append(log)
                self.processes.append(subprocess.Popen([sys.executable,'-m',cap+'.server','--host','127.0.0.1','--port',str(port)],env=env,stdout=log,stderr=subprocess.STDOUT))
            deadline=time.monotonic()+30
            with httpx.Client(trust_env=False,timeout=1) as http:
                for cap,process,log in zip(READ_TOOLS,self.processes,self.logs):
                    while True:
                        if process.poll() is not None:
                            log.seek(0);raise RuntimeError(cap+' failed: '+log.read()[-2000:])
                        try:
                            if all(http.get(self.urls[cap].removesuffix('/mcp')+p).status_code==200 for p in ['/health','/ready']): break
                        except httpx.HTTPError: pass
                        if time.monotonic()>deadline: raise TimeoutError(cap+' readiness timed out')
                        time.sleep(.1)
            return self
        except BaseException:
            self.__exit__(None,None,None);raise
    def __exit__(self,*args):
        for process in self.processes:
            if process.poll() is None: process.terminate()
        for process in self.processes:
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill();process.wait(timeout=5)
        for log in self.logs: log.close()
        self.tmp.cleanup()
    @contextlib.contextmanager
    def agent_environment(self):
        updates={'MCP_CONNECTION_MODE':'local_demo','GENIE_MCP_URL':''}
        for cap in READ_TOOLS:
            updates[cap.upper()+'_MCP_URL']=self.urls[cap]
            updates['DEMO_'+cap.upper()+'_READ_TOKEN']=self.tokens[cap]['read']
        updates['DEMO_OPSTASK_WRITE_TOKEN']=self.tokens['opstask']['write']
        old={k:os.getenv(k) for k in updates};os.environ.update(updates)
        try: yield
        finally:
            for k,v in old.items():
                if v is None: os.environ.pop(k,None)
                else: os.environ[k]=v

def demo_settings():
    return Settings(model='test-only',genie_space='test-only',lakebase_endpoint='test-only',workflow_job=0,
      storetime_connection='',opstask_connection='',confluence_connection='',task_tool='create_task',
      storetime_tools=tuple(sorted(READ_TOOLS['storetime'])),opstask_tools=tuple(sorted(READ_TOOLS['opstask'])),confluence_tools=tuple(sorted(READ_TOOLS['confluence'])))
def client(stack,cap,write=False):
    return MCPServerStreamableHttp(name='validate-'+cap,params={'url':stack.urls[cap],
       'headers':{'X-Demo-MCP-Token':stack.tokens[cap]['write' if write else 'read']}})
async def verify(stack):
    published=json.loads(Path('mcp-apps/contracts.json').read_text())['apps'];evidence=Evidence();report={}
    with stack.agent_environment():
        for cap,names in READ_TOOLS.items():
            checks={}
            with httpx.Client(trust_env=False) as http:
                for path in ['/health','/ready']:
                    response=http.get(stack.urls[cap].removesuffix('/mcp')+path)
                    assert response.status_code==200
                    checks[path]={'status_code':response.status_code,'body':response.json()}
            async with client(stack,cap) as raw:
                tools=await raw.list_tools()
                assert {t.name for t in tools}==names
                assert all(t.annotations.readOnlyHint for t in tools)
                schemas=[t.model_dump(mode='json',exclude_none=True) for t in tools]
                expected=[t for t in published[cap] if t['name'] in names]
                assert sorted(schemas,key=lambda t:t['name'])==sorted(expected,key=lambda t:t['name'])
                report[cap]={'checks':checks,'initialize':raw.server_initialize_result.model_dump(mode='json'),
                             'runtime_tools':schemas,'matches_contract':True}
                if cap=='opstask':
                    denied=await raw.call_tool('create_task',dict(title='Forbidden read probe',store_id='DEMO-001',assignee='DEMO-MANAGER',due_date='2030-01-15',idempotency_key='forbidden-read'))
                    assert denied.isError
                    report[cap]['read_mutation_denial']=denied.model_dump(mode='json')
            async with read_client(cap,demo_settings(),None,evidence) as reader:
                tools=await reader.list_tools();assert {t.name for t in tools}==names
                for tool in tools:
                    result=await reader.call_tool(tool.name,ARGUMENTS[tool.name]);assert not result.isError
                    jsonschema.validate(result.structuredContent,tool.outputSchema)
                try: await reader.call_tool('create_task',{})
                except PermissionError: pass
                else: raise AssertionError('Model-facing mutation dispatch was permitted')
        async with client(stack,'opstask',True) as writer:
            schemas=[t.model_dump(mode='json',exclude_none=True) for t in await writer.list_tools()]
            assert sorted(schemas,key=lambda t:t['name'])==sorted(published['opstask'],key=lambda t:t['name'])
            report['writer']={'runtime_tools':schemas,'matches_contract':True}
    return {'services':report,'read_tool_results':evidence.calls,'real_http_processes':3,'live_databricks_verified':False}
def main():
    import mlflow
    mlflow.tracing.disable()
    with DemoStack() as stack: result=asyncio.run(verify(stack))
    print(json.dumps(result,indent=2))
if __name__=='__main__': main()
