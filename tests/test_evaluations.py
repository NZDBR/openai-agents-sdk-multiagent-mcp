from evaluations.run import load_dataset
from evaluations.scorers import tool_selection, task_approval_safety, policy_provenance, suite


def test_dataset_and_all_requested_scorers():
    data = load_dataset()
    assert len(data) >= 12
    assert all('question' in row['inputs'] and 'expectations' in row for row in data)
    names = {s.name for s in suite('databricks:/test-judge')}
    assert {'tool_selection','task_approval_safety','policy_compliance','response_quality','retrieval_groundedness'}.issubset(names)


def test_scorers_fail_unsafe_or_wrong_tool_outputs():
    assert not tool_selection(outputs={'tool_calls':[{'capability':'genie'}]}, expectations={'required_capabilities':['storetime']})
    assert tool_selection(outputs={'tool_calls':[{'capability':'storetime'}]}, expectations={'required_capabilities':['storetime']})
    assert not task_approval_safety(outputs={'mutation':True})
    assert task_approval_safety(outputs={'proposals':[{'status':'pending'}]})
    assert not policy_provenance(outputs={'citations':['fake']}, expectations={'policy_query':True})
    assert policy_provenance(outputs={'abstained':True}, expectations={'policy_query':True})


def test_prediction_output_uses_actual_responses_content_shape():
    from agent_server.agent import response
    from evaluations.run import prediction_output
    result = response('I cannot establish that policy.',{'tool_calls':[],'citations':[]})
    output = prediction_output(result)
    assert output['abstained'] is True
    assert output['answer'] == 'I cannot establish that policy.'
