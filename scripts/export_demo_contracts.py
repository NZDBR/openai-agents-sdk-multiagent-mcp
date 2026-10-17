"""Export registered schemas; runtime equality is checked separately."""
import asyncio
import json
from pathlib import Path
from shared.transport import scope_role
from storetime.server import build as time_server
from opstask.server import build as task_server
from opstask.repository import TaskRepository
from confluence.server import build as context_server
import tempfile
async def contracts():
    with tempfile.TemporaryDirectory() as tmp:
        servers={'storetime':time_server()[0], 'opstask':task_server(TaskRepository(Path(tmp)/'tasks.db'))[0], 'confluence':context_server()[0]}
        token=scope_role.set('write')
        try: return {'reconstruction':True,'apps':{name:[t.model_dump(mode='json',exclude_none=True) for t in await mcp.list_tools()] for name,mcp in servers.items()}}
        finally: scope_role.reset(token)
def main():
    Path('mcp-apps/contracts.json').write_text(json.dumps(asyncio.run(contracts()),indent=2,sort_keys=True)+'\n')
if __name__=='__main__': main()
