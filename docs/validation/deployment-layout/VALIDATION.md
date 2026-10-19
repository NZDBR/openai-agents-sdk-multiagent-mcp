# Deployment-layout validation

Recorded 2026-10-19T19:22:12.903424-04:00 on `refactor/deployment-layout`, based on `a2a9ed1b4889bfd69d273aee2efdd3bcf2ccf360`. This is a deployment/package/configuration refactor, not application logic changes. The source branch is unchanged.

## Verified locally

| Check | Result |
| --- | --- |
| Python suite | **79 passed, 2 live tests skipped**, 42 upstream deprecation warnings |
| Checkout MCP/application scenarios | Passed: three HTTP services, initialization, runtime contract equality, read/write boundaries, training, approval/rejection/replay, policy provenance/grounding |
| Approval task counts | **1 → 1 → 2 → 2**, no duplicate on replay |
| Staged MCP artifacts | All three separate processes started from their standalone staged environments; health/readiness, discovery, schemas, read calls and mutation denial passed |
| Production agent artifact | Installed independently with locked production groups; agent identity module imported from staged source, synthetic server modules absent |
| Frontend | npm clean install + build passed in the checkout AND the staged agent artifact; optional frontend PostgreSQL migration skipped without DB settings |
| Wheels | Separate agent/demo wheels built; tests assert no demo servers/corpus in the core wheel and no agent runtime in the demo wheel |
| Artifact boundaries | Tests/docs/harness/editor/env/dependency directories excluded; frontend DB support and migration runner retained |
| Dependency versions | Derived standalone locks contain only package versions from canonical root lock; core requirements.txt generated from it |
| Deployment configuration | DEV/PROD/DEMO passed pinned official Databricks CLI JSON schema and local path/secret/identity-binding checks |
| Schema negative test | Inline DAB `valueFrom` is rejected; `value_from` is validated |

Agent orchestration, employee/OBO identity, app/M2M writes, explicit approval, Lakebase memory, tracing, runtime launchers, frontend runtime/workspace code and all MCP business-service source were compared against the branch base and are unchanged. Only deployment declarations, packaging, development validation utilities, tests and documentation changed.

## Files and deployment behavior

One root bundle now defines the main App/Workflow, plus three separate MCP resources on the demo target. Historical standalone UI YAML is archived unchanged in `docs/template-reference/chat-ui/`. Duplicated nested MCP YAML is removed. Root manifest remains. Resource IDs/bundle name for the main App/Workflow are preserved; adoption of Apps from a former separate MCP bundle is not performed.

The demo services are a separate development workspace package and wheel. Production App artifacts contain no synthetic business MCP code/data. Demo Apps share the small demo package/corpus but run independently with distinct credentials. Frontend DB code and icon assets are retained. Startup still performs npm install/build and guarded DB migration; no prebuilt-only launcher was introduced.

The redundant requirements.lock was removed. Root requirements.txt is now a generated pinned runtime compatibility export, not another dependency authority. Omnigent, tests, CI, evidence and developer configuration remain in Git, outside App artifacts.

## Evidence

[Python](python-suite.txt) · [checkout UI](frontend-build.txt) · [staged UI](staged-frontend-build.txt) · [wheel build](wheel-build.txt) · [application scenarios](demo-e2e-evidence.json) · [staged MCP protocol](staged-mcp-evidence.json) · configuration: [dev](config-dev.json), [prod](config-prod.json), [demo](config-demo.json).

The application scenario harness uses real SDK orchestration, Responses/approval handlers and local HTTP MCP apps with explicitly test-only model, Genie, identity and memory/approval-store fixtures. The standalone artifact protocol check uses actual installed staged-service Python environments. No credentials were written to evidence.

## Not live-validated

No Databricks CLI executable was installed, so `databricks bundle validate` was not executed. Schema validation used the unmodified official schema at CLI commit `9a0157147e163c28f618ec2667c062233a030b0a`; see deployment/schema/PROVENANCE.md. A public API metadata request was blocked by the proxy; the pinned raw schema was retrieved successfully. No workspace/profile was requested or used, no App was deployed, and no real Genie/OBO/M2M/UC/Gateway/Lakebase/MLflow/Workflow operation is certified by this run.

Before deployment, supply target bindings, stage fresh artifacts, run authenticated CLI validation, inspect the deployment plan and existing bundle ownership, and verify actual Apps build/sync behavior and permissions. Runtime execution against real workspace services remains outside these credential-free checks. Full browser end-to-end and model quality are also not certified.

## Reproduce

See [deployment/README.md](../../../deployment/README.md) for staging, validation, and deployment commands. The schema checker and artifact tests are in CI; they do not silently substitute for workspace validation. Earlier reconstruction and identity evidence are preserved unchanged.
