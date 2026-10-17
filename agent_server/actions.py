"""Human-only commands. None of these mutation functions is an agent tool."""
import asyncio
import hashlib
import json
import os
from datetime import date

import jsonschema
from databricks_openai.agents import McpServer
from pydantic import BaseModel, Field
from agent_server.connections import write_client


class TaskProposal(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    store_id: str = Field(min_length=1, max_length=100)
    assignee: str = Field(min_length=1, max_length=200)
    due_date: date


async def decide_task(store, settings, user_client, owner, session_id, approval_id, approve):
    if type(approve) is not bool:
        raise ValueError('Approval decision must be an explicit boolean')
    claim = await store.claim(owner, session_id, approval_id, approve)
    if 'payload' not in claim or not approve:
        return {'status': claim['status'], 'task_id': claim.get('external_id')}
    try:
        # Separate writer is never attached to a model.
        async with write_client(settings, user_client, databricks_factory=McpServer) as server:
            tools = await server.list_tools()
            tool = next(t for t in tools if t.name == settings.task_tool)
            mapping = json.loads(os.environ.get('OPSTASK_ARGUMENT_MAP', '{"title":"title","store_id":"store_id","assignee":"assignee","due_date":"due_date","idempotency_key":"idempotency_key"}'))
            payload = dict(claim['payload'], idempotency_key=approval_id)
            if set(mapping) != set(payload):
                raise ValueError('OpsTask argument map must cover every reviewed field and idempotency_key')
            arguments = {mapping[key]: value for key, value in payload.items()}
            jsonschema.validate(arguments, tool.inputSchema)
            result = await server.call_tool(settings.task_tool, arguments)
            if result.isError:
                raise RuntimeError('OpsTask mutation failed')
            response = result.structuredContent
            if not response:
                response = json.loads(next(c.text for c in result.content if c.type == 'text'))
            if isinstance(response.get('data'), dict):
                response = response['data']
            task_id = response.get(os.getenv('OPSTASK_RESULT_ID_FIELD', 'task_id'))
            if not isinstance(task_id, str) or not task_id:
                raise RuntimeError('OpsTask did not return a task identifier')
        await store.complete(approval_id, 'created', task_id)
        return {'status': 'created', 'task_id': task_id}
    except Exception:
        await store.complete(approval_id, 'needs_reconciliation')
        raise RuntimeError('OpsTask outcome requires reconciliation by approval ID; automatic retry is disabled') from None


async def background_job(store, service_client, settings, owner, request_id, confirm, status_only=False):
    if not request_id or len(request_id) > 64:
        raise ValueError('A stable request_id of 1–64 characters is required')
    key = hashlib.sha256(f'{owner}:{request_id}'.encode()).hexdigest()
    if status_only:
        rows = await store.sql('SELECT run_id FROM store_ops.workflow_runs WHERE request_id=%s AND owner_id=%s', (key, owner))
        if not rows or not rows[0]['run_id']:
            raise ValueError('No recorded run for this employee request')
        run = await asyncio.to_thread(service_client.jobs.get_run, run_id=rows[0]['run_id'])
        return {'run_id': run.run_id, 'state': run.state.as_dict() if run.state else {}}
    if confirm is not True:
        raise PermissionError('Human confirmation is required to submit the background job')
    await store.sql('INSERT INTO store_ops.workflow_runs(request_id,owner_id) VALUES (%s,%s) ON CONFLICT DO NOTHING', (key, owner))
    # Databricks guarantees run-now idempotency for this identity-scoped token.
    response = await asyncio.to_thread(service_client.jobs.run_now, job_id=settings.workflow_job, idempotency_token=key)
    run_id = response.run_id
    if run_id is None:
        raise RuntimeError('Databricks did not return a workflow run ID')
    await store.sql('UPDATE store_ops.workflow_runs SET run_id=%s WHERE request_id=%s AND owner_id=%s', (run_id, key, owner))
    return {'status': 'submitted', 'run_id': run_id}
