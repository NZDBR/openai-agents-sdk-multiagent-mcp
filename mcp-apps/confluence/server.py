from typing import Annotated
from pydantic import Field
from mcp.types import ToolAnnotations
from shared.contracts import Identifier, Result, Documents, DocumentItem
from shared.transport import make_server, serve
from confluence.repository import Corpus
READ=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
def build(corpus=None,**auth):
    corpus=corpus or Corpus()
    mcp,app=make_server('confluence',corpus.ready,**auth)
    @mcp.tool(annotations=READ)
    def search_company_context(query:Annotated[str,Field(min_length=1,max_length=1000)],limit:Annotated[int,Field(ge=1,le=20)]=5)->Result[Documents]:
        """Search stored synthetic company context and policy verbatim."""
        return Result(source='confluence',data=Documents(documents=corpus.search(query,limit)))
    @mcp.tool(annotations=READ)
    def get_policy_document(source_id:Identifier)->Result[DocumentItem]:
        """Retrieve one stored synthetic policy section with provenance."""
        return Result(source='confluence',data=DocumentItem(document=corpus.get(source_id)))
    for tool in mcp._tool_manager.list_tools():
        tool.fn_metadata.arg_model.model_config['extra']='forbid'
        tool.fn_metadata.arg_model.model_rebuild(force=True)
        tool.parameters['additionalProperties']=False
    return mcp,app
def create_app(): return build()[1]()
def main(): serve(create_app,8103)
if __name__=='__main__': main()
