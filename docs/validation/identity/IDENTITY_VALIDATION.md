# Enterprise identity refactor validation

Recorded at `2026-10-17T06:22:10.993582+00:00`. Applied only after reconstruction commit **`8e1e729915dd7c4602dfd1742425b09459ea0796`** was pushed and its remote hash verified. This refactor preserves the reconstructed MCP service code, contracts and reconstruction evidence unchanged.

## Results

- **73 Python tests passed, 2 live integration tests skipped**, exit 0. The reconstruction checkpoint had 51 passing tests; 22 identity-boundary/configuration cases were added.
- The full three-process MCP/application harness passed again. Health/readiness, initialization, runtime schema equality, every read tool, read/write denial, training diagnosis, policy grounding and explicit approval/replay were retained.
- Task counts remained **1 → 1 → 2 → 2** for before/proposal/approval/replay. Rejection creates no task; only one application writer completion occurs. A same-ID direct server replay returns the same task ID.
- Wheel build passed with updated runtime code. The frontend install/client/server build passed at the reconstruction checkpoint and frontend source has not changed since; it was not rerun for this backend/configuration refactor.
- DAB/manifest/secrets examples and the minimal grant template were checked locally. No workspace deployment, `databricks bundle validate`, OAuth exchange, UC grant or Gateway policy operation was performed.

## Identity checks added

| Boundary | Locally verified |
| --- | --- |
| Employee token | Exactly the forwarded bearer is supplied to the SDK; employee identity verified with `/Me` contract |
| Missing employee authentication | No app/SP fallback; missing user client cannot trigger the MCP SDK's default identity |
| Local profile | Requires explicit mode and opt-in; forbidden as fallback inside an App |
| Backend app / M2M | Explicit OAuth-M2M SDK construction from trusted server configuration; ignores employee header and ambient PAT |
| Missing backend configuration | Fails closed; no shared read client accepted by writer factory |
| Read specialists | All four receive the user-scoped client; no read factory constructs app identity or includes create_task |
| Privileged factory ownership | Only the application approval handler invokes it in production source |
| Approval | Claim/ownership check precedes construction; rejection and replay never create another writer |
| Service bindings | Production read/write routes must differ, including encoded-path equivalence; cross-origin/missing write route denied |
| Demo roles | Separate read/write credentials retained; actual HTTP read credential cannot discover/invoke mutation |
| Browser boundary | Client source contains no write-secret configuration; secret example uses backend valueFrom resource binding |
| Gateway defense in depth | Mode B requires policy identifier; no attachment/enforcement is inferred; unconfirmed outcome stops with reconciliation and no retry |
| Least privilege | Separate DAB read/write bindings; template grants employees three read connections, backend only write connection, no MCP admin rights |

The credential-construction checks use mocked SDK constructors, not an actual employee or service principal. The Gateway challenge test uses a deliberately test-only unconfirmed outcome, not a claimed platform response schema. Local MCP tokens simulate enterprise roles. A direct write-token holder can call the synthetic service; application approval state is not duplicated in the server.

## Evidence and reproduction

[Protocol/scenario JSON](demo-e2e-evidence.json) · [Python output](python-suite.txt) · [harness output](harness-output.txt) · [wheel output](wheel-build.txt) · [preserved reconstruction/frontend evidence](../DEMO_E2E_REPORT.md).

```bash
export UV_CACHE_DIR=/tmp/store-operations-uv-cache
uv run pytest -q
uv run python -m tests.demo_e2e_validation --output-dir docs/validation/identity
uv build --wheel
```

These regenerate local evidence; they do not start a credential-free production agent. The harness uses actual MCP HTTP/SDK/application handlers but scripted model, test-only Genie, synthetic employee identity and FakeStore memory/approval fixtures. It does not verify Lakebase, model inference or the browser flow. MLflow trace export is disabled for the harness. The ordinary test suite separately tests local trace readback and fake Workflow contracts.

## Remaining live checks

Validate employee OBO tokens/scopes and read permissions, deny employee access to the separate write service (including inherited grants), verify actual App/M2M identity and its minimal write grants, test task store/assignee authorization, persistent Lakebase approvals/locks, remote idempotency, actual Genie/model responses, workspace MLflow traces/evaluations, Workflow execution, deployed Apps and the browser approval path. For Mode B, attach a supported Unity Gateway service policy and validate its ASK/challenge/resume behavior with the selected platform/client versions. Exact scope names and policy attachment remain operator/workspace requirements; public-doc retrieval was blocked by the proxy. No such operation is claimed completed.
