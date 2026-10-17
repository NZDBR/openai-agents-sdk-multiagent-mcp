# Store Operations development

Use this existing checkout; do not create a Git worktree unless the user requests one. The runtime derives from pinned official Databricks templates; see docs/TEMPLATE_PROVENANCE.md. Do not reintroduce the deleted synthetic FastAPI runtime.

Run `uv sync --locked`, `uv run pytest -q`, and the official UI build (`npm ci --prefix e2e-chatbot-app-next`, `npm run build --prefix e2e-chatbot-app-next`). All synthetic adapters belong in tests/. Live tests are opt-in integration tests and skip without configuration.

Keep deployment-specific identities configurable. Do not require real workspace values to implement or locally test code. Preserve MCP capability isolation and the separate human command channel for mutation. No model, memory, tool output or harness may approve a task. Avoid automatic retries after uncertain writes.

Use the actual LongRunningAgentServer / AsyncDatabricksSession APIs from uv.lock. Local tests do not certify live deployment, Lakebase, Unity Catalog grants, external MCP schemas or MLflow export/judges. Do not invent Omnigent schemas; see OMNIGENT_SETUP.md.
