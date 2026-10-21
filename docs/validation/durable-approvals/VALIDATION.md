# Durable approval gap analysis — 2026-10-21

Branch: feat/durable-approval-workflows, based on 32d6727. No source-branch commits changed.

## Implemented — local verification

All test names below are in `tests/test_durable_approvals.py` unless a different path is stated. SQL tests execute the real production schema, trigger, migration and persistence queries against an isolated local PostgreSQL server using separate connections. They are not mocked SQL parsers. Databricks Jobs and OAuth remain fake; external task effects use the synthetic demo OpsTask repository.

| Requirement | Responsible code | Exact proving tests |
|---|---|---|
| Separate approval/execution states; persisted restart state | ApprovalPersistence.propose/decide; resources/schema.sql | test_atomic_approval_outbox_restart_replay_and_ownership; test_persisted_states_survive_new_store_instances |
| Ownership and replay protection | ApprovalPersistence.decide, atomic decision/outbox CTE | test_atomic_approval_outbox_restart_replay_and_ownership; test_outbox_failure_rolls_back_approval_decision |
| Stable business key and provider conflict rejection | approval_worker.write_task; demo TaskRepository.create | test_write_succeeded_but_result_lost_replays_same_external_task; mcp-apps/tests/test_opstask.py::test_atomic_replay_conflict_and_restart |
| One execution owner, recoverable expiry and stale fencing | execution_claim/executable/execution_finish/recover | test_only_one_lease_owner_recovery_and_stale_fencing; test_expired_execution_lease_is_fenced_without_replacement |
| Bounded retries/backoff and sanitized errors | execution_finish/recover/dispatch_failed; approval_worker.classify | test_bounded_retry_backoff_and_sanitized_errors; test_permanent_error_no_retry; test_submission_retries_are_bounded_and_sanitized; test_retry_classifier_and_limits |
| Expiry before approval and execution; rejected/expired cannot execute; approved-but-expired fails | decide/recover/executable | test_expiry_before_approval_rejection_and_after_approval; test_real_expiry_during_tool_discovery_prevents_mutation |
| Actor, payload, timestamps, attempt history and result audit | approvals + approval_events triggers | test_audit_history_retains_each_attempt_and_result; test_atomic_approval_outbox_restart_replay_and_ownership |
| Reviewed payload, ownership, key and approved decision immutability | freeze_reviewed_approval database trigger | test_reviewed_payload_identity_and_decision_are_immutable |
| Scheduled-only durable dispatch; crash after decision | transactional outbox; dispatch_approvals; dispatch_claim/dispatched | test_dispatch_after_app_crash_and_ambiguous_submission; test_dispatch_lease_restart_and_fencing; test_scheduled_only_topology_and_worker_secret_bindings |
| Recovery when Workflow terminates before worker claim | submitted_runs/terminal_run/recover | test_terminal_workflow_before_claim_requeues_with_new_generation |
| Lost external response or database result persistence | execute_approval + lease recovery + stable key | test_write_succeeded_but_result_lost_replays_same_external_task |
| Revalidation of exact action before external call | approval_worker.write_task | test_worker_revalidates_persisted_action_before_writer; test_expiry_revalidated_immediately_before_write; test_real_expiry_during_tool_discovery_prevents_mutation |
| No HTTP writer, separate worker secret bindings | decide_task, worker, DAB Jobs | tests/test_identity_boundaries.py::test_only_approval_handler_calls_privileged_factory (historical name; now asserts worker-only factory caller); tests/test_identity_boundaries.py::test_approval_never_constructs_writer; test_scheduled_only_topology_and_worker_secret_bindings |
| Review card fields, hidden internals, JSON details and polling response | StoreTaskReview; proposals public SQL projection | test_frontend_review_fields_and_no_internal_metadata; test_public_projection_hides_internal_execution_data; test_poll_response_serializes_only_review_fields |
| Legacy data migration without replaying ambiguous writes | resources/migrations/002_durable_approvals.sql | test_migration_expires_legacy_pending_and_quarantines_ambiguous_writes |

## Partial — live Databricks acceptance required

- Lakebase OAuth, runtime grants, real restart/commit behavior and concurrent Jobs accessing the selected database have not been tested in a workspace. Local PostgreSQL proves SQL behavior, not live Lakebase configuration.
- Databricks schedule, run-as identity, secret scope ACLs, real Jobs submission-token deduplication, cluster startup/failure and Job recovery have not run live. Fake Jobs tests prove code branches and stable tokens. Pinned JobsAPI.run_now supports the used job_parameters/idempotency_token arguments; pinned DAB schema validation passes.
- The real OpsTask provider must durably honor identical-key/payload replay and reject conflicting payloads. Local demo repository proves this contract only for the synthetic provider. A stale request may still be in flight externally after its lease expires; database fencing alone cannot provide exactly-once external creation.
- Frontend builds and source/projection checks passed; no new browser automation test was run.

## Missing

No requested durability mechanism remains absent in code. Live acceptance evidence above remains missing; production readiness must not be inferred from local test success.

## Executed checks

- Full Python suite with TEST_POSTGRES_DSN pointing at isolated local PostgreSQL: **107 passed, 2 skipped**, 43 dependency warnings. The skipped tests are the unconfigured opt-in live Genie/Lakebase session tests. Raw output: pytest.txt.
- Three actual local MCP processes and credential separation/approval/worker/replay/provenance scenarios: passed (`uv run python -m scripts.validate_demo_stack`). Fixture-backed Genie/model and local fake approval store; not a live end-to-end Databricks run. Durable SQL is separately verified above.
- Frontend `npm run build --prefix e2e-chatbot-app-next`: passed. No new dependencies.
- `uv build --all-packages --wheel`: both packages passed; wheels.txt.
- `uv run python -m scripts.stage_apps --target demo`: four artifacts; staging.txt.
- Deployment validation for dev, prod, demo: all passed against the pinned schema; config-*.json explicitly states live_verified=false.
- `git diff --check`: passed.

Migration/deployment is deliberately not executed against any live resource. Dispatcher defaults to PAUSED. See [selected-resource rollout and grants](../../DURABLE_APPROVALS.md).
