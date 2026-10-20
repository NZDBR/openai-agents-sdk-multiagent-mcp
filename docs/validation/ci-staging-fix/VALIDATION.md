# CI artifact staging fix — 2026-10-20

## Cause and correction

Run 39341167634 failed at artifact staging, before application tests. Reproducing the former stager with an empty `UV_CACHE_DIR` failed during `uv lock --offline`: the universal resolver required uncached `databricks-agents` registry metadata for a Windows/Python >=3.14 fork. A successful root `uv sync --locked` installs current-platform dependencies; it does not populate all metadata needed for a new universal resolution. Root manifests and lock existed; rewriting workspace metadata triggered unnecessary resolution. Earlier warm-cache validation missed this dependency.

The stager now preserves both workspace manifest locations, copies the canonical `uv.lock` byte-for-byte, and runs only a frozen offline export for the selected package. No fresh lockfile is generated. Production carries the demo member manifest as metadata only, without demo code/data. Demo artifacts explicitly select their member package. App commands consume the lock frozen; the existing agent launcher receives the same policy through uv environment variables. No agent, identity, approval or business-tool source changed.

Regression tests stage agent and MCP artifacts with an empty cache and network disabled, forbid `uv lock`, assert canonical lock identity, and check useful error reporting without destroying the previous artifact. Separate tests install both selected runtime packages from staged source and verify imports originate inside the artifact and the other runtime is absent.

## Results

- `uv run python -m scripts.stage_apps --target demo`: passed, four artifacts.
- `uv run python -m scripts.validate_deployment --target dev`: passed.
- Same command for `prod` and `demo`: passed.
- `uv run pytest -q`: **84 passed, 2 skipped** (live integration tests unconfigured).
- `uv build --all-packages --wheel`: passed, agent and demo MCP wheels.
- Local three-process MCP validation (`uv run python -m scripts.validate_demo_stack`): passed (health/readiness, discovery/contracts, identity and approval boundaries).
- Focused deployment packaging suite: **11 passed**.

Raw command outputs are adjacent to this report. Commands used `UV_CACHE_DIR=/tmp/store-operations-uv-cache`; cold-cache regression cases override it with an empty temporary directory. Configuration validation uses the pinned Databricks schema and local bindings, without authenticated workspace deployment. No live Databricks integration was claimed or attempted.

CI uses Node.js 24-compatible checkout@v6, setup-uv@v7 and setup-node@v6, and ubuntu-24.04 runners. Frontend application Node remains version 22. GitHub-hosted execution is distinct from these local results; its run URL/status will be reported after push. No local frontend source changed.
