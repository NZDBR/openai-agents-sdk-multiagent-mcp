"""Credential-construction contracts, not live UC/OAuth permission evidence."""
import ast
import asyncio
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from mcp.types import Tool, CallToolResult
from agent_server import identity, connections, actions
from agent_server.governance import Evidence
from tests.fakes import FakeStore

HOST='https://workspace.example'

@pytest.fixture
def oauth_env(monkeypatch):
    for k,v in dict(DATABRICKS_HOST=HOST,DATABRICKS_APP_NAME='test-app',DATABRICKS_CLIENT_ID='test-app-id',
       DATABRICKS_CLIENT_SECRET='test-app-secret',OPSTASK_WRITE_OAUTH_SCOPES='test-mcp-scope',
       OPSTASK_WRITE_AUTH_MODE='app').items(): monkeypatch.setenv(k,v)
    for k in ['OPSTASK_WRITE_MCP_URL','OPSTASK_READ_MCP_URL','USER_AUTHORIZATION_MODE']:
        monkeypatch.delenv(k,raising=False)


def test_obo_preserves_employee_token_without_constructing_service_identity(oauth_env,monkeypatch):
    factory=Mock(return_value=SimpleNamespace(current_user=SimpleNamespace(me=lambda:SimpleNamespace(id='employee'))))
    monkeypatch.setattr(identity,'WorkspaceClient',factory)
    monkeypatch.setattr(identity,'get_request_headers',lambda:{'x-forwarded-access-token':'employee-oauth-token'})
    owner,_=asyncio.run(identity.employee())
    assert owner=='employee'
    factory.assert_called_once_with(host=HOST,token='employee-oauth-token',auth_type='pat')


def test_no_employee_token_never_falls_back_to_app(oauth_env,monkeypatch):
    factory=Mock();monkeypatch.setattr(identity,'WorkspaceClient',factory)
    monkeypatch.setattr(identity,'get_request_headers',lambda:{})
    with pytest.raises(PermissionError): identity.user_workspace_client()
    factory.assert_not_called()


def test_local_profile_requires_explicit_mode_and_is_forbidden_in_app(oauth_env,monkeypatch):
    monkeypatch.setattr(identity,'get_request_headers',lambda:{})
    monkeypatch.setenv('USER_AUTHORIZATION_MODE','local_profile')
    monkeypatch.setenv('ALLOW_LOCAL_PROFILE_IDENTITY','true')
    factory=Mock();monkeypatch.setattr(identity,'WorkspaceClient',factory)
    with pytest.raises(PermissionError): identity.user_workspace_client()
    monkeypatch.delenv('DATABRICKS_APP_NAME')
    identity.user_workspace_client();factory.assert_called_once_with()


@pytest.mark.parametrize('mode',['app','m2m'])
def test_backend_oauth_identity_never_uses_forwarded_token_or_ambient_pat(oauth_env,monkeypatch,mode):
    monkeypatch.setenv('OPSTASK_WRITE_AUTH_MODE',mode)
    monkeypatch.setenv('OPSTASK_WRITE_CLIENT_ID','test-backend-id')
    monkeypatch.setenv('OPSTASK_WRITE_CLIENT_SECRET','test-backend-secret')
    monkeypatch.setenv('DATABRICKS_TOKEN','test-ambient-user-pat')
    monkeypatch.setattr(identity,'get_request_headers',lambda:pytest.fail('Writer must never inspect forwarded employee headers'))
    factory=Mock();monkeypatch.setattr(identity,'WorkspaceClient',factory)
    identity.app_workspace_client()
    prefix='test-app' if mode=='app' else 'test-backend'
    factory.assert_called_once_with(host=HOST,client_id=prefix+'-id',client_secret=prefix+'-secret',auth_type='oauth-m2m',scopes=['test-mcp-scope'])


@pytest.mark.parametrize('missing',['DATABRICKS_CLIENT_ID','DATABRICKS_CLIENT_SECRET','OPSTASK_WRITE_OAUTH_SCOPES'])
def test_backend_missing_credentials_fail_closed(oauth_env,monkeypatch,missing):
    monkeypatch.delenv(missing)
    with pytest.raises(ValueError): identity.app_workspace_client()


def test_user_specialists_receive_user_client_only(settings,monkeypatch):
    employee_client=SimpleNamespace(config=SimpleNamespace(host=HOST))
    constructor=Mock();monkeypatch.setattr(connections,'GovernedMcpServer',constructor)
    monkeypatch.setattr(connections,'app_workspace_client',lambda:pytest.fail('Read path constructed backend identity'))
    for cap in ['genie','storetime','opstask','confluence']:
        connections.user_mcp_client(cap,settings,employee_client,Evidence())
        kwargs=constructor.call_args.kwargs
        assert kwargs['workspace_client'] is employee_client
        assert 'create_task' not in kwargs['allowed']
        assert 'WRITE' not in str(kwargs)


def test_production_write_factory_uses_distinct_backend_and_route(settings,monkeypatch):
    settings=replace(settings,opstask_write_connection='test-write-service')
    backend=SimpleNamespace(config=SimpleNamespace(host=HOST))
    monkeypatch.setattr(connections,'app_workspace_client',lambda:backend)
    constructor=Mock()
    connections.app_write_mcp_client(settings,databricks_factory=constructor)
    assert constructor.call_args.kwargs['workspace_client'] is backend
    assert constructor.call_args.kwargs['url']==HOST+'/api/2.0/mcp/external/test-write-service'
    assert constructor.call_args.kwargs['max_retry_attempts']==0
    with pytest.raises(TypeError): connections.app_write_mcp_client(settings,backend)


@pytest.mark.parametrize('override',[None,HOST+'/api/2.0/mcp/external/test-tasks',HOST+'/api/2.0/mcp/external/%74est-tasks','https://evil.invalid/mcp'])
def test_write_binding_cannot_fall_back_to_read_or_cross_origin(settings,monkeypatch,override):
    if override: monkeypatch.setenv('OPSTASK_WRITE_MCP_URL',override)
    with pytest.raises(ValueError): settings.write_mcp_url(HOST)


def test_only_approval_handler_calls_privileged_factory():
    callers=[]
    for p in Path('agent_server').glob('*.py'):
        tree=ast.parse(p.read_text())
        for fn in ast.walk(tree):
            if isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)):
                for node in ast.walk(fn):
                    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='app_write_mcp_client':
                        callers.append((p.name,fn.name))
    assert callers==[('actions.py','decide_task')]
    client_source=Path('e2e-chatbot-app-next/client/src').rglob('*')
    for p in client_source:
        if p.is_file():
            text=p.read_text()
            assert 'OPSTASK_WRITE_CLIENT_SECRET' not in text and 'DEMO_OPSTASK_WRITE_TOKEN' not in text


def test_approval_claim_precedes_writer_and_rejection_replay_never_construct_writer(settings,monkeypatch):
    events=[]
    class Store(FakeStore):
        async def claim(self,*args):
            events.append('claim');return await super().claim(*args)
    class Writer:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def list_tools(self): return [Tool(name='create_task',inputSchema={'type':'object'})]
        async def call_tool(self,name,args):
            events.append('write');return CallToolResult(content=[],structuredContent={'task_id':'test-stable-id'})
    def factory(*args,**kwargs): events.append('construct');return Writer()
    monkeypatch.setattr(actions,'app_write_mcp_client',factory)
    async def run():
        store=Store();payload=dict(title='Review training',store_id='test-store',assignee='manager',due_date='2030-01-15')
        rejected=await store.propose('employee','session',payload)
        for approval in [False,True]:
            await actions.decide_task(store,settings,'employee','session',rejected['approval_id'],approval)
        assert events==['claim','claim']
        proposal=await store.propose('employee','session',payload)
        with pytest.raises(PermissionError):
            await actions.decide_task(store,settings,'another-employee','session',proposal['approval_id'],True)
        assert 'construct' not in events
        one=await actions.decide_task(store,settings,'employee','session',proposal['approval_id'],True)
        two=await actions.decide_task(store,settings,'employee','session',proposal['approval_id'],True)
        assert one==two and events.count('construct')==events.count('write')==1
        assert events.index('construct')>events.index('claim')
    asyncio.run(run())


def test_demo_credentials_simulate_roles_without_backend_oauth(settings,monkeypatch):
    monkeypatch.setenv('MCP_CONNECTION_MODE','local_demo')
    for cap,port in [('storetime',8101),('opstask',8102),('confluence',8103)]:
        monkeypatch.setenv(cap.upper()+'_MCP_URL',f'http://127.0.0.1:{port}/mcp')
        monkeypatch.setenv('DEMO_'+cap.upper()+'_READ_TOKEN','read-'+cap+'-test-token-'+'r'*24)
    monkeypatch.setenv('DEMO_OPSTASK_WRITE_TOKEN','write-test-token-'+'w'*24)
    monkeypatch.setattr(connections,'app_workspace_client',lambda:pytest.fail('Local simulation must not construct an OAuth identity'))
    reader=connections.user_mcp_client('opstask',settings,None,Evidence())
    writer=connections.app_write_mcp_client(settings)
    assert reader.params['headers']['X-Demo-MCP-Token'] != writer.params['headers']['X-Demo-MCP-Token']
    assert reader.permitted('list_followups') and not reader.permitted('create_task')
    with pytest.raises(PermissionError): asyncio.run(reader.call_tool('create_task',{}))


def test_optional_gateway_approval_is_configuration_not_fabricated_api(settings,monkeypatch):
    assert settings.approval_policy()==dict(mode='application',policy_id=None)
    monkeypatch.setenv('OPSTASK_APPROVAL_MODE','application_and_gateway_ask')
    with pytest.raises(ValueError): settings.approval_policy()
    monkeypatch.setenv('OPSTASK_GATEWAY_POLICY_ID','test-policy-id')
    assert settings.approval_policy()==dict(mode='application_and_gateway_ask',policy_id='test-policy-id')
    for path in ['docs/GOVERNANCE.md','.env.example','deployment/agent.resources.yml']:
        assert 'OPSTASK_APPROVAL_MODE' in Path(path).read_text()


def test_least_privilege_grant_plan_does_not_grant_employee_write_or_admin():
    statements=[line for line in Path('config/mcp-grants.sql.example').read_text().splitlines() if line.startswith('GRANT ')]
    employee=[s for s in statements if '<employee-read-group>' in s]
    backend=[s for s in statements if '<backend-writer-principal>' in s]
    assert len(employee)==3 and len(backend)==1
    assert all('write-connection' not in s for s in employee)
    assert '<opstask-write-connection>' in backend[0]
    assert all(s.startswith('GRANT USE CONNECTION ') for s in statements)


def test_gateway_challenge_is_not_approved_or_retried_by_application(settings,monkeypatch):
    calls=[]
    class Writer:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def list_tools(self): return [Tool(name='create_task',inputSchema={'type':'object'})]
        async def call_tool(self,name,args):
            calls.append(name)
            # Test-only shape representing an unconfirmed outcome; not an asserted platform API.
            return CallToolResult(content=[],structuredContent={'test_only_unconfirmed_outcome':'ASK'})
    monkeypatch.setattr(actions,'app_write_mcp_client',lambda *args,**kwargs:Writer())
    async def run():
        store=FakeStore();proposal=await store.propose('employee','session',dict(title='Review',store_id='test',assignee='manager',due_date='2030-01-15'))
        with pytest.raises(RuntimeError,match='reconciliation'):
            await actions.decide_task(store,settings,'employee','session',proposal['approval_id'],True)
        replay=await actions.decide_task(store,settings,'employee','session',proposal['approval_id'],True)
        assert replay['status']=='needs_reconciliation' and calls==['create_task']
    asyncio.run(run())


def test_missing_user_client_cannot_trigger_sdk_app_identity_fallback(settings,monkeypatch):
    constructor=Mock();monkeypatch.setattr(connections,'GovernedMcpServer',constructor)
    for capability in ['genie','storetime','opstask','confluence']:
        with pytest.raises(PermissionError): connections.user_mcp_client(capability,settings,None,Evidence())
    constructor.assert_not_called()


def test_m2m_secret_binding_example_never_embeds_a_secret_value():
    import yaml
    config=yaml.safe_load(Path('config/m2m-write-bindings.example.yaml').read_text())
    app=config['resources']['apps']['store_operations']
    env={item['name']:item for item in app['config']['env']}
    secret=env['OPSTASK_WRITE_CLIENT_SECRET']
    assert 'value' not in secret
    assert secret['value_from']==app['resources'][0]['name']
    assert app['resources'][0]['secret']['permission']=='READ'
