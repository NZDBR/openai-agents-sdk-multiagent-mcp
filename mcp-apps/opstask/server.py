import os
from datetime import date
from typing import Annotated, Literal
from pydantic import Field
from mcp.types import ToolAnnotations
from shared.contracts import Identifier, Result, Tasks, TaskItem, TaskCreated
from shared.transport import make_server, serve
from opstask.repository import TaskRepository
READ=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
def build(repository=None,**auth):
    repository=repository or TaskRepository(os.getenv('MCP_TASK_DB','.demo-data/tasks.db'))
    mcp,app=make_server('opstask',repository.ready,**auth)
    @mcp.tool(annotations=READ)
    def list_followups(store_id:Identifier,status:Literal['all','open','in_progress','completed']='all',limit:Annotated[int,Field(ge=1,le=100)]=50,cursor:str|None=None)->Result[Tasks]:
        """List synthetic tasks; no diagnosis or mutation."""
        return Result(source='opstask',data=repository.list(store_id,status,limit,cursor))
    @mcp.tool(annotations=READ)
    def get_task(task_id:Identifier)->Result[TaskItem]:
        """Look up one synthetic task."""
        return Result(source='opstask',data=TaskItem(task=repository.get(task_id)))
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False,destructiveHint=False,idempotentHint=True,openWorldHint=False))
    def create_task(title:Annotated[str,Field(min_length=3,max_length=300)],store_id:Identifier,assignee:Identifier,due_date:date,idempotency_key:Identifier)->Result[TaskCreated]:
        """Create an idempotent synthetic task using the separately authorized writer."""
        return Result(source='opstask',data=repository.create(title,store_id,assignee,due_date,idempotency_key))
    for tool in mcp._tool_manager.list_tools():
        tool.fn_metadata.arg_model.model_config['extra']='forbid'
        tool.fn_metadata.arg_model.model_rebuild(force=True)
        tool.parameters['additionalProperties']=False
    return mcp,app
def create_app(): return build()[1]()
def main(): serve(create_app,8102)
if __name__=='__main__': main()
