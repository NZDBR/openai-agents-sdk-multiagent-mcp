# Databricks notebook source
"""Backend-only Workflow entry point. approval_id is the sole business parameter."""
import asyncio
import json
import os
from agent_server.config import Settings
from agent_server.memory import LakebaseStore
from agent_server.approval_worker import execute_approval

for name in ('approval_id','deployment_config','secret_scope','client_id_key','client_secret_key','demo_write_key'):
    dbutils.widgets.text(name, '')  # noqa: F821
config = json.loads(dbutils.widgets.get('deployment_config'))  # noqa: F821
os.environ.update({key:str(value) for key,value in config.items()})
scope = dbutils.widgets.get('secret_scope')  # noqa: F821
if config.get('MCP_CONNECTION_MODE') == 'deployed_demo':
    os.environ['DEMO_OPSTASK_WRITE_TOKEN'] = dbutils.secrets.get(scope, dbutils.widgets.get('demo_write_key'))  # noqa: F821
else:
    os.environ['OPSTASK_WRITE_CLIENT_ID'] = dbutils.secrets.get(scope, dbutils.widgets.get('client_id_key'))  # noqa: F821
    os.environ['OPSTASK_WRITE_CLIENT_SECRET'] = dbutils.secrets.get(scope, dbutils.widgets.get('client_secret_key'))  # noqa: F821
os.environ['OPSTASK_WRITE_AUTH_MODE'] = 'm2m'
settings = Settings.load()
dbutils.widgets.text('policy_config', '{}')  # noqa: F821
os.environ['APPROVAL_POLICY_JSON'] = dbutils.widgets.get('policy_config')  # noqa: F821
store = LakebaseStore(settings.lakebase_endpoint)
try:
    # Do not print payload, credentials or errors into notebook outputs.
    asyncio.run(execute_approval(store, settings, dbutils.widgets.get('approval_id')))  # noqa: F821
finally:
    store.close()
