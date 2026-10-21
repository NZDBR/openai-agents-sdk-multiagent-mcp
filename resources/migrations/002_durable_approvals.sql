-- Run once, with App/Jobs stopped, in the explicitly selected schema.
-- Substitute store_ops consistently if STORE_OPS_SCHEMA differs. Back up first.
BEGIN;
ALTER TABLE store_ops.approvals RENAME TO approvals_legacy;
CREATE TABLE IF NOT EXISTS store_ops.approvals (
  proposal_id TEXT PRIMARY KEY, employee_id TEXT NOT NULL, session_id TEXT NOT NULL,
  store_id TEXT NOT NULL, action_type TEXT NOT NULL CHECK (action_type='CREATE_TASK'),
  tool_name TEXT NOT NULL, reviewed_payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), expires_at TIMESTAMPTZ NOT NULL,
  approval_state TEXT NOT NULL DEFAULT 'PENDING_APPROVAL'
    CHECK (approval_state IN ('PENDING_APPROVAL','APPROVED','REJECTED','EXPIRED')),
  approved_by TEXT, approved_at TIMESTAMPTZ,
  execution_state TEXT NOT NULL DEFAULT 'NOT_STARTED'
    CHECK (execution_state IN ('NOT_STARTED','QUEUED','EXECUTING','EXECUTED','RETRYABLE_FAILURE','FAILED')),
  idempotency_key TEXT NOT NULL UNIQUE CHECK (idempotency_key=proposal_id), result_task_id TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count>=0), last_error TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  lease_token TEXT, lease_expires_at TIMESTAMPTZ, execution_started_at TIMESTAMPTZ,
  last_attempt_at TIMESTAMPTZ, executed_at TIMESTAMPTZ,
  CHECK (approval_state!='APPROVED' OR (approved_by=employee_id AND approved_at IS NOT NULL)),
  CHECK (execution_state NOT IN ('QUEUED','EXECUTING','EXECUTED','RETRYABLE_FAILURE') OR approval_state='APPROVED')
);
CREATE TABLE IF NOT EXISTS store_ops.approval_outbox (
  approval_id TEXT NOT NULL REFERENCES store_ops.approvals(proposal_id), generation INTEGER NOT NULL,
  run_id BIGINT, submitted_at TIMESTAMPTZ, dispatch_count INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(), lease_token TEXT, lease_expires_at TIMESTAMPTZ,
  last_error TEXT, PRIMARY KEY(approval_id,generation)
);
CREATE INDEX IF NOT EXISTS approval_recovery ON store_ops.approvals(execution_state,next_attempt_at,lease_expires_at);
CREATE INDEX IF NOT EXISTS approval_employee ON store_ops.approvals(employee_id,session_id,created_at);
CREATE OR REPLACE FUNCTION store_ops.freeze_reviewed_approval() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF ROW(OLD.proposal_id,OLD.employee_id,OLD.session_id,OLD.store_id,OLD.action_type,OLD.tool_name,
         OLD.reviewed_payload,OLD.idempotency_key,OLD.created_at,OLD.expires_at)
     IS DISTINCT FROM
     ROW(NEW.proposal_id,NEW.employee_id,NEW.session_id,NEW.store_id,NEW.action_type,NEW.tool_name,
         NEW.reviewed_payload,NEW.idempotency_key,NEW.created_at,NEW.expires_at) THEN
    RAISE EXCEPTION 'Reviewed proposal is immutable; create a new proposal';
  END IF;
  IF OLD.approval_state!='PENDING_APPROVAL' AND
     ROW(OLD.approval_state,OLD.approved_by,OLD.approved_at) IS DISTINCT FROM
     ROW(NEW.approval_state,NEW.approved_by,NEW.approved_at) THEN
    RAISE EXCEPTION 'Approval decision is immutable';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS freeze_reviewed_approval ON store_ops.approvals;
CREATE TRIGGER freeze_reviewed_approval BEFORE UPDATE ON store_ops.approvals
  FOR EACH ROW EXECUTE FUNCTION store_ops.freeze_reviewed_approval();

CREATE TABLE IF NOT EXISTS store_ops.approval_events (
  event_id BIGSERIAL PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES store_ops.approvals(proposal_id),
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(), approval_state TEXT NOT NULL,
  execution_state TEXT NOT NULL, approved_by TEXT, retry_count INTEGER NOT NULL,
  result_task_id TEXT, last_error TEXT
);
CREATE OR REPLACE FUNCTION store_ops.audit_approval_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO store_ops.approval_events(proposal_id,approval_state,execution_state,approved_by,retry_count,result_task_id,last_error)
  VALUES(NEW.proposal_id,NEW.approval_state,NEW.execution_state,NEW.approved_by,NEW.retry_count,NEW.result_task_id,NEW.last_error);
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS audit_approval_transition ON store_ops.approvals;
CREATE TRIGGER audit_approval_transition AFTER INSERT OR UPDATE ON store_ops.approvals
  FOR EACH ROW EXECUTE FUNCTION store_ops.audit_approval_transition();

INSERT INTO store_ops.approvals
 (proposal_id,employee_id,session_id,store_id,action_type,tool_name,reviewed_payload,
  created_at,expires_at,approval_state,approved_by,approved_at,execution_state,idempotency_key,
  result_task_id,last_error)
SELECT id,owner_id,session_id,payload->>'store_id','CREATE_TASK',
 current_setting('store_ops.migration_tool_name'),payload,created_at,created_at,
 CASE WHEN status='pending' THEN 'EXPIRED' WHEN status='rejected' THEN 'REJECTED' ELSE 'APPROVED' END,
 CASE WHEN status NOT IN ('pending','rejected') THEN owner_id END,
 CASE WHEN status NOT IN ('pending','rejected') THEN coalesce(decided_at,created_at) END,
 CASE WHEN status='created' THEN 'EXECUTED' WHEN status IN ('executing','needs_reconciliation') THEN 'FAILED' ELSE 'NOT_STARTED' END,
 id,external_id,CASE WHEN status IN ('executing','needs_reconciliation') THEN 'LEGACY_RECONCILIATION_REQUIRED' END
FROM store_ops.approvals_legacy;
COMMIT;
-- Keep approvals_legacy read-only for audit. Legacy pending records are expired,
-- requiring fresh review. Never seed the outbox for legacy ambiguous writes.
