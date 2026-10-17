"""Deterministic behavioral evaluation, optionally logged to MLflow.

Run: .venv/bin/python -m scripts.evaluate [--mlflow]
This is a baseline behavior evaluation, not a model-quality claim.
"""
import argparse
import os
import tempfile
from fastapi.testclient import TestClient
from app import main


def evaluate():
    with tempfile.TemporaryDirectory() as tmp:
        old_dsn = os.environ.pop('LAKEBASE_DSN', None)
        old_mode, old_db = main.MODE, main.DB
        main.MODE, main.DB = 'demo', tmp + '/eval.db'
        try:
            client = TestClient(main.app, headers={'X-Session-ID': 'evaluationSession123456789'})
            cases = [('Why is training behind?', 'coverage gaps'), ('What is company policy?', 'cannot'), ('Change the schedule', 'cannot')]
            outcomes = [expected in client.post('/api/chat', json={'message': prompt}).json()['answer'].lower() for prompt, expected in cases]
            return {'cases': len(outcomes), 'passed': sum(outcomes), 'pass_rate': sum(outcomes) / len(outcomes)}
        finally:
            main.MODE, main.DB = old_mode, old_db
            if old_dsn is not None:
                os.environ['LAKEBASE_DSN'] = old_dsn

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mlflow', action='store_true')
    args = parser.parse_args()
    result = evaluate()
    if args.mlflow:
        import mlflow
        with mlflow.start_run(run_name='store-operations-contract-evaluation'):
            mlflow.log_metrics(result)
    print(result)
    raise SystemExit(0 if result['cases'] == result['passed'] else 1)
