"""Scheduled Databricks Jobs dispatcher and lease-fenced OpsTask execution, no model."""
import asyncio
import hashlib
import json
import os

import httpx
import jsonschema
from mcp.shared.exceptions import McpError
from mcp.types import CONNECTION_CLOSED
from databricks_openai.agents import McpServer
from agent_server.actions import TaskProposal
from agent_server.approval_store import ApprovalPolicy
from agent_server.connections import app_write_mcp_client


class PermanentExecutionError(Exception):
    pass


async def write_task(settings, row, store):
    """Only this worker can construct the privileged writer; arguments come from Lakebase."""
    payload = TaskProposal(**row['reviewed_payload']).model_dump(mode='json')
    if (payload != row['reviewed_payload'] or row['action_type'] != 'CREATE_TASK'
            or row['tool_name'] != settings.task_tool or payload['store_id'] != row['store_id']
            or row['idempotency_key'] != row['proposal_id']):
        raise PermanentExecutionError('Invalid persisted action')
    settings.approval_policy()
    async with app_write_mcp_client(settings, databricks_factory=McpServer) as server:
        tools = await server.list_tools()
        tool = next((t for t in tools if t.name == row['tool_name']), None)
        if tool is None:
            raise PermanentExecutionError('Mutation tool is unavailable')
        mapping = json.loads(os.environ.get('OPSTASK_ARGUMENT_MAP', '{"title":"title","store_id":"store_id","assignee":"assignee","due_date":"due_date","idempotency_key":"idempotency_key"}'))
        payload['idempotency_key'] = row['idempotency_key']
        if set(mapping) != set(payload) or len(set(mapping.values())) != len(mapping):
            raise PermanentExecutionError('Invalid argument map')
        arguments = {mapping[key]: value for key,value in payload.items()}
        jsonschema.validate(arguments, tool.inputSchema)
        # Check again after discovery, immediately before any external side effect.
        if not await store.executable(row):
            raise PermanentExecutionError('Execution lease or action expired')
        result = await server.call_tool(row['tool_name'], arguments)
        if result.isError:
            # Generic tool errors have no portable transient classification. Fail closed.
            raise PermanentExecutionError('Tool rejected execution')
        response = result.structuredContent
        if not response:
            response = json.loads(next(c.text for c in result.content if c.type == 'text'))
        if isinstance(response.get('data'), dict):
            response = response['data']
        task_id = response.get(os.getenv('OPSTASK_RESULT_ID_FIELD','task_id'))
        if not isinstance(task_id,str) or not task_id:
            raise PermanentExecutionError('Unconfirmed result requires operator reconciliation')
        return task_id


def classify(error):
    # Never persist exception text, payloads, response bodies, URLs or credentials.
    if isinstance(error, BaseExceptionGroup):
        retry = all(classify(e)[1] for e in error.exceptions)
        return ('TRANSIENT_TRANSPORT' if retry else 'PERMANENT_OR_UNCONFIRMED', retry)
    if isinstance(error, McpError) and error.error.code == CONNECTION_CLOSED:
        return 'TRANSIENT_MCP_CONNECTION', True
    if isinstance(error, httpx.HTTPStatusError):
        retry = error.response.status_code in {408,429,500,502,503,504}
        return ('TRANSIENT_HTTP' if retry else 'PERMANENT_HTTP', retry)
    if isinstance(error,(TimeoutError,ConnectionError,httpx.TransportError)):
        return 'TRANSIENT_TRANSPORT', True
    return 'PERMANENT_OR_UNCONFIRMED', False


async def execute_approval(store, settings, approval_id):
    row = await store.execution_claim(approval_id)
    if row is None:
        return {'claimed':False}
    try:
        async with asyncio.timeout(ApprovalPolicy.load().timeout):
            task_id = await write_task(settings,row,store)
    except Exception as error:
        code,retryable = classify(error)
        return await store.execution_finish(row,error=code,retryable=retryable)
    # Persistence errors propagate: lease recovery safely replays the same business key.
    return await store.execution_finish(row,task_id=task_id)


async def dispatch_approvals(store, jobs, execution_job_id, batch_size=20):
    await store.recover()
    # A terminal Workflow can fail before it ever claims the approval.
    for row in await store.submitted_runs():
        try:
            run = await asyncio.to_thread(jobs.get_run,run_id=row['run_id'])
        except Exception:
            continue  # No conclusion without a confirmed run status.
        lifecycle = getattr(getattr(run,'state',None),'life_cycle_state',None)
        if getattr(lifecycle,'value',lifecycle) in {'TERMINATED','SKIPPED','INTERNAL_ERROR'}:
            await store.terminal_run(row)
    for row in await store.dispatch_claim(batch_size):
        token = hashlib.sha256(f"approval:{row['approval_id']}:{row['generation']}".encode()).hexdigest()
        try:
            run = await asyncio.to_thread(jobs.run_now,job_id=execution_job_id,
                job_parameters={'approval_id':row['approval_id']},idempotency_token=token)
            if run.run_id is None:
                raise RuntimeError('No run ID')
            await store.dispatched(row,run.run_id)
        except Exception:
            await store.dispatch_failed(row)
