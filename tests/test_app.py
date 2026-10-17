import pytest
from fastapi.testclient import TestClient
from app import main

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'MODE', 'demo')
    monkeypatch.delenv('LAKEBASE_DSN', raising=False)
    monkeypatch.setattr(main, 'DB', str(tmp_path / 'memory.db'))
    return TestClient(main.app, headers={'X-Session-ID': 'a' * 32})

def test_diagnostics(client):
    r = client.post('/api/chat', json={'message': 'Why is training behind?'})
    assert r.status_code == 200
    assert r.json()['evidence'][0]['source'].startswith('StoreTime')

def test_explicit_approval_and_idempotency(client):
    proposal = client.post('/api/chat', json={'message': 'Create a training follow-up'}).json()['proposal']
    assert client.get('/api/tasks').json() == []
    for _ in range(2):
        assert client.post('/api/approvals/' + proposal['id'], json={'approve': True}).json()['status'] == 'created'
    assert len(client.get('/api/tasks').json()) == 1

def test_rejection_and_isolation(client):
    proposal = client.post('/api/chat', json={'message': 'Create a task'}).json()['proposal']
    url = '/api/approvals/' + proposal['id']
    assert client.post(url, json={'approve': True}, headers={'X-Session-ID': 'b'*32}).status_code == 404
    assert client.post(url, json={'approve': False}).json()['status'] == 'rejected'
    assert client.post(url, json={'approve': True}).json()['status'] == 'rejected'
    assert client.get('/api/tasks').json() == []

def test_live_writes_fail_closed(client, monkeypatch):
    monkeypatch.setattr(main, 'MODE', 'live')
    assert client.post('/api/approvals/unknown', json={'approve': True}).status_code == 401


def test_memory_consent_isolation_and_deletion(client):
    url = '/api/memory/long-term'
    assert client.post(url, json={'content': 'Prefer West region', 'consent': False}).status_code == 422
    memory = client.post(url, json={'content': 'Prefer West region', 'consent': True}).json()
    assert client.get(url).json()[0]['content'] == 'Prefer West region'
    assert client.get(url, headers={'X-Session-ID': 'b'*32}).json() == []
    assert client.delete(url + '/' + memory['id'], headers={'X-Session-ID': 'b'*32}).status_code == 404
    assert client.delete(url + '/' + memory['id']).status_code == 200
    assert client.get(url).json() == []


def test_short_term_memory(client):
    client.post('/api/chat', json={'message': 'Compare stores'})
    assert len(client.get('/api/memory/short-term').json()) == 2
    assert client.delete('/api/memory/short-term').status_code == 200
    assert client.get('/api/memory/short-term').json() == []


def test_schedule_changes_refused(client):
    data = client.post('/api/chat', json={'message': 'Change the schedule'}).json()
    assert 'cannot change schedules' in data['answer']
    assert data['proposal'] is None


def test_workflow_confirmation_and_repeatability(client):
    url = '/api/workflows'
    body = {'request_id': 'workflowRequest1234567890', 'confirm': False}
    assert client.post(url, json=body).status_code == 422
    body['confirm'] = True
    first = client.post(url, json=body).json()
    assert first['status'] == 'simulated'
    assert client.post(url, json=body).json() == first


def test_live_approval_adapter_called_only_once(client, monkeypatch):
    from app.storage import connect
    calls = []
    async def employee(request):
        return 'employee-1'
    async def write(title, key):
        calls.append((title, key))
        return 'REMOTE-123'
    monkeypatch.setattr(main, 'MODE', 'live')
    monkeypatch.setattr(main, 'database', lambda: connect(main.DB))
    monkeypatch.setattr(main.integrations, 'employee_id', employee)
    monkeypatch.setattr(main.integrations, 'create_task', write)
    proposal = client.post('/api/chat', json={'message': 'Create a follow-up'}).json()['proposal']
    assert calls == []
    url = '/api/approvals/' + proposal['id']
    assert client.post(url, json={'approve': True}).json()['task_id'] == 'REMOTE-123'
    assert client.post(url, json={'approve': True}).json()['task_id'] == 'REMOTE-123'
    assert len(calls) == 1


def test_ambiguous_write_not_retried(client, monkeypatch):
    from app.storage import connect
    calls = []
    async def employee(request):
        return 'employee-1'
    async def write(title, key):
        calls.append(key)
        raise TimeoutError()
    monkeypatch.setattr(main, 'MODE', 'live')
    monkeypatch.setattr(main, 'database', lambda: connect(main.DB))
    monkeypatch.setattr(main.integrations, 'employee_id', employee)
    monkeypatch.setattr(main.integrations, 'create_task', write)
    proposal = client.post('/api/chat', json={'message': 'Create a task'}).json()['proposal']
    url = '/api/approvals/' + proposal['id']
    assert client.post(url, json={'approve': True}).status_code == 502
    assert client.post(url, json={'approve': True}).json()['status'] == 'needs_reconciliation'
    assert len(calls) == 1


def test_invalid_session(client):
    assert client.post('/api/chat', json={'message': 'Hello'}, headers={'X-Session-ID': '../bad'}).status_code == 400
