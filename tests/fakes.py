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
        self.proposals = {}
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
        id = uuid4().hex
        self.proposals[id] = {'owner': owner, 'session': session, 'payload': payload, 'status': 'pending'}
        return {'approval_id': id, 'task': payload, 'status': 'pending'}
    async def claim(self, owner, session, id, approve):
        row = self.proposals[id]
        if row['owner'] != owner or row['session'] != session:
            raise PermissionError('wrong owner/session')
        if row['status'] != 'pending':
            return {'status': row['status'], 'external_id': row.get('external_id')}
        row['status'] = 'executing' if approve else 'rejected'
        return {'payload': row['payload'], 'status': row['status']}
    async def complete(self, id, state, external_id=None):
        self.proposals[id].update(status=state, external_id=external_id)
        self.completed.append((id, state))
