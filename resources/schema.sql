CREATE SCHEMA IF NOT EXISTS store_ops;
CREATE TABLE IF NOT EXISTS store_ops.memories (
  id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, content TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS memory_owner ON store_ops.memories(owner_id);
CREATE TABLE IF NOT EXISTS store_ops.approvals (
  id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, session_id TEXT NOT NULL,
  payload JSONB NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','executing','rejected','created','needs_reconciliation')),
  external_id TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), decided_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS store_ops.workflow_runs (
  request_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, run_id BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
