"""Validated resource bindings, not a demo fallback."""
import os
from urllib.parse import urlparse
from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True)
class Settings:
    model: str
    genie_space: str
    storetime_connection: str
    opstask_connection: str
    confluence_connection: str
    storetime_tools: tuple[str, ...]
    opstask_tools: tuple[str, ...]
    confluence_tools: tuple[str, ...]
    task_tool: str
    lakebase_endpoint: str
    workflow_job: int

    @classmethod
    def load(cls):
        def required(name):
            value = os.environ.get(name, '').strip()
            if not value or '<' in value:
                raise ValueError(f'{name} must reference a real deployed resource')
            return value
        def tools(name):
            result = tuple(v.strip() for v in required(name).split(',') if v.strip())
            if not result:
                raise ValueError(f'{name} cannot be empty')
            return result
        return cls(
            model=required('MODEL_ENDPOINT'), genie_space=required('GENIE_SPACE_ID'),
            storetime_connection=os.getenv('STORETIME_CONNECTION', ''),
            opstask_connection=os.getenv('OPSTASK_CONNECTION', ''),
            confluence_connection=os.getenv('CONFLUENCE_CONNECTION', ''),
            storetime_tools=tools('STORETIME_READ_TOOLS'),
            opstask_tools=tools('OPSTASK_READ_TOOLS'),
            confluence_tools=tools('CONFLUENCE_READ_TOOLS'),
            task_tool=required('OPSTASK_CREATE_TOOL'),
            lakebase_endpoint=os.getenv('LAKEBASE_ENDPOINT') or required('LAKEBASE_AUTOSCALING_ENDPOINT'),
            workflow_job=int(os.getenv('DATABRICKS_WORKFLOW_JOB_ID') or required('BACKGROUND_JOB_ID')),
        )

    def mcp_paths(self):
        return {
            'genie': f'/api/2.0/mcp/genie/{quote(self.genie_space, safe="")}',
            'storetime': f'/api/2.0/mcp/external/{quote(self.storetime_connection, safe="")}',
            'opstask': f'/api/2.0/mcp/external/{quote(self.opstask_connection, safe="")}',
            'confluence': f'/api/2.0/mcp/external/{quote(self.confluence_connection, safe="")}',
        }

    def mcp_urls(self, host):
        host = host.rstrip('/')
        paths = self.mcp_paths()
        urls = {}
        variables = {'genie': 'GENIE_MCP_URL', 'storetime': 'STORETIME_MCP_URL', 'opstask': 'OPSTASK_MCP_URL', 'confluence': 'CONFLUENCE_MCP_URL'}
        for capability, path in paths.items():
            override = os.getenv(variables[capability])
            if capability != 'genie' and not override and path.endswith('/'):
                raise ValueError(f'{capability} requires a UC connection or an explicit governed MCP URL')
            url = override or host + path
            parsed, workspace = urlparse(url), urlparse(host)
            # OAuth tokens may only go to the authenticated workspace gateway.
            if parsed.scheme != 'https' or parsed.netloc != workspace.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError('MCP must use the authenticated workspace HTTPS gateway origin')
            expected = '/api/2.0/mcp/genie/' if capability == 'genie' else '/api/2.0/mcp/external/'
            if not parsed.path.startswith(expected) or not parsed.path[len(expected):]:
                raise ValueError(f'{capability} must use its governed MCP route')
            urls[capability] = url
        return urls
