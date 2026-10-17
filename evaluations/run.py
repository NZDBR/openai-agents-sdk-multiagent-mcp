"""Evaluate actual agent invocations with trace-linked MLflow scorers.

Uses real Databricks data/model calls; never substitutes canned answers. Run
unit tests to validate dataset/scorer logic without a workspace.
"""
import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

import mlflow
from mlflow.types.responses import ResponsesAgentRequest
from evaluations.scorers import suite


def load_dataset(path=None):
    path = Path(path) if path else Path(__file__).parent / 'datasets/store_operations.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def prediction_output(result):
    payload = result.model_dump()
    text = '\n'.join(part.get('text', '') for item in payload.get('output', []) for part in item.get('content', []) if part.get('type') == 'output_text')
    return {'answer': text, **(payload.get('custom_outputs') or {}), 'abstained': 'cannot establish' in text.lower()}


def main():
    from dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument('--judge-model', required=True, help='databricks:/<judge-serving-endpoint>')
    parser.add_argument('--dataset')
    args = parser.parse_args()
    from agent_server.agent import configure_model, invoke_handler
    from agent_server.observability import configure_tracing
    configure_tracing()
    configure_model()

    async def predict(question):
        request = ResponsesAgentRequest(input=[{'role': 'user', 'content': question}], custom_inputs={'session_id': 'eval-' + uuid4().hex})
        result = await invoke_handler(request)
        return prediction_output(result)

    # MLflow owns trace linkage around predict_fn. Each row gets a unique isolated session.
    mlflow.genai.evaluate(data=load_dataset(args.dataset), predict_fn=predict, scorers=suite(args.judge_model))

if __name__ == '__main__':
    main()
