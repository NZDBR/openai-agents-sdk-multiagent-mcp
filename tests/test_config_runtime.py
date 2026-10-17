import asyncio
import importlib
import sys
from types import SimpleNamespace
import pytest
import yaml
from agent_server.config import Settings
from agent_server.agent import response, stream_handler


def test_workspace_routes_and_no_cross_origin_credentials(settings, monkeypatch):
    urls = settings.mcp_urls('https://workspace.example')
    assert urls['genie'] == 'https://workspace.example/api/2.0/mcp/genie/test-space'
    assert urls['storetime'].endswith('/mcp/external/test-time')
    monkeypatch.setenv('GENIE_MCP_URL', 'https://evil.example/steal')
    with pytest.raises(ValueError, match='origin'):
        settings.mcp_urls('https://workspace.example')


def test_genie_override_cannot_target_task_gateway(settings, monkeypatch):
    monkeypatch.setenv('GENIE_MCP_URL','https://workspace.example/api/2.0/mcp/external/task-writer')
    with pytest.raises(ValueError, match='governed MCP route'):
        settings.mcp_urls('https://workspace.example')


def test_configuration_is_portable_and_aliases_work(monkeypatch):
    values = {'MODEL_ENDPOINT':'test-model','GENIE_SPACE_ID':'test-genie','STORETIME_CONNECTION':'test-time',
              'OPSTASK_CONNECTION':'test-tasks','CONFLUENCE_CONNECTION':'test-context',
              'STORETIME_READ_TOOLS':'get_schedule','OPSTASK_READ_TOOLS':'list_tasks','CONFLUENCE_READ_TOOLS':'search',
              'OPSTASK_CREATE_TOOL':'create_task','LAKEBASE_ENDPOINT':'projects/test/branches/test/endpoints/test',
              'DATABRICKS_WORKFLOW_JOB_ID':'456'}
    for key,value in values.items(): monkeypatch.setenv(key,value)
    settings = Settings.load()
    assert settings.workflow_job == 456
    assert settings.lakebase_endpoint == values['LAKEBASE_ENDPOINT']
    monkeypatch.setenv('GENIE_SPACE_ID','<genie-space-id>')
    with pytest.raises(ValueError): Settings.load()


def test_dab_targets_permissions_and_resource_substitutions():
    with open('databricks.yml') as f: bundle = yaml.safe_load(f)
    assert bundle['targets']['dev']['mode'] == 'development'
    assert bundle['targets']['prod']['mode'] == 'production'
    assert bundle['workspace']['host'] == '${var.workspace_host}'
    app = bundle['resources']['apps']['store_operations']
    assert app['name'] == '${var.app_name}'
    grants = {r['name']:r for r in app['resources']}
    assert grants['genie-space']['genie_space']['permission'] == 'CAN_RUN'
    for capability in ['storetime','confluence']:
        assert grants[capability+'-mcp']['uc_securable']['permission'] == 'USE_CONNECTION'
    for name in ['opstask-read-mcp','opstask-write-mcp']:
        assert grants[name]['uc_securable']['permission'] == 'USE_CONNECTION'
    assert grants['opstask-read-mcp']['uc_securable']['securable_full_name'] != grants['opstask-write-mcp']['uc_securable']['securable_full_name']
    assert grants['background-job']['job']['permission'] == 'CAN_MANAGE_RUN'
    assert bundle['resources']['jobs']['store_operations_background']['tasks'][0]['notebook_task']


def test_response_and_stream_protocol(monkeypatch):
    import agent_server.agent as agent
    async def invoke(request):
        return response('Verified answer', {'session_id':'test','proposals':[]})
    monkeypatch.setattr(agent, 'invoke_handler', invoke)
    async def run():
        events = [event async for event in stream_handler(None)]
        assert events[0].type == 'response.output_item.added'
        assert any(e.type == 'response.output_text.delta' for e in events)
        assert events[-1].type == 'response.completed'
        assert events[-1].model_dump()['response']['custom_outputs']['session_id'] == 'test'
    asyncio.run(run())


def test_official_long_running_server_is_the_runtime(monkeypatch, settings):
    # Import the production entry point with only credential/configuration setup
    # stubbed. Instantiate the real official runtime; no custom FastAPI app.
    import agent_server.agent as agent
    import agent_server.observability as observability
    import mlflow.genai.agent_server as mlserver
    monkeypatch.setattr(agent.Settings,'load',lambda: settings)
    monkeypatch.setattr(agent,'configure_model',lambda: None)
    monkeypatch.setattr(observability,'configure_tracing',lambda: None)
    monkeypatch.setattr(mlserver,'setup_mlflow_git_based_version_tracking',lambda: None)
    cfg = SimpleNamespace(autoscaling_endpoint=settings.lakebase_endpoint,autoscaling_project=None,autoscaling_branch=None,memory_schema=None,description='test')
    utils = SimpleNamespace(lakebase_config=cfg,replace_fake_id=lambda obj,id:obj,get_lakebase_access_error_message=lambda desc:desc)
    monkeypatch.setitem(sys.modules,'agent_server.template_utils',utils)
    sys.modules.pop('agent_server.start_server',None)
    module = importlib.import_module('agent_server.start_server')
    from databricks_ai_bridge.long_running import LongRunningAgentServer
    assert isinstance(module.agent_server,LongRunningAgentServer)
    assert any(route.path == '/invocations' for route in module.app.routes)
    captured = []
    class Session:
        def __init__(self,**kwargs): captured.append(kwargs)
        async def _ensure_tables(self): captured.append('initialized')
    monkeypatch.setattr(module,'AsyncDatabricksSession',Session)
    asyncio.run(module.run_lakebase_session_setup())
    assert captured[0]['autoscaling_endpoint'] == settings.lakebase_endpoint
    assert captured[1] == 'initialized'
    sys.modules.pop('agent_server.start_server',None)
