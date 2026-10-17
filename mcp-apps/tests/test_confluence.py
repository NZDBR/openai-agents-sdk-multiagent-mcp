import pytest
from confluence.repository import Corpus
from shared.demo_data import DATA
from agent_server.agent import Answer
from agent_server.governance import Evidence,enforce_policy
from mcp.types import CallToolResult

def test_provenance_exact_text_and_no_invented_policy():
    corpus=Corpus();document=corpus.get('DEMO-TRAINING-1')
    assert document in corpus.search('protected training')
    assert document.text==(DATA/'policies/protected-training.md').read_text()
    assert document.source_url.startswith('https://demo.invalid/') and document.section and document.title and document.document_id
    assert corpus.search('zzzznomatch')==[]
    with pytest.raises(ValueError): corpus.get('unknown')
    evidence=Evidence();evidence.record('confluence','get_policy_document',CallToolResult(content=[],structuredContent={'mode':'demo','data':{'document':document.model_dump()}}))
    answer=Answer(answer='Generated prose',citations=[document.source_id],is_policy=True,policy_quotes=[document.text])
    assert document.text in enforce_policy(answer,evidence)
    answer.policy_quotes=['Invented policy text that was never in the corpus.']
    assert 'cannot establish' in enforce_policy(answer,evidence)
