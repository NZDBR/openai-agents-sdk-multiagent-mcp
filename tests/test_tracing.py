import mlflow
from agent_server import observability
from mlflow.entities.trace_location import UnityCatalog
import pytest


def test_uc_trace_binding_required(monkeypatch):
    monkeypatch.setenv('MLFLOW_EXPERIMENT_ID','test')
    monkeypatch.setattr(mlflow,'get_experiment',lambda id: type('Experiment',(),{'trace_location':None})())
    with pytest.raises(ValueError,match='Unity Catalog'):
        observability.configure_tracing()
    location = UnityCatalog(catalog_name='test_catalog',schema_name='test_schema')
    monkeypatch.setattr(mlflow,'get_experiment',lambda id: type('Experiment',(),{'trace_location':location})())
    calls = []
    monkeypatch.setattr(mlflow,'set_experiment',lambda **kw: calls.append(kw))
    observability.configure_tracing()
    assert calls == [{'experiment_id':'test'}]


def test_actual_local_trace_can_be_read(tmp_path, monkeypatch):
    # Verifies instrumentation/readback locally, not Databricks export.
    old_uri = mlflow.get_tracking_uri()
    monkeypatch.delenv('MLFLOW_EXPERIMENT_ID',raising=False)
    monkeypatch.delenv('MLFLOW_EXPERIMENT_NAME',raising=False)
    try:
        mlflow.set_tracking_uri('sqlite:///' + str(tmp_path/'traces.db'))
        mlflow.set_experiment('local-contract-tracing')
        @mlflow.trace(name='store_operations_test_retrieval',span_type='RETRIEVER')
        def retrieve():
            return [{'page_content':'Test-only evidence','metadata':{'capability':'confluence'}}]
        retrieve()
        trace_id = mlflow.get_last_active_trace_id()
        assert trace_id
        mlflow.flush_trace_async_logging()
        trace = mlflow.get_trace(trace_id)
        assert trace is not None
        assert any(span.name == 'store_operations_test_retrieval' for span in trace.data.spans)
    finally:
        mlflow.set_tracking_uri(old_uri)
