# Reconstructed synthetic MCP applications

This layer is a controlled functional reconstruction from the documented architecture/contracts after the original uncommitted workspace was lost. It is not recovered source or an original Store Operations demo copy. See [contracts](CONTRACTS.md).

Install `uv sync --locked` from the repository root. For automated startup, health/readiness, MCP initialization, discovery, exact runtime schema comparison, all nine read calls and agent-client boundary checks:

```bash
uv run python -m scripts.validate_demo_stack
uv run python -m tests.demo_e2e_validation
```

For persistent interactive services, run these in separate terminals from the root with independently generated credentials in ignored env files:

```bash
uv run --env-file mcp-apps/storetime/.env demo-storetime
uv run --env-file mcp-apps/opstask/.env demo-opstask
uv run --env-file mcp-apps/confluence/.env demo-confluence
```

Copy the corresponding `.env.example` first. Ports: 8101/8102/8103. Each exposes `/mcp`, `/health`, `/ready`; health routes reveal no credentials. Send `X-Demo-MCP-Token` for MCP. Use the same service-specific read token in the agent's `DEMO_*_READ_TOKEN`; only its approved writer receives the separate `DEMO_OPSTASK_WRITE_TOKEN`. Never put these credentials in frontend configuration. `/ready` returns 503 on invalid fixture/storage.

StoreTime and Confluence read immutable synthetic JSON/Markdown. OpsTask uses demo-only SQLite at `.demo-data/tasks.db`; keep that file for local replay durability. It is not production Lakebase memory and is not durable across App redeployments or replicas. Future corporate adapters must live separately from these fixture repositories.

The OpsTask server trusts the write credential; it does not verify human approval records. The application performs explicit approval. The local credential boundary simulates identity roles; it does not prove OBO, OAuth, UC or Gateway authorization.

## Databricks Apps examples

`databricks.yml` declares three separate Apps with generic DEV/PROD targets. Supply all variables with `BUNDLE_VAR_*` or target bindings: workspace_host, secret_scope, each app_name/public_host/read_secret_key, and opstask_write_secret_key. Each app uses the root package and a distinct startup command. Bind secrets with supported Apps secret resources. Set public_host to the exact deployed App hostname for host-header protection. Deployment config is parsed/tested locally, not server-validated or deployed.

Genie is not implemented here. Full interactive chat also requires real Genie, model, authenticated employee identity, Lakebase and other App bindings; no synthetic agent runtime or production SQLite memory fallback is supplied.
