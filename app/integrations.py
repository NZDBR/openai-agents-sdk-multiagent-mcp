"""Explicit external contracts; no inferred tool names or unrestricted model writes."""
import json
import os
from urllib.parse import urlparse

import httpx
from agents.mcp import MCPServerStreamableHttp


def https_url(name):
    value = os.getenv(name, '')
    parsed = urlparse(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f'{name} must be an HTTPS URL without embedded credentials')
    return value.rstrip('/')


def mcp_params(prefix):
    headers = {}
    token = os.getenv(prefix + '_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    return {'url': https_url(prefix + '_URL'), 'headers': headers, 'timeout': 30}


def tool_names(prefix):
    names = [s.strip() for s in os.getenv(prefix + '_TOOLS', '').split(',') if s.strip()]
    if not names:
        raise ValueError(f'{prefix}_TOOLS must explicitly list approved read-only tool names')
    return names


async def create_task(title, approval_id):
    """Configured OpsTask tool must honor approval_id as its idempotency key.

    Contract: accepts title and idempotency_key; returns structured task_id.
    It is never exposed to the model.
    """
    tool = os.environ['OPSTASK_WRITE_TOOL']
    async with MCPServerStreamableHttp(params=mcp_params('OPSTASK_WRITE_MCP'), name='Approved OpsTask writer') as server:
        result = await server.call_tool(tool, {'title': title, 'idempotency_key': approval_id})
        if result.isError:
            raise RuntimeError('OpsTask rejected task creation')
        payload = result.structuredContent
        if not payload:
            payload = json.loads(next(c.text for c in result.content if c.type == 'text'))
        task_id = payload.get('task_id')
        if not isinstance(task_id, str) or not task_id.strip():
            raise RuntimeError('OpsTask did not return a task_id')
        return task_id


async def employee_id(request):
    """Verify forwarded user token with Databricks, rather than trusting an ID header."""
    token = request.headers.get('X-Forwarded-Access-Token')
    if not token:
        raise ValueError('Databricks user authorization is required')
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(https_url('DATABRICKS_HOST') + '/api/2.0/preview/scim/v2/Me', headers={'Authorization': 'Bearer ' + token})
        response.raise_for_status()
        identity = response.json().get('id')
    if not isinstance(identity, str) or not identity:
        raise ValueError('Databricks did not return an employee identity')
    return identity


async def run_workflow(request_id):
    """Fixed, administrator-selected job; arbitrary job IDs/parameters are prohibited."""
    host = https_url('DATABRICKS_HOST')
    job_id = int(os.environ['DATABRICKS_WORKFLOW_JOB_ID'])
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(host + '/api/2.1/jobs/run-now', headers={'Authorization': 'Bearer ' + os.environ['DATABRICKS_WORKFLOW_TOKEN']}, json={'job_id': job_id, 'idempotency_token': request_id})
        response.raise_for_status()
        return response.json()['run_id']
