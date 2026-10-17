"""User-scoped reads and isolated backend-only writes; explicit demo simulations."""
import os
from agents.mcp import MCPServerStreamableHttp
from databricks_openai.agents import McpServer
from agent_server.identity import app_workspace_client
from agent_server.governance import GovernedMcpServer, LocalDemoMcpServer

def demo_headers(capability,write=False):
    key='DEMO_'+capability.upper()+('_WRITE_TOKEN' if write else '_READ_TOKEN')
    token=os.getenv(key,'')
    if len(token)<24: raise ValueError(key+' must be configured (24+ characters)')
    return {'X-Demo-MCP-Token':token}

def user_mcp_client(capability,settings,user_client,evidence):
    if user_client is None and (capability == 'genie' or settings.connection_mode != 'local_demo'):
        raise PermissionError('A verified employee client is required for user-scoped MCP access')
    host=user_client.config.host if user_client else 'https://unused.invalid'
    url=settings.mcp_urls(host)[capability]
    allow={'genie':(),'storetime':settings.storetime_tools,'opstask':settings.opstask_tools,'confluence':settings.confluence_tools}
    common=dict(capability=capability,allowed=allow[capability],evidence=evidence,name=capability)
    if capability=='genie' or settings.connection_mode=='databricks':
        return GovernedMcpServer(url=url,workspace_client=user_client,**common)
    headers=demo_headers(capability)
    if settings.connection_mode=='local_demo':
        return LocalDemoMcpServer(params={'url':url,'headers':headers},**common)
    return GovernedMcpServer(url=url,params={'headers':headers},workspace_client=user_client,**common)

def app_write_mcp_client(settings, *, databricks_factory=McpServer):
    """Called only by the trusted application approval handler, never by an agent."""
    settings.approval_policy()  # Validates operator intent, not actual policy attachment.
    common=dict(name='Human-approved backend OpsTask writer',max_retry_attempts=0)
    if settings.connection_mode=='databricks':
        # No employee WorkspaceClient is accepted or reused here.
        backend = app_workspace_client()
        return databricks_factory(url=settings.write_mcp_url(backend.config.host),workspace_client=backend,**common)
    headers=demo_headers('opstask',write=True)
    # Both demo roles may use one synthetic server; production bindings must differ.
    url=settings.write_mcp_url(os.getenv('DATABRICKS_HOST','https://unused.invalid'))
    if settings.connection_mode=='local_demo':
        return MCPServerStreamableHttp(params={'url':url,'headers':headers},**common)
    backend=app_workspace_client()
    return databricks_factory(url=url,params={'headers':headers},workspace_client=backend,**common)
