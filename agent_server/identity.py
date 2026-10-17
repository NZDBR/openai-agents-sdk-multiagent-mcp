"""Identity is established by Databricks, never custom_inputs.user_id."""
import asyncio
import os
from databricks.sdk import WorkspaceClient
from mlflow.genai.agent_server import get_request_headers


async def employee():
    token = get_request_headers().get('x-forwarded-access-token')
    if token:
        client = WorkspaceClient(host=WorkspaceClient().config.host, token=token, auth_type='pat')
    elif not os.getenv('DATABRICKS_APP_NAME') and os.getenv('ALLOW_LOCAL_PROFILE_IDENTITY') == 'true':
        client = WorkspaceClient()
    else:
        raise PermissionError('Databricks Apps user authorization is required; no forwarded access token was supplied')
    me = await asyncio.to_thread(client.current_user.me)
    if not me.id:
        raise PermissionError('Databricks did not establish an employee identity')
    return me.id, client
