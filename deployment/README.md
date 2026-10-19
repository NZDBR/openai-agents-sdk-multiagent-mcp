# Deployment layout

`databricks.yml` is the single active bundle entry point. It includes `agent.resources.yml`, `workflow.resources.yml` and `demo.resources.yml`. The original bundle name and main App/Workflow resource keys are unchanged. Do not adopt existing resources from the former separate MCP bundle without reviewing their bundle ownership/state; this change does not perform adoption or deploy anything.

## Targets and identities

- `dev` / `prod`: Store Operations App plus evaluation Workflow. Use configured corporate MCP connections and native managed Genie. No synthetic MCP server or fixture is installed in the agent artifact.
- `demo`: adds independently deployable StoreTime, OpsTask and Confluence Apps. Each installs the same small demo package, starts only its selected service, and receives its own credentials. The main App uses explicit trusted demo URLs and secret-resource bindings. Genie, model, OBO and Lakebase still require real configuration; demo is not a credential-free production agent.

The default production binding remains employee/OBO reads and human-approved App/M2M writes to distinct OpsTask connections. This refactor changes no agent, approval, memory, MCP business-tool or frontend feature code. The frontend DB package remains: its history/messages/feedback/ACL functionality is separate from Agent Server memory.

## Build and validate locally

```bash
uv sync --locked
uv run pytest -q
uv run python -m scripts.validate_demo_stack
npm ci --prefix e2e-chatbot-app-next
npm run build --prefix e2e-chatbot-app-next
uv build --all-packages --wheel
uv run python -m scripts.stage_apps --target demo
uv run python -m scripts.validate_deployment --target dev
uv run python -m scripts.validate_deployment --target prod
uv run python -m scripts.validate_deployment --target demo
```

The validator checks the pinned official Databricks CLI JSON schema, included resource definitions, target App sets, paths, identity bindings and secret references. It does not execute the CLI, verify actual permissions or contact a workspace. See `schema/PROVENANCE.md`. The schema uses `value_from` for inline DAB App environment bindings; standalone `app.yaml` uses `valueFrom`. These formats must not be mixed.

For deployment select a target, supply its generic values via `BUNDLE_VAR_*`, profile and server-side resource/secret bindings, then run:

```bash
uv build --package store-operations-agent --wheel
uv run python -m scripts.stage_apps --target prod
uv run python -m scripts.validate_deployment --target prod
databricks bundle validate -t prod --profile <profile>
databricks bundle deploy -t prod --profile <profile>
databricks bundle run store_operations -t prod --profile <profile>
```

Use `dev` or `demo` consistently instead of `prod` for those targets. Stage **before** CLI validation/deploy. The Databricks CLI and workspace checks require the selected environment; no example value provisions or authenticates a real resource.

For `demo`, also configure `secret_scope`, per-service app_name/public_host/read_secret_key, `opstask_write_secret_key`, the explicit `demo_*_mcp_url` values and `demo_mcp_allowed_hosts`. Empty defaults keep these variables out of the non-demo required-input set; supply real values before deploying demo. App URLs/hostnames and matching tokens must be configured; resource existence alone does not wire the agent or grant access. Root app/model/Lakebase/Genie/Workflow bindings remain required. Do not use demo SQLite for production persistence.

## Artifacts

`.deploy/` is generated and ignored by Git. Each subdirectory is a standalone source-build project with a derived lock and generated pip compatibility export. The stager rejects dependency version changes relative to the canonical root `uv.lock`. It resolves offline from the existing lock/cache; run `uv sync --locked` first. Only directories marked as owned staging artifacts are replaced.

```text
.deploy/
  agent/
    pyproject.toml, uv.lock, requirements.txt, README.md, LICENSE, NOTICE
    agent_server/
    scripts/ (__init__, start_app, app_diagnostics only)
    evaluations/, jobs/ (core wheel/evaluation entry points)
    e2e-chatbot-app-next/
      package.json, package-lock.json, tsconfig.json
      client/, server/, packages/ (including db)
      scripts/migrate.ts
  storetime/   standalone demo project + common demo MCP package/corpus
  opstask/     standalone demo project + common demo MCP package/corpus
  confluence/  standalone demo project + common demo MCP package/corpus
```

No tests, CI, documentation/evidence directories, editor/harness settings, local env files, source-checkout dependency directories or validation utilities are copied. The production agent has no `mcp-apps/` tree. Demo artifacts have no agent/UI/evaluation code. Shared demo packaging intentionally contains all three services and synthetic corpus; separate App processes and credentials determine exposed capabilities.

`uv sync --locked --no-default-groups` works inside each artifact. For additional artifact-level checks, install dependencies in each staged MCP App, then run `uv run python -m scripts.validate_demo_stack --artifact-root .deploy` from the checkout. This uses three actual staged-service processes. The agent's frontend can also be built directly under `.deploy/agent/e2e-chatbot-app-next`.

The existing startup launcher is unchanged: frontend `npm ci` and build still run at startup, including the guarded PostgreSQL migration. We do not replace that behavior with prebuilt assets. Runtime dev dependencies needed by that frontend build cannot yet be pruned. Unused icon pruning is deferred until a separate import/asset audit; barrel exports currently reference icon modules.

## Dependency and template policy

- Root `pyproject.toml` declares agent/evaluation dependencies; `mcp-apps/pyproject.toml` declares demo dependencies. Root `uv.lock` pins the workspace.
- Default development installation includes the demo workspace package. Production installations omit development groups.
- `requirements.txt` is a generated, pinned **core runtime** compatibility export. Regenerate with the command in its header; never edit it as a second source of dependency declarations. The redundant `requirements.lock` export is retired. Per-artifact requirements are generated from its verified standalone lock.
- Root `manifest.yaml` remains template metadata. Obsolete standalone UI deployment examples are preserved byte-for-byte under `docs/template-reference/chat-ui/`; their paths/variables are archival, not runnable current configuration. Duplicate MCP bundle/app YAML files are replaced by the root demo target.
- License/NOTICE, template runtime helpers, OBO forwarding, SDK contracts and frontend DB migrations are preserved. Omnigent/Codex files stay in Git, outside deployed artifacts.
