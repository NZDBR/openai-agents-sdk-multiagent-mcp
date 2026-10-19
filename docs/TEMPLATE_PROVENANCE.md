# Official scaffold provenance

Upstream: https://github.com/databricks/app-templates
Commit: `0e572976459aafa3d41047067382cb9a6c015d52`

This implementation is rebased architecturally on `agent-openai-agents-sdk`, `agent-openai-agents-sdk-multiagent` and `agent-openai-advanced` at that commit:

- `agent_server/start_server.py`: modified advanced runtime (LongRunningAgentServer, MLflow Responses registration, Lakebase startup).
- `agent_server/template_utils.py`, `history.py`: advanced-template helpers, retained unchanged.
- `scripts/start_app.py`, `app_diagnostics.py`, `grant_lakebase_permissions.py`, `discover_tools.py`, `quickstart.py`, `preflight.py`: official template scripts; start_app is modified to use the pinned vendored official UI with npm ci; the permissions helper adds the portable Lakebase endpoint alias.
- `pyproject.toml`, `manifest.yaml`, `databricks.yml`: adapted packaging and bundle scaffold.
- `agent_server/agent.py`: store-specific replacement of the official @invoke/@stream orchestration pattern using the same SDK/runtime contracts.

Upstream LICENSE and NOTICE are retained. Modified derived files carry notices. `LongRunningAgentServer` is the current official advanced-template class, not `DurableAgentServer`; this project does not claim an unavailable API by that name.

The official `e2e-chatbot-app-next` source/lockfile is vendored at the same commit. Only `client/src/components/chat.tsx` is extended and `store-task-review.tsx` is added for the human approval panel. Build outputs and dependencies are ignored.

The `mcp-apps/` business services are a functional reconstruction from the recorded requirements, not recovered original demo source. They use the pinned MCP Python SDK FastMCP Streamable HTTP/ASGI APIs, independently from the official Agent Server runtime. No missing upstream business implementation is claimed as copied.

## Deployment-only layout refactor

The standalone UI databricks.yml, app.yaml and manifest.yaml are archived unchanged in docs/template-reference/chat-ui/. Their runtime/build sources are unchanged. Active deployment is consolidated in the root bundle with included deployment/ resource definitions. Synthetic MCP packaging is a separate workspace project; the core package excludes its services/data. Pinned CLI schema provenance is in deployment/schema/PROVENANCE.md. These changes do not replace the official Agent Server, SDK session API or official UI behavior.
