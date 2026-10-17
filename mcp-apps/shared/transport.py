"""MCP SDK Streamable HTTP, scoped demo credentials, public readiness."""
import argparse
from contextvars import ContextVar
import hmac
import jsonschema
import os
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse
import uvicorn

scope_role = ContextVar('demo_mcp_role', default='read')
class ScopedMCP(FastMCP):
    async def list_tools(self):
        tools = await super().list_tools()
        return [t for t in tools if t.name != 'create_task' or scope_role.get() == 'write']
    async def call_tool(self, name, arguments):
        if name == 'create_task' and scope_role.get() != 'write':
            raise ToolError('A separately authorized human-approved writer is required')
        tool = self._tool_manager.get_tool(name)
        if tool is not None:
            try: jsonschema.validate(arguments, tool.parameters)
            except jsonschema.ValidationError: raise ToolError('Invalid tool arguments') from None
        return await super().call_tool(name, arguments)

class DemoAuth:
    def __init__(self, app, read_token, write_token=None):
        if len(read_token) < 24 or (write_token is not None and (len(write_token)<24 or hmac.compare_digest(read_token,write_token))):
            raise ValueError('Configure distinct demo tokens of at least 24 characters')
        self.app,self.read,self.write = app,read_token,write_token
    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'] in {'/health','/ready'}:
            return await self.app(scope,receive,send)
        supplied = dict(scope['headers']).get(b'x-demo-mcp-token',b'').decode('utf-8',errors='replace')
        role = 'write' if self.write and hmac.compare_digest(supplied,self.write) else 'read' if hmac.compare_digest(supplied,self.read) else None
        if role is None:
            return await JSONResponse({'error':'Demo credential required'},status_code=401)(scope,receive,send)
        token = scope_role.set(role)
        try:
            await self.app(scope,receive,send)
        finally:
            scope_role.reset(token)

def make_server(name, readiness, read_token=None, write_token=None):
    hosts = ['127.0.0.1:*','localhost:*','[::1]:*']
    public = os.getenv('MCP_PUBLIC_HOST')
    if public: hosts.append(public)
    mcp = ScopedMCP(name,stateless_http=True,json_response=True,streamable_http_path='/mcp',
                    transport_security=TransportSecuritySettings(allowed_hosts=hosts))
    @mcp.custom_route('/health',methods=['GET'])
    async def health(request):
        return JSONResponse({'status':'alive','service':name,'mode':'demo'})
    @mcp.custom_route('/ready',methods=['GET'])
    async def ready(request):
        try:
            readiness()
            return JSONResponse({'status':'ready','service':name,'mode':'demo'})
        except Exception:
            return JSONResponse({'status':'not_ready','service':name,'mode':'demo'},status_code=503)
    def application():
        return DemoAuth(mcp.streamable_http_app(),read_token or os.getenv('MCP_READ_TOKEN',''),
                        write_token if write_token is not None else os.getenv('MCP_WRITE_TOKEN') if name=='opstask' else None)
    return mcp,application

def serve(factory,port):
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='0.0.0.0')
    parser.add_argument('--port',type=int,default=int(os.getenv('DATABRICKS_APP_PORT',port)))
    args=parser.parse_args()
    uvicorn.run(factory(),host=args.host,port=args.port)
