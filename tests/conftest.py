import os
from dataclasses import replace
import pytest
from agent_server.config import Settings

@pytest.fixture
def settings():
    return Settings(model='test-model', genie_space='test-space', storetime_connection='test-time',
                    opstask_connection='test-tasks', confluence_connection='test-context',
                    storetime_tools=('read_schedule',), opstask_tools=('list_followups',),
                    confluence_tools=('search_policy',), task_tool='create_task',
                    lakebase_endpoint='projects/test/branches/test/endpoints/test', workflow_job=123)


@pytest.fixture(autouse=True)
def isolate_runtime_urls(request, monkeypatch):
    if request.node.get_closest_marker('integration'):
        return
    for name in ['MCP_CONNECTION_MODE','DEMO_MCP_ALLOWED_HOSTS','GENIE_MCP_URL','STORETIME_MCP_URL','OPSTASK_MCP_URL','CONFLUENCE_MCP_URL','OPSTASK_ARGUMENT_MAP','OPSTASK_RESULT_ID_FIELD']:
        monkeypatch.delenv(name,raising=False)


@pytest.fixture(scope='session',autouse=True)
def local_tracking_backend(tmp_path_factory):
    # The ordinary test suite must never export employee/tool data to an ambient
    # configured workspace. Explicit live integration checks use their own clients.
    import mlflow
    old_uri = mlflow.get_tracking_uri()
    old_id = os.environ.pop('MLFLOW_EXPERIMENT_ID',None)
    old_name = os.environ.pop('MLFLOW_EXPERIMENT_NAME',None)
    mlflow.set_tracking_uri('sqlite:///' + str(tmp_path_factory.mktemp('tracking')/'tests.db'))
    try:
        yield
    finally:
        mlflow.flush_trace_async_logging()
        mlflow.set_tracking_uri(old_uri)
        if old_id is not None: os.environ['MLFLOW_EXPERIMENT_ID'] = old_id
        if old_name is not None: os.environ['MLFLOW_EXPERIMENT_NAME'] = old_name
