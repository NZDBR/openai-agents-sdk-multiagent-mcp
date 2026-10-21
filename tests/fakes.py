"""All synthetic data/adapters live in tests, never in the deployed runtime."""
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4
from agents.models.interface import Model
from agents import ModelResponse, Usage
from openai.types.responses import ResponseOutputMessage, ResponseOutputText, ResponseFunctionToolCall


class ScriptedModel(Model):
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.seen_tools = []

    async def get_response(self, *args, **kwargs):
        tools = kwargs.get('tools', args[3] if len(args) > 3 else [])
        self.seen_tools.append([t.name for t in tools])
        return ModelResponse(output=next(self.outputs), usage=Usage(), response_id='test-response')

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError('Streaming is not used by the buffered runtime')
        yield


def message(text):
    return ResponseOutputMessage(id=uuid4().hex, role='assistant', status='completed', content=[ResponseOutputText(type='output_text', text=text, annotations=[])], type='message')


def call(name, arguments):
    return ResponseFunctionToolCall(type='function_call', id=uuid4().hex, call_id=uuid4().hex, name=name, arguments=json.dumps(arguments))


class MemorySession:
    session_id = 'test-session'
    def __init__(self):
        self.items = []
    async def get_items(self, limit=None):
        return self.items[-limit:] if limit else list(self.items)
    async def add_items(self, items):
        self.items.extend(items)
    async def pop_item(self):
        return self.items.pop() if self.items else None
    async def clear_session(self):
        self.items.clear()


class FakeStore:
    def __init__(self):
        self.approval_rows = {}
        self.prefs = []
        self.history = MemorySession()
        self.completed = []
    def session(self, *args):
        return self.history
    @asynccontextmanager
    async def lock(self, session):
        yield
    async def preferences(self, owner):
        return self.prefs
    async def propose(self, owner, session, payload):
        from datetime import datetime, timezone, timedelta
        from copy import deepcopy
        id = uuid4().hex
        now = datetime.now(timezone.utc)
        self.approval_rows[id] = dict(proposal_id=id,employee_id=owner,session_id=session,
            reviewed_payload=deepcopy(payload),store_id=payload['store_id'],action_type='CREATE_TASK',
            tool_name='create_task',idempotency_key=id,approval_state='PENDING_APPROVAL',
            execution_state='NOT_STARTED',created_at=now,expires_at=now+timedelta(days=1),retry_count=0)
        return dict(approval_id=id,task=payload,approval_state='PENDING_APPROVAL',execution_state='NOT_STARTED')
    async def proposals(self, owner, session):
        return [dict(id=r['proposal_id'],payload=r['reviewed_payload'],**{k:r[k] for k in
            ('action_type','created_at','expires_at','approval_state','execution_state')})
            for r in self.approval_rows.values() if r['employee_id']==owner and r['session_id']==session]
    async def decide(self, owner, session, id, approve):
        from datetime import datetime, timezone
        row=self.approval_rows[id]
        if row['employee_id']!=owner or row['session_id']!=session:
            raise PermissionError('wrong owner/session')
        if row['approval_state']=='PENDING_APPROVAL':
            row['approval_state']='EXPIRED' if row['expires_at']<=datetime.now(timezone.utc) else 'APPROVED' if approve else 'REJECTED'
            if row['approval_state']=='APPROVED': row['execution_state']='QUEUED'
        return {k:row.get(k) for k in ('approval_state','execution_state','task_id')}
    async def execution_claim(self,id):
        row=self.approval_rows[id]
        if row['approval_state']!='APPROVED' or row['execution_state'] not in ('QUEUED','RETRYABLE_FAILURE'): return None
        row.update(execution_state='EXECUTING',lease_token=uuid4().hex)
        return dict(row)
    async def executable(self,row):
        return self.approval_rows[row['proposal_id']]['lease_token']==row['lease_token']
    async def execution_finish(self,row,task_id=None,error=None,retryable=False):
        target=self.approval_rows[row['proposal_id']]
        target.update(execution_state='EXECUTED' if task_id else 'RETRYABLE_FAILURE' if retryable else 'FAILED',task_id=task_id)
        self.completed.append((row['proposal_id'],target['execution_state']))
        return [dict(execution_state=target['execution_state'],result_task_id=task_id)]
