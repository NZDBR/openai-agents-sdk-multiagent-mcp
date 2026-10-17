"""Explicit demo transport selection; reconstructed before identity refactor."""
import os
from agents.mcp import MCPServerStreamableHttp
from databricks_openai.agents import McpServer
from agent_server.governance import GovernedMcpServer, LocalDemoMcpServer

def demo_headers(capability,write=False):
    key='DEMO_'+capability.upper()+('_WRITE_TOKEN' if write else '_READ_TOKEN')
    token=os.getenv(key,'')
    if len(token)<24: raise ValueError(key+' must be configured (24+ characters)')
    return {'X-Demo-MCP-Token':token}

def read_client(capability,settings,client,evidence):
    host=client.config.host if client else 'https://unused.invalid'
    url=settings.mcp_urls(host)[capability]
    allow={'genie':(),'storetime':settings.storetime_tools,'opstask':settings.opstask_tools,'confluence':settings.confluence_tools}
    common=dict(capability=capability,allowed=allow[capability],evidence=evidence,name=capability)
    if capability=='genie' or settings.connection_mode=='databricks':
        return GovernedMcpServer(url=url,workspace_client=client,**common)
    headers=demo_headers(capability)
    if settings.connection_mode=='local_demo':
        return LocalDemoMcpServer(params={'url':url,'headers':headers},**common)
    return GovernedMcpServer(url=url,params={'headers':headers},workspace_client=client,**common)

def write_client(settings,client,databricks_factory=McpServer):
    url=settings.mcp_urls(client.config.host)['opstask']
    common=dict(name='Human-approved OpsTask writer',max_retry_attempts=0)
    if settings.connection_mode=='databricks':
        return databricks_factory(url=url,workspace_client=client,**common)
    headers=demo_headers('opstask',write=True)
    if settings.connection_mode=='local_demo':
        return MCPServerStreamableHttp(params={'url':url,'headers':headers},**common)
    return databricks_factory(url=url,params={'headers':headers},workspace_client=client,**common)
