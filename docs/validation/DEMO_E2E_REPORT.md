# Reconstructed Store Operations demo — validation report

This is a **controlled functional reconstruction**, not recovery or byte-for-byte reproduction of the lost uncommitted workspace. Built from committed baseline `2c25a660efc09197cc71f322ce393834462179ae` and the documented tool contracts. The historical lost 74-test run is not claimed as reproduced. Fresh evidence was recorded at `2026-10-17T06:15:57.302749+00:00`.

| Check | Fresh result |
| --- | --- |
| Three MCP processes start | Passed; separate StoreTime, OpsTask and Confluence HTTP processes |
| Health/readiness | Six successful HTTP 200 responses |
| MCP initialization/list_tools | Passed for each service; actual initialize results in JSON |
| Runtime schemas vs contracts.json | Exact complete tool-object equality; read views and OpsTask write view |
| All read tools | Nine real HTTP calls, structured results schema-validated |
| Tool boundaries | StoreTime has no writes; Confluence retrieves only; OpsTask read cannot discover/invoke create_task; agent-side dispatch also denies writes |
| Training scenario | Actual SDK supervisor → test-only Genie fixture → actual StoreTime HTTP → supervisor evidence response |
| Proposal / approval / replay | Task counts **1 → 1 → 2 → 2**; same approval ID returns stable task ID; rejection writes nothing |
| Server idempotency | Same key/payload replays; conflicting payload rejected; concurrent/restart behavior tested |
| Policy scenario | Actual HTTP search/get; source/document ID, title, URL, section and exact stored text verified; final response cites source ID and URL |
| Python suite | **51 passed, 2 skipped**, exit 0; 42 upstream deprecation warnings |
| Frontend | `npm ci` and client/server build exit 0; optional PostgreSQL history migration skipped without DB config |
| Wheel | Build exit 0; includes services and synthetic corpus |

## Evidence and limits

[Raw protocol/scenario evidence](reconstruction/demo-e2e-evidence.json), [Python results](reconstruction/python-suite.txt), [frontend output](reconstruction/frontend-build.txt), [harness output](reconstruction/harness-output.txt), [wheel output](reconstruction/wheel-build.txt).

Real local operations: service processes, Streamable HTTP `/mcp`, health/readiness, SDK orchestration, Responses handlers, human-decision handler, synthetic task database and policy retrieval/grounding guard. Fixture-only components: scripted model outputs, Genie transport/metrics, verified employee identity, session/approval store (`FakeStore`, not Lakebase). This is not a browser end-to-end test or model-quality evaluation. MLflow export is disabled for the standalone harness.

Synthetic StoreTime records show 6 scheduled/protected hours, 3 completed, 2 converted, a 3-hour completion gap, blocks B-1/B-2 and recorded peak/absence contributors. Responses label this synthetic and do not claim every incomplete hour has a proven root cause. Confluence returns the stored `DEMO-TRAINING-1` document and `https://demo.invalid/policies/training#protected-blocks` as synthetic provenance.

The OpsTask server trusts its separate write credential; a direct credential-holder probe succeeds without consulting an application approval table. The application gate and read/model isolation are verified locally. Credentials alone simulate read/backend roles and do not demonstrate live OBO or service-principal authorization. The enterprise identity refactor has deliberately not been applied in this reconstruction checkpoint.

No live Databricks resource was required, provisioned or verified. Still unverified: real Genie/model calls, employee OBO and service identities, Lakebase persistence/locks/OAuth, UC/Gateway grants and policies, remote App deployments, MLflow workspace trace export/model-judge evaluations, actual Workflow execution, and browser-to-deployed-server operation. Both opt-in integration tests skipped without live configuration/opt-in. YAML was parsed/tested; no `databricks bundle validate` or deployment occurred.

## Reproduce from the repository root

```bash
export UV_CACHE_DIR=/tmp/store-operations-uv-cache
export NPM_CONFIG_CACHE=/tmp/store-operations-npm-cache
uv sync --locked
uv run python -m scripts.validate_demo_stack
uv run python -m tests.demo_e2e_validation
uv run pytest -q
npm ci --prefix e2e-chatbot-app-next
npm run build --prefix e2e-chatbot-app-next
uv build --wheel
```

The harness generates fresh JSON evidence; `--output-dir` selects a new run directory to preserve previous evidence. It creates temporary random credentials, stops only its own subprocesses and deletes its isolated synthetic database. No service credentials are saved in evidence. See [MCP contracts](../../mcp-apps/CONTRACTS.md) and [startup/deployment guidance](../../mcp-apps/README.md).

## Reconstructed file tree

```text
mcp-apps/
  CONTRACTS.md, contracts.json, README.md, databricks.yml
  shared/     __init__.py, contracts.py, demo_data.py, transport.py
  storetime/  __init__.py, server.py, service.py, app.yaml, .env.example
  opstask/    __init__.py, server.py, repository.py, app.yaml, .env.example
  confluence/ __init__.py, server.py, repository.py, app.yaml, .env.example
  data/       storetime.json, initial_tasks.json
    policies/ index.json, protected-training.md, followup-approval.md, store-context.md
  tests/      conftest.py, test_storetime.py, test_opstask.py, test_confluence.py,
              test_contracts.py, test_transport.py
agent_server/connections.py
scripts/validate_demo_stack.py
scripts/export_demo_contracts.py
tests/demo_e2e_validation.py
.env.demo.example
docs/validation/DEMO_E2E_REPORT.md
docs/validation/reconstruction/ (JSON and command evidence)
```

StoreTime: five windowed read tools. OpsTask: `list_followups`, `get_task`, separately scoped `create_task`. Confluence: `search_company_context`, `get_policy_document`. Exact signatures and error/idempotency semantics are in CONTRACTS.md and runtime-checked contracts.json.

## Subsequent enterprise identity refactor

This document preserves the reconstruction checkpoint. See the [separate post-refactor report](identity/IDENTITY_VALIDATION.md) for current identity-boundary results and fresh evidence.
