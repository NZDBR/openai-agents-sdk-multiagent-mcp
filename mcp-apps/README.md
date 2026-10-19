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

## Databricks Apps deployments

The single root bundle defines the `demo` target and three separate App resources in `deployment/demo.resources.yml`. Follow [root deployment instructions](../deployment/README.md). The old nested bundle and duplicate per-service app.yaml files have been consolidated; startup commands and service implementations are unchanged. Use `uv run python -m scripts.stage_apps --target demo` before bundle validation. All workspace IDs, App names, hosts, secret keys and endpoint URLs remain supplied through configuration.

The demo workspace package is installed by the root default development group; `uv sync --locked` still enables the three `demo-*` commands. The production agent wheel excludes these servers and their synthetic data. `uv build --all-packages --wheel` builds separate agent and demo wheels. Demo App persistence remains illustrative SQLite; no production durability is claimed.
