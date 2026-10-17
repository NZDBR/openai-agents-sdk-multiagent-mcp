# Unity Gateway / Unity Catalog permissions

This project uses the workspace-managed MCP surface. External services are registered as Unity Catalog connections and accessed through `/api/2.0/mcp/external/<connection>`. Genie uses the native space endpoint. If your workspace exposes these through a Unity Gateway deployment, configure its policies at that gateway; this repository does not assert an undocumented Gateway admin schema/API.

## Resource bindings

`databricks.yml` declares the app principal's required bindings:

| Resource | Permission |
| --- | --- |
| Genie One space | `CAN_RUN` |
| StoreTime UC connection | `USE_CONNECTION` |
| OpsTask UC connection | `USE_CONNECTION` |
| Confluence UC connection | `USE_CONNECTION` |
| Model serving endpoint | `CAN_QUERY` |
| MLflow experiment | `CAN_MANAGE` (reduce if your platform supports the needed trace operations with a smaller grant) |
| Lakebase branch/database | `CAN_CONNECT_AND_CREATE` per upstream bootstrap template |
| Fixed Workflow job | `CAN_MANAGE_RUN` |

The Workflow runs as the configurable `job_service_principal`. Grant that principal the same evaluation-required model/judge, Genie, UC connection, Lakebase and MLflow access; app resource bindings do not automatically grant a different job identity those permissions. The job cluster must allow that execution identity.

Resource grants are deploy-time configuration, not proof that the connected data permissions are correct. Requests authenticate with the forwarded employee token for MCP calls. Both the app principal and employees need the appropriate access for the configured OBO route. Verify token scopes and gateway behavior in your workspace.

## Data permissions

- Grant `USE CATALOG`, `USE SCHEMA` and `SELECT` only on the tables/views the Genie Space needs. Apply store/region row filters and sensitive-column masks in UC. Do not grant unrestricted SQL or table-write functions to the analytics capability.
- Restrict StoreTime credentials/service-side endpoints to schedule/training reads. Remove schedule mutations from the exposed server or enforce their denial at the gateway even if a broader API exists upstream.
- Split/audit OpsTask lookup versus mutation permissions. The application does not expose mutation tools to any model. The writer rechecks the employee via OBO, validates the live tool schema, uses an immutable reviewed payload and a durable idempotency key. The provider must enforce store/assignee authorization and remote idempotency.
- Confluence credentials must honor company document ACLs. Return actual source URLs/document IDs with excerpts. Retrieval from an inaccessible or nonexistent policy cannot be replaced by model-generated policy.
- Configure gateway tool allowlists, argument constraints, audit logs and credential handling using the supported workspace interface. The application's allowlist is defense in depth; a misleadingly named tool can still be mutating, so administrator review and upstream scopes are mandatory.

## Lakebase and traces

Use a migration/bootstrap principal for schema creation. The app runtime needs access to session tables, `memories`, `approvals` and `workflow_runs`, not unrelated employee tables. Native session initialization currently follows the pinned template's private `_ensure_tables()` startup API; the dependency lock and runtime tests protect that integration. Move DDL to deployment migrations when tightening runtime grants.

`STORE_OPS_SCHEMA` and `LAKEBASE_AGENT_MEMORY_SCHEMA` are configurable SQL namespaces. Long-term memory is employee-scoped and opt-in, with deletion. Set retention and deletion policies for session history, preferences, proposal audit records, runtime tasks and traces. A UC resource grant alone does not implement retention.

MLflow traces include employee inputs and retrieved context. Use a deliberately selected `<catalog>.<schema>` trace location, required warehouse permissions, and restricted experiment/table access. No trace-schema creation occurs implicitly during chat requests. The setup script only binds an operator-selected schema.
