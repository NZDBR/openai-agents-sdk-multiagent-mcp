"""Explicit employee/OBO and backend OAuth identities; never from custom_inputs."""
import asyncio
import os
from databricks.sdk import WorkspaceClient
from mlflow.genai.agent_server import get_request_headers


def _required(name):
    value = os.getenv(name, '').strip()
    if not value or '<' in value:
        raise ValueError(f'{name} must be configured by the trusted deployment')
    return value


def user_workspace_client():
    """Preserve the platform-forwarded employee credential; never fall back to SP."""
    mode = os.getenv('USER_AUTHORIZATION_MODE', 'obo')
    if mode not in {'obo', 'local_profile'}:
        raise ValueError('USER_AUTHORIZATION_MODE must be obo or local_profile')
    token = get_request_headers().get('x-forwarded-access-token')
    if token:
        # The pinned template uses auth_type=pat to pass through a bearer token;
        # this does not mean the forwarded OAuth token is a personal access token.
        return WorkspaceClient(host=_required('DATABRICKS_HOST'), token=token, auth_type='pat')
    if mode == 'local_profile' and not os.getenv('DATABRICKS_APP_NAME') and os.getenv('ALLOW_LOCAL_PROFILE_IDENTITY') == 'true':
        return WorkspaceClient()
    raise PermissionError('Databricks Apps user authorization requires a forwarded employee token')


async def employee():
    client = user_workspace_client()
    me = await asyncio.to_thread(client.current_user.me)
    if not me.id:
        raise PermissionError('Databricks did not establish an employee identity')
    return me.id, client


def app_workspace_client():
    """Trusted backend only. Force OAuth M2M; no user token/PAT/profile fallback."""
    mode = os.getenv('OPSTASK_WRITE_AUTH_MODE', 'app')
    if mode == 'app':
        if not os.getenv('DATABRICKS_APP_NAME'):
            raise PermissionError('App write identity requires a Databricks App deployment; configure m2m for another backend')
        client_id = _required('DATABRICKS_CLIENT_ID')
        client_secret = _required('DATABRICKS_CLIENT_SECRET')
    elif mode == 'm2m':
        client_id = _required('OPSTASK_WRITE_CLIENT_ID')
        client_secret = _required('OPSTASK_WRITE_CLIENT_SECRET')
    else:
        raise ValueError('OPSTASK_WRITE_AUTH_MODE must be app or m2m')
    scopes = [s.strip() for s in _required('OPSTASK_WRITE_OAUTH_SCOPES').split(',') if s.strip()]
    if not scopes:
        raise ValueError('Configure supported backend MCP OAuth scopes')
    return WorkspaceClient(host=_required('DATABRICKS_HOST'), client_id=client_id, client_secret=client_secret,
                           auth_type='oauth-m2m', scopes=scopes)
