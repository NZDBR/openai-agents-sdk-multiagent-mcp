# Databricks notebook source
"""Scheduled-only dispatcher. It never receives or constructs an OpsTask writer."""
import asyncio
import os
from databricks.sdk import WorkspaceClient
from agent_server.memory import LakebaseStore
from agent_server.approval_worker import dispatch_approvals

dbutils.widgets.text('lakebase_endpoint', '')  # noqa: F821
dbutils.widgets.text('schema', '')  # noqa: F821
dbutils.widgets.text('execution_job_id', '')  # noqa: F821
os.environ['STORE_OPS_SCHEMA'] = dbutils.widgets.get('schema')  # noqa: F821
dbutils.widgets.text('policy_config', '{}')  # noqa: F821
os.environ['APPROVAL_POLICY_JSON'] = dbutils.widgets.get('policy_config')  # noqa: F821
store = LakebaseStore(dbutils.widgets.get('lakebase_endpoint'))  # noqa: F821
try:
    asyncio.run(dispatch_approvals(store, WorkspaceClient().jobs,
        int(dbutils.widgets.get('execution_job_id'))))  # noqa: F821
finally:
    store.close()
