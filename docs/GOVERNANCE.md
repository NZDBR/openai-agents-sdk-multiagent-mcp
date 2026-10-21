# Durable approval identity update

The scheduled execution Workflow now owns privileged mutation. The interactive App persists approval/outbox only; its deployed writer UC binding and demo write token have been removed. Revoke previous manual/inherited writer grants from the App SP. The worker reads dedicated M2M credentials from its secret scope; dispatcher Jobs identity and worker Lakebase identity have separate grants. No employee token is reused for writes. See [current execution, migration and grant requirements](DURABLE_APPROVALS.md).

The historical identity configuration below describes the earlier request-bound path; statements about decide_task directly invoking the writer, App SP writer grants, or needs_reconciliation are superseded by the linked durability instructions. Generic tool error/Gateway ASK outcomes now fail closed into FAILED; transient transport failures use durable bounded recovery with the same business key.

# Enterprise identity and least-privilege MCP authorization

The runtime retains the pinned official Databricks Agent Server and OpenAI Agents SDK scaffold. Identity selection is explicit in `agent_server/identity.py` and `agent_server/connections.py`. Resource names, OAuth scope values and policy IDs are deployment inputs, never evidence that access exists.

## Interactive reads: verified employee / OBO

The App platform supplies `x-forwarded-access-token`. `user_workspace_client()` passes that token to the SDK using the pinned template convention (`auth_type='pat'` is bearer-token pass-through, not a claim that the OAuth token is a PAT). `employee()` verifies it through `current_user.me()`. Each `user_mcp_client()` receives this same employee client for Genie, StoreTime, OpsTask lookup and Confluence. No read factory constructs an app writer or reads write credentials. An absent token in a deployed App fails closed; no service-principal fallback is permitted.

`USER_AUTHORIZATION_MODE=obo` is the deployed default. Explicit `local_profile` plus `ALLOW_LOCAL_PROFILE_IDENTITY=true` permits CLI development outside an App. This profile is not OBO evidence. Noninteractive Workflow evaluation explicitly uses its configured job identity with this profile mode; it does not impersonate a human employee. Never enable that mode as a substitute for App user authorization.

The proxy/Agent Server must be reachable only through trusted platform ingress so clients cannot supply forged forwarded headers. Preserve the official UI server's forwarding behavior. Verifying a supplied token establishes its identity; trusting arbitrary browser-supplied identity strings does not. `custom_inputs` cannot choose identities, credentials, service URLs or approval owners.

## Privileged writes: trusted backend identity

`decide_task()` verifies the explicit boolean decision and atomically claims the employee/session-bound persisted proposal **before** calling `app_write_mcp_client()`. It receives no employee SDK client to reuse. Rejection, wrong-owner requests and replay never construct a writer. The model can save a proposal, but receives neither a write tool nor a write credential. The browser posts only approval ID and decision, not reviewed-payload replacements or backend authentication.

The writer uses one of two explicit backend identities:

- `OPSTASK_WRITE_AUTH_MODE=app`: require an actual App deployment and use platform-injected `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET`.
- `OPSTASK_WRITE_AUTH_MODE=m2m`: use separately secret-bound `OPSTASK_WRITE_CLIENT_ID` / `OPSTASK_WRITE_CLIENT_SECRET` for a dedicated backend service principal.

Both construct `WorkspaceClient(auth_type='oauth-m2m', ...)`, with configured `OPSTASK_WRITE_OAUTH_SCOPES`. They never inspect forwarded employee tokens or fall back to a PAT/profile. Credentials remain backend-only; do not add them to frontend configuration, model instructions, tool schemas, traces or responses. Model-facing read-client construction never receives the writer factory.

`OPSTASK_READ_CONNECTION` (legacy read alias: `OPSTASK_CONNECTION`) and `OPSTASK_WRITE_CONNECTION` are distinct UC connections. `OPSTASK_READ_MCP_URL` (legacy alias: `OPSTASK_MCP_URL`) and `OPSTASK_WRITE_MCP_URL` optionally override their respective workspace-governed routes. Production writer configuration fails if missing, cross-origin or equal to the read service. There is no write-to-read fallback. Demo mode is explicitly separate and may share one synthetic server with role-separated credentials.

The default DAB/manifest describes **app-identity** writes. For dedicated M2M deployment, use the reviewed secret-resource fragment in `config/m2m-write-bindings.example.yaml` as a configuration example (not automatically included), bind the backend secret only to the trusted server using Apps secret resources, grant invocation rights to that dedicated principal, and tailor the deployment resource bindings to avoid granting the App principal redundant write access. Merely selecting `m2m` does not change existing UC grants. The app resource definitions do not automatically grant a different backend principal permission.

## Who may call which service

| Identity | Intended MCP grants | Must not receive |
| --- | --- | --- |
| Employee / read role | Native Genie Space access; read-only StoreTime, OpsTask-read and Confluence invocation; underlying store/document permissions | OpsTask-write connection/service invocation or its credentials |
| App SP acting as writer | Minimum invocation grant on OpsTask-write; other App runtime resources only as operationally required | MCP CREATE/MANAGE/ownership or unrelated data access |
| Dedicated backend M2M SP | Minimum invocation grant on OpsTask-write | Read-service/admin grants unless separately justified |
| Deployment administrator | Separately authorized provisioning/policy operations | Runtime use of administrator credentials |

For the pinned external UC connection route, the resource privilege is `USE_CONNECTION` (`USE CONNECTION` in SQL grants). Native Genie uses `CAN_RUN` on its configured space plus underlying governed data access. If using a supported Unity Gateway MCP-service securable instead, grant the platform's service invocation privilege (for example EXECUTE where applicable) only to the corresponding identity. Do not invent a grant syntax or service securable unsupported by your workspace.

The DAB and manifest encode separate OpsTask read/write bindings using the pinned connection resource shapes and no MCP administration grants. The operator-reviewed `config/mcp-grants.sql.example` encodes the minimal connection-grant plan; it is not executed by the app. Audit existing and inherited group grants, since omitting a grant in this file is not an explicit deny. Employee group grants and upstream service permissions must be provisioned separately by an authorized administrator. Where an OBO route requires both App resource permission and employee permission, grant the minimum needed at both layers; the actual request still uses the employee token. A connection registration must preserve end-user ACLs where required; an upstream connector using a generic shared credential is not proof of employee-specific authorization.

## OAuth scopes and authorization checks

Enable Databricks Apps **user authorization** and configure/consent the supported scopes needed for: verifying user identity, native Genie MCP, invoking each read UC connection/service, and upstream access required by those reads. Add model/SQL scopes only if those calls actually execute as the employee. Never include write-service access in the employee grant set. Scope strings and permission names vary with the selected supported route/platform release: obtain their exact values from the workspace's Apps authorization UI and endpoint documentation. The forwarded token cannot be elevated by an environment variable.

Supply `OPSTASK_WRITE_OAUTH_SCOPES` as the comma-separated supported scopes for the chosen backend MCP route. The code passes this list to the SDK; it does not silently default to broad `all-apis`. OAuth scope is not a substitute for UC/service permissions. No new unverified Apps `user_api_scopes` or Gateway schema is added to the pinned manifest.

Public documentation requests in this task were blocked by the network proxy. APIs used for credential construction were checked against the installed locked SDK and the pinned template helper. Exact live scope identifiers, Gateway policy attachment and ACL behavior remain workspace validation requirements, not local claims.

## Human approval modes

`OPSTASK_APPROVAL_MODE` selects operator intent:

**Mode A — `application`:** employee approval → trusted handler → backend identity → OpsTask write MCP.

**Mode B — `application_and_gateway_ask`:** Mode A plus a separately attached Unity Gateway MCP service policy returning `ASK` for sensitive input calls. Set `OPSTASK_GATEWAY_POLICY_ID` to the operator-selected policy identifier. This is configuration metadata, not an attachment request or proof of enforcement. Attach and verify the policy using the supported platform interface; the feature and approval protocol may depend on preview availability.

UC grants answer **who may call the service**. The application approval record answers **whether this specific mutation was approved**. Optional Gateway `ASK` adds per-request approval of MCP input calls. No approval table is duplicated inside the MCP server, and no custom/fabricated policy API or automatic `ASK` acceptance is implemented. If the locked client surfaces a challenge/error or no confirmed task ID, the application fails closed into `needs_reconciliation`, without retrying the mutation. Verify the platform's complete challenge/resume interaction before enabling Mode B; local configuration tests do not certify that interaction.

The reviewed payload is immutable; the approval ID is sent as an idempotency key. A confirmed replay returns the recorded task ID. Unknown outcomes require reconciliation; do not create a new request ID to work around them. Restrict task store/assignee permissions at the writer/upstream service, since the backend acts with elevated authority.

## Local simulation and validation

The reconstructed synthetic Apps retain separate read and write tokens. Read tokens cannot discover or invoke `create_task`; the model specialist also independently rejects mutation dispatch. Only the application approval path obtains the synthetic writer token. A holder of that write token can call the demo server directly: it is a simulation of backend service access, not a signed approval artifact. Preserve token secrecy and HTTPS/host allowlists for deployed demos.

Tests verify user-client routing, explicit backend OAuth arguments, distinct routes, no write factory on read paths, ownership, rejection, single approved invocation, replay, model-visible boundaries and optional policy configuration. They do not prove live OAuth issuance, employee UC denial, upstream ACLs, Gateway `ASK`, deployment or Workspace connectivity.

## Other runtime resources

Lakebase sessions and approvals remain app infrastructure, with employee-scoped records and consented preferences; they are not replaced with demo task SQLite. Use deliberately selected database/schema grants and separate migration/bootstrap permissions. MLflow trace data contains employee context; restrict experiment/UC trace access and retention. The background Workflow uses its explicitly configured job principal and requires its own model/evaluation permissions. None of these resources is provisioned or live-validated by local tests.
