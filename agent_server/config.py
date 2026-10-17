"""Validated resource bindings, not a demo fallback."""
import os
from urllib.parse import urlparse, unquote
from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True)
class Settings:
    model: str
    genie_space: str
    storetime_connection: str
    opstask_read_connection: str
    confluence_connection: str
    storetime_tools: tuple[str, ...]
    opstask_tools: tuple[str, ...]
    confluence_tools: tuple[str, ...]
    task_tool: str
    lakebase_endpoint: str
    workflow_job: int
    opstask_write_connection: str = ''

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
            opstask_read_connection=os.getenv('OPSTASK_READ_CONNECTION') or os.getenv('OPSTASK_CONNECTION', ''),
            opstask_write_connection=os.getenv('OPSTASK_WRITE_CONNECTION', ''),
            confluence_connection=os.getenv('CONFLUENCE_CONNECTION', ''),
            storetime_tools=tools('STORETIME_READ_TOOLS'),
            opstask_tools=tools('OPSTASK_READ_TOOLS'),
            confluence_tools=tools('CONFLUENCE_READ_TOOLS'),
            task_tool=required('OPSTASK_CREATE_TOOL'),
            lakebase_endpoint=os.getenv('LAKEBASE_ENDPOINT') or required('LAKEBASE_AUTOSCALING_ENDPOINT'),
            workflow_job=int(os.getenv('DATABRICKS_WORKFLOW_JOB_ID') or required('BACKGROUND_JOB_ID')),
        )

    @property
    def connection_mode(self):
        mode = os.getenv('MCP_CONNECTION_MODE','databricks')
        if mode not in {'databricks','local_demo','deployed_demo'}:
            raise ValueError('Unknown MCP connection mode')
        return mode

    def mcp_paths(self):
        return {
            'genie': f'/api/2.0/mcp/genie/{quote(self.genie_space, safe="")}',
            'storetime': f'/api/2.0/mcp/external/{quote(self.storetime_connection, safe="")}',
            'opstask': f'/api/2.0/mcp/external/{quote(self.opstask_read_connection, safe="")}',
            'confluence': f'/api/2.0/mcp/external/{quote(self.confluence_connection, safe="")}',
        }

    def mcp_urls(self, host):
        host = host.rstrip('/')
        paths = self.mcp_paths()
        urls = {}
        variables = {'genie': 'GENIE_MCP_URL', 'storetime': 'STORETIME_MCP_URL', 'opstask': 'OPSTASK_MCP_URL', 'confluence': 'CONFLUENCE_MCP_URL'}
        for capability, path in paths.items():
            override = (os.getenv('OPSTASK_READ_MCP_URL') or os.getenv('OPSTASK_MCP_URL')) if capability == 'opstask' else os.getenv(variables[capability])
            if capability != 'genie' and self.connection_mode != 'databricks':
                parsed = urlparse(override or '')
                if parsed.path != '/mcp' or parsed.username or parsed.password or parsed.query or parsed.fragment:
                    raise ValueError('Demo MCP requires explicit /mcp endpoint without embedded credentials')
                if self.connection_mode == 'local_demo':
                    if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1','localhost','::1'}:
                        raise ValueError('Local demo MCP requires loopback HTTP')
                else:
                    allowed = set(os.getenv('DEMO_MCP_ALLOWED_HOSTS','').split(','))
                    if parsed.scheme != 'https' or parsed.hostname not in allowed or parsed.port not in {None,443}:
                        raise ValueError('Deployed demo requires HTTPS and exact trusted host')
                urls[capability] = override
                continue
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


    def write_mcp_url(self, host):
        """A dedicated production write binding; never fall back to the read route."""
        if self.connection_mode != 'databricks':
            url = os.getenv('DEMO_OPSTASK_WRITE_MCP_URL') or self.mcp_urls(host)['opstask']
            parsed = urlparse(url)
            if parsed.path != '/mcp' or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError('Invalid demo write MCP endpoint')
            if self.connection_mode == 'local_demo':
                if parsed.scheme != 'http' or parsed.hostname not in {'localhost','127.0.0.1','::1'}:
                    raise ValueError('Local demo write endpoint requires loopback HTTP')
            elif parsed.scheme != 'https' or parsed.hostname not in set(os.getenv('DEMO_MCP_ALLOWED_HOSTS','').split(',')) or parsed.port not in {None,443}:
                raise ValueError('Deployed demo writer requires an exact trusted HTTPS host')
            return url
        override = os.getenv('OPSTASK_WRITE_MCP_URL')
        connection = self.opstask_write_connection
        if not override and (not connection or '<' in connection):
            raise ValueError('A distinct OPSTASK_WRITE_CONNECTION or OPSTASK_WRITE_MCP_URL is required')
        url = override or host.rstrip('/') + '/api/2.0/mcp/external/' + quote(connection, safe='')
        parsed, workspace = urlparse(url), urlparse(host)
        prefix = '/api/2.0/mcp/external/'
        if parsed.scheme != 'https' or parsed.netloc != workspace.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.path.startswith(prefix) or not parsed.path[len(prefix):] or '<' in url:
            raise ValueError('Write MCP must use the configured workspace governed external route')
        read = urlparse(self.mcp_urls(host)['opstask'])
        if unquote(parsed.path).rstrip('/') == unquote(read.path).rstrip('/'):
            raise ValueError('Production OpsTask read and write services must be distinct')
        return url

    def approval_policy(self):
        """Operator configuration only; not proof a Gateway policy is attached."""
        mode = os.getenv('OPSTASK_APPROVAL_MODE', 'application')
        if mode not in {'application','application_and_gateway_ask'}:
            raise ValueError('Unknown OpsTask approval mode')
        policy = os.getenv('OPSTASK_GATEWAY_POLICY_ID', '')
        if mode == 'application_and_gateway_ask' and (not policy or '<' in policy):
            raise ValueError('Mode B requires the operator-selected Gateway policy identifier')
        return {'mode':mode,'policy_id':policy or None}
