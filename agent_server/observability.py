"""Fail closed unless the MLflow experiment is bound to governed UC traces."""
import os
import mlflow
from mlflow.entities.trace_location import UnityCatalog


def configure_tracing():
    experiment_id = os.environ.get('MLFLOW_EXPERIMENT_ID')
    if not experiment_id:
        raise ValueError('Bind a real MLflow experiment resource before startup')
    experiment = mlflow.get_experiment(experiment_id)
    if not experiment or not isinstance(experiment.trace_location, UnityCatalog):
        raise ValueError('Experiment must be provisioned with a Unity Catalog trace location; run scripts.configure_traces with your selected catalog/schema')
    mlflow.set_experiment(experiment_id=experiment_id)
