"""Enforce capability boundaries before MCP dispatch and policy delivery."""
import json
import re
import mlflow
from dataclasses import dataclass, field

from databricks_openai.agents import McpServer

WRITE = re.compile(r'(^|[_\W])(create|update|delete|approve|mutate|write|assign|schedule_shift|cancel|patch)([_\W]|$)', re.I)


@dataclass
class Evidence:
    calls: list[dict] = field(default_factory=list)

    def record(self, capability, tool, result):
        if result.isError:
            return
        payload = result.structuredContent or [part.model_dump() for part in result.content]
        self.calls.append({'capability': capability, 'tool': tool, 'result': payload})

    def source_ids(self, capability):
        sources = set()
        def visit(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in {'url', 'source_url', 'document_id', 'source_id'} and isinstance(child, str):
                        sources.add(child)
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
            elif isinstance(value, str):
                try:
                    decoded = json.loads(value)
                    if not isinstance(decoded, str):
                        visit(decoded)
                except (ValueError, TypeError):
                    pass
                sources.update(re.findall(r'https://[^\s<>"\)]+', value))
        for call in self.calls:
            if call['capability'] == capability:
                visit(call['result'])
        return sources


class GovernedMcpServer(McpServer):
    """Defense in depth: list filtering AND direct call enforcement.

    External tools require audited exact names; managed Genie is restricted by
    its native space-only endpoint. Mutations are excluded from all model views.
    """
    def __init__(self, *, capability, allowed, evidence, **kwargs):
        self.capability, self.allowed, self.evidence = capability, frozenset(allowed), evidence
        if any(WRITE.search(name) for name in self.allowed):
            raise ValueError(f'{capability} read allowlist contains a mutating tool')
        if capability != 'genie' and not self.allowed:
            raise ValueError('External MCP requires an audited read-only allowlist')
        super().__init__(**kwargs)

    def permitted(self, name):
        return not WRITE.search(name) and (self.capability == 'genie' or name in self.allowed)

    async def list_tools(self, *args, **kwargs):
        tools = await super().list_tools(*args, **kwargs)
        filtered = [tool for tool in tools if self.permitted(tool.name)]
        if self.allowed - {tool.name for tool in tools}:
            raise ValueError(f'{self.capability} configured tools are missing from deployed MCP schema')
        if not filtered:
            raise ValueError(f'{self.capability} exposes no permitted tools')
        return filtered

    async def call_tool(self, tool_name, arguments=None, meta=None):
        if not self.permitted(tool_name):
            raise PermissionError(f'{self.capability} cannot call {tool_name}')
        with mlflow.start_span(name=f'{self.capability}.retrieve', span_type='RETRIEVER') as span:
            span.set_inputs({'tool': tool_name, 'arguments': arguments})
            result = await super().call_tool(tool_name, arguments, meta)
            if not result.isError:
                payload = result.structuredContent or [p.model_dump() for p in result.content]
                span.set_outputs([{'page_content': json.dumps(payload), 'metadata': {'capability': self.capability}}])
        self.evidence.record(self.capability, tool_name, result)
        return result


def enforce_policy(answer, evidence):
    """Deliver only verifiable source excerpts for company-policy answers.

    A source citation alone is insufficient: policy quotes must actually occur
    in governed Confluence tool output. Relevance/entailment remains evaluated
    by MLflow judges; no model-authored policy prose is presented as authority.
    """
    if not answer.is_policy:
        return answer.answer
    valid = evidence.source_ids('confluence')
    documents = [json.dumps(call['result'], ensure_ascii=False) for call in evidence.calls if call['capability'] == 'confluence']
    quotes = answer.policy_quotes
    # JSON encoding preserves quotation/newline escapes for reliable substring checks.
    supported = bool(quotes) and all(len(q.strip()) >= 20 and any(json.dumps(q, ensure_ascii=False)[1:-1] in document for document in documents) for q in quotes)
    if not answer.citations or not set(answer.citations).issubset(valid) or not supported:
        return 'I cannot establish that policy from governed Confluence sources. Please consult the policy owner.'
    return 'Governed Confluence policy excerpts:\n' + '\n'.join('> ' + quote for quote in quotes)
