# Verification levels

## Verified locally

- `uv sync --locked`: installed the locked Python environment.
- `uv run pytest -q`: 35 tests passed; 2 live integration tests skipped because live configuration/opt-in was absent. One upstream SQLAlchemy deprecation warning was emitted.
- Real OpenAI Agents SDK `Runner.run` execution with test-only scripted models: supervisor → scoped MCP specialist → test transport, and task proposal without mutation.
- Direct and model-visible tool boundaries: Genie task creation denied; StoreTime schedule changes denied; OpsTask mutation unavailable without a separate human action; policy delivered only with matching Confluence source identifiers and exact retrieved excerpts.
- Task rejection, ownership, replay handling, and ambiguous-write reconciliation; employee identity verification contract.
- Native Lakebase session constructor/scoping and long-term SQL adapter contracts with test dependencies. These do not establish a database connection.
- Actual `LongRunningAgentServer` construction and startup-session wiring with credential setup stubbed; MLflow Responses response/stream shapes, including text delta events for the official UI.
- Actual local MLflow trace creation and readback using an isolated local tracking database. This does not verify Databricks export.
- Evaluation dataset/scorer loading and negative/positive safety scoring. Model-based judges were instantiated, not executed against a real model.
- Databricks Jobs SDK submission/status contracts using a fake client, confirmation and identity-scoped idempotency.
- Official vendored chat UI: `npm ci` and `npm run build` completed. Its optional frontend-history migration skipped because no PG database was configured. Agent conversation memory has a separate mandatory Lakebase backend.
- `uv build --wheel` completed; the wheel contains the runtime, evaluation dataset and scorers.
- Dependency compatibility check and Python compilation completed.

## Configuration/syntax checked only

- DEV/PROD DAB YAML parsed and resource permissions/variable substitutions asserted in tests.
- App manifest follows the pinned official template resource shapes.
- Workflow notebook, SQL migration and configuration/debug files are present and syntax checked.
- No `databricks bundle validate` or deployment was performed: a CLI/profile/target workspace was not supplied. YAML parsing is not equivalent to Databricks CLI/server validation.

## Requires live workspace validation

- Actual Genie One analytics and UC connection MCP schema discovery/authorization for StoreTime, OpsTask and Confluence.
- Workspace OBO token scopes, store/region row permissions, company document ACLs, and Unity Gateway policies.
- Lakebase OAuth rotation, persistent session replay, long-term memory SQL grants, runtime task persistence and advisory-lock concurrency on the actual database.
- OpsTask provider argument/result mapping, store/assignee authorization, remote idempotency and staging mutation results.
- UC trace-table provisioning/readback and model-based MLflow evaluation quality scores.
- Actual Workflow execution/output, target cluster permissions and app principal job grants.
- DEV/PROD deployment, remote health/readiness, and team-specific Omnigent/Codex harness configuration.

Run live checks only against an authorized environment:

```bash
RUN_DATABRICKS_INTEGRATION=1 uv run pytest -m integration -q
```

Live tests additionally require their named environment variables to contain real values. The two included checks discover native Genie tools and round-trip an isolated Lakebase session (then delete that test session). They never create external OpsTask tasks. Broader staging approval and deployment acceptance should be performed with your team's configured services before release.

The application-owned diff passes whitespace checks. The unmodified vendored official UI retains upstream whitespace in a few setup scripts; a whole-diff `git diff --check` reports those inherited lines. They were left intact to preserve the pinned upstream source.
