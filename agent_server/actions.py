"""Human-only commands. None of these mutation functions is an agent tool."""
import asyncio
import hashlib
from datetime import date

from pydantic import BaseModel, Field


class TaskProposal(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    store_id: str = Field(min_length=1, max_length=100)
    assignee: str = Field(min_length=1, max_length=200)
    due_date: date


async def decide_task(store, settings, owner, session_id, approval_id, approve):
    if type(approve) is not bool:
        raise ValueError('Approval decision must be an explicit boolean')
    # Persist decision and outbox atomically; no Jobs or privileged MCP call here.
    return await store.decide(owner, session_id, approval_id, approve)


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
