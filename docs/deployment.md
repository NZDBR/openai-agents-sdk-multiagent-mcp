# Deployment validation

1. Select the official Databricks Apps OpenAI Agents SDK template and confirm compatibility with `app.yaml` and Python dependencies. Use this existing checkout; no worktree is needed.
2. Provision Genie Space, StoreTime/OpsTask/Confluence MCP services, Lakebase and the background Workflow in the target workspace. Record real endpoint/tool schemas. Bind least-privilege credentials and Unity Catalog permissions to the app resources.
3. Configure Databricks Apps user authorization and verify SCIM `/Me` access with the forwarded token. Verify that two employees cannot access each other's sessions or memories and that MCP resources enforce authorized stores. The backend verifies identity; data-source permissions still require workspace configuration.
4. Configure HTTPS MCP URLs, endpoint-specific credentials and explicit read-tool allowlists. Confirm that no write tool is available to any model specialist. Adapt the documented OpsTask write contract to the deployed schema and validate remote idempotency before enabling it.
5. Configure Lakebase with trusted TLS roots, secure authentication and appropriate connection/credential rotation. Exercise schema setup with the migration role, then use a least-privilege runtime role. Verify persistent memory, consent, deletion and retention. DSN authentication refresh/rotation must be supplied by the deployment environment.
6. Test task proposal, reject, approve, replay, timeout, crash recovery and cross-employee denial against a staging OpsTask instance. Reconcile `executing` and `needs_reconciliation` records by approval ID; do not blindly reset them to pending.
7. Bind the fixed Workflow job and scoped token. Verify repeated request IDs return the same logical run and inspect actual job output in Databricks. The API implements submission, not a job-monitoring dashboard.
8. Configure MLflow tracking authentication. Verify real traces, restricted access and a representative labeled evaluation dataset. The repository's local behavior evaluation is only a baseline.
9. Configure Agent Bricks and the correct Omnigen/Omnigent harness with the workspace-supported interface. No harness commands are assumed here. Deploy/redeploy through that supported interface or Databricks Apps, validate health, and perform a representative authenticated employee query.

None of these external deployment steps is certified by local unit tests. The local demo is suitable for evaluating interactions, not for handling sensitive employee data.
