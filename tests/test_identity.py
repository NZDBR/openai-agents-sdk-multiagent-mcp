import asyncio
from types import SimpleNamespace
import pytest
from agent_server import identity


def test_deployed_runtime_requires_forwarded_user_token(monkeypatch):
    monkeypatch.setenv('DATABRICKS_APP_NAME','test-app')
    monkeypatch.setenv('ALLOW_LOCAL_PROFILE_IDENTITY','true')
    monkeypatch.setattr(identity,'get_request_headers',lambda:{})
    with pytest.raises(PermissionError): asyncio.run(identity.employee())


def test_forwarded_identity_is_verified_not_taken_from_context(monkeypatch):
    clients = []
    def client(**kwargs):
        clients.append(kwargs)
        return SimpleNamespace(config=SimpleNamespace(host='https://workspace.example'),current_user=SimpleNamespace(me=lambda:SimpleNamespace(id='verified-employee')))
    monkeypatch.setattr(identity,'WorkspaceClient',client)
    monkeypatch.setattr(identity,'get_request_headers',lambda:{'x-forwarded-access-token':'test-token'})
    owner,_ = asyncio.run(identity.employee())
    assert owner == 'verified-employee'
    assert clients[-1] == {'host':'https://workspace.example','token':'test-token','auth_type':'pat'}
