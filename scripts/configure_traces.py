"""Bind an existing experiment to an explicitly selected UC trace schema.

This provisions trace tables. Run only after the owner has selected the schema
and authorized creation there. It never chooses a schema on the user's behalf.
"""
import argparse
import os
import mlflow
from mlflow.entities.trace_location import UnityCatalog


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--experiment-id', required=True)
    parser.add_argument('--catalog', required=True)
    parser.add_argument('--schema', required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--warehouse-id')
    args = parser.parse_args()
    from databricks.sdk import WorkspaceClient
    client = WorkspaceClient(profile=args.profile)
    client.current_user.me()  # Verify authentication before provisioning.
    client.schemas.get(f'{args.catalog}.{args.schema}')
    warehouse = args.warehouse_id
    if not warehouse:
        warehouses = list(client.warehouses.list())
        warehouses.sort(key=lambda w: str(w.state) != 'State.RUNNING')
        warehouse = next((w.id for w in warehouses if w.id), None)
    if not warehouse:
        raise RuntimeError('No accessible SQL warehouse was discovered')
    os.environ['MLFLOW_TRACING_SQL_WAREHOUSE_ID'] = warehouse
    mlflow.set_tracking_uri('databricks://' + args.profile)
    location = UnityCatalog(catalog_name=args.catalog, schema_name=args.schema)
    experiment = mlflow.get_experiment(args.experiment_id)
    existing = experiment.trace_location
    if existing:
        if not isinstance(existing, UnityCatalog) or existing.catalog_name != args.catalog or existing.schema_name != args.schema:
            raise ValueError('Experiment is already bound to a different location; use a new experiment')
        mlflow.set_experiment(experiment_id=args.experiment_id)
    else:
        mlflow.set_experiment(experiment_id=args.experiment_id, trace_location=location)
    print('Experiment bound to the selected Unity Catalog trace location.')

if __name__ == '__main__':
    main()
