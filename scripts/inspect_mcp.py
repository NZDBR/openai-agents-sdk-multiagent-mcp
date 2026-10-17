"""Discover actual tool names/schemas using workspace OAuth, without mutations."""
import argparse
import asyncio
import json
from databricks.sdk import WorkspaceClient
from databricks_openai.agents import McpServer

async def inspect(profile, path):
    client = WorkspaceClient(profile=profile)
    client.current_user.me()
    if not path.startswith('/api/2.0/mcp/'):
        raise ValueError('Only workspace-governed MCP paths are accepted')
    async with McpServer(url=client.config.host.rstrip('/') + path, workspace_client=client) as server:
        for tool in await server.list_tools():
            print(json.dumps({'name': tool.name, 'description': tool.description, 'inputSchema': tool.inputSchema}))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', required=True)
    parser.add_argument('--path', required=True)
    args = parser.parse_args()
    asyncio.run(inspect(args.profile, args.path))

if __name__ == '__main__':
    main()
