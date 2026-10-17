from datetime import date
from mcp.types import ToolAnnotations
from shared.contracts import Identifier, Result, Schedules, Blocks, Hours, Reasons, Diagnosis
from shared.transport import make_server, serve
from storetime.service import StoreTime
READ=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
def build(service=None,**auth):
    service=service or StoreTime()
    mcp,app=make_server('storetime',service.ready,**auth)
    @mcp.tool(annotations=READ)
    def get_schedules(store_id:Identifier,start_date:date,end_date:date)->Result[Schedules]:
        """Look up synthetic employee schedules, read only."""
        return Result(source='storetime',data=Schedules(schedules=service.window(store_id,start_date,end_date)[0]))
    @mcp.tool(annotations=READ)
    def get_training_blocks(store_id:Identifier,start_date:date,end_date:date)->Result[Blocks]:
        """Look up protected synthetic training blocks."""
        return Result(source='storetime',data=Blocks(blocks=service.window(store_id,start_date,end_date)[1]))
    @mcp.tool(annotations=READ)
    def get_training_hours(store_id:Identifier,start_date:date,end_date:date)->Result[Hours]:
        """Read scheduled, protected, completed and converted training hours."""
        return Result(source='storetime',data=Hours(hours=service.hours(store_id,start_date,end_date)))
    @mcp.tool(annotations=READ)
    def get_coverage_reasons(store_id:Identifier,start_date:date,end_date:date)->Result[Reasons]:
        """Read recorded synthetic coverage reasons."""
        return Result(source='storetime',data=Reasons(reasons=service.window(store_id,start_date,end_date)[2]))
    @mcp.tool(annotations=READ)
    def diagnose_training_gap(store_id:Identifier,start_date:date,end_date:date)->Result[Diagnosis]:
        """Diagnose recorded training gaps without changing schedules or creating tasks."""
        return Result(source='storetime',data=Diagnosis(diagnostic=service.diagnose(store_id,start_date,end_date)))
    for tool in mcp._tool_manager.list_tools():
        tool.fn_metadata.arg_model.model_config['extra']='forbid'
        tool.fn_metadata.arg_model.model_rebuild(force=True)
        tool.parameters['additionalProperties']=False
    return mcp,app
def create_app(): return build()[1]()
def main(): serve(create_app,8101)
if __name__=='__main__': main()
