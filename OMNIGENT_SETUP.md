# Omnigent / Codex setup handoff

No authoritative public Omnigent project schema was found in the pinned official Databricks `app-templates` scaffold. A public repository search was blocked by this environment's network proxy, so no broader documentation claim is made. **There is intentionally no invented `omnigent.yaml` or claim of validated harness integration.**

Add your team's supported project configuration under `omnigent/` once the platform owner provides its schema/version and deployment contract. Review that addition before treating it as executable harness configuration.

## Intended integration points

| Harness operation | Repository entry point |
| --- | --- |
| Install/synchronize | `uv sync --locked`; `npm ci --prefix e2e-chatbot-app-next` |
| Test | `uv run pytest -q` |
| Build UI/package | `npm run build --prefix e2e-chatbot-app-next`; `uv build --wheel` |
| Run/debug agent | `uv run start-server` (MLflow Responses API / LongRunningAgentServer) |
| Run complete app | `uv run start-app` (official chat UI and agent backend) |
| Evaluate | `uv run agent-evaluate --judge-model databricks:/<judge-model>` |
| Deploy/redeploy | Databricks CLI `bundle validate`, `bundle deploy`, `bundle run store_operations`, all with `-t <dev-or-prod> --profile <profile>` |
| Inspect traces | Configured MLflow experiment and UC trace tables |
| Background execution | DAB `store_operations_background` Databricks Workflow |

Required team bindings are workspace host/profile, app name, MCP UC connections and audited tools, Genie space, Lakebase endpoint/SQL namespaces, model/judge endpoints, MLflow experiment/trace schema/warehouse, and Workflow resource IDs. Supply credentials through approved secret/profile bindings; never embed values in the harness project file or Codex prompts.

The standard debugger config in `.vscode/launch.json` is a VS Code configuration, **not an Omnigent schema**. `AGENTS.md` guides Codex without adding a separate execution engine. Any team-specific meta-harness must preserve the explicit human approval boundary; it must not auto-approve tool mutations during debug or redeploy.
