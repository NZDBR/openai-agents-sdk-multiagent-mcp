"""Atomic Lakebase approval state, transactional outbox and fenced execution claims."""
import json
import os
from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class ApprovalPolicy:
    ttl: int = 86400
    lease: int = 120
    timeout: int = 45
    retries: int = 5
    backoff: int = 30
    backoff_cap: int = 3600

    @classmethod
    def load(cls):
        overrides = json.loads(os.getenv('APPROVAL_POLICY_JSON', '{}'))
        if set(overrides) - set(cls().__dict__):
            raise ValueError('Unknown approval policy key')
        policy = cls(**{name: int(os.getenv('APPROVAL_' + name.upper(), overrides.get(name, default)))
                       for name, default in cls().__dict__.items()})
        if min(policy.__dict__.values()) <= 0 or policy.timeout * 2 >= policy.lease:
            raise ValueError('Approval limits must be positive and lease must exceed twice the MCP timeout')
        return policy


class ApprovalPersistence:
    async def propose(self, owner, session_id, payload):
        from agent_server.actions import TaskProposal
        payload = TaskProposal(**payload).model_dump(mode='json')
        proposal_id = uuid4().hex
        await self.sql('''INSERT INTO store_ops.approvals
            (proposal_id,employee_id,session_id,store_id,action_type,tool_name,reviewed_payload,
             idempotency_key,expires_at)
            VALUES (%s,%s,%s,%s,'CREATE_TASK',%s,%s::jsonb,%s,now()+%s*interval '1 second')''',
            (proposal_id, owner, session_id, payload['store_id'], os.getenv('OPSTASK_CREATE_TOOL','create_task'),
             json.dumps(payload), proposal_id, ApprovalPolicy.load().ttl))
        return {'approval_id': proposal_id, 'approval_state': 'PENDING_APPROVAL', 'execution_state': 'NOT_STARTED', 'task': payload}

    async def proposals(self, owner, session_id):
        # Explicit public projection: never return identity, tool or retry metadata.
        await self.sql('''UPDATE store_ops.approvals SET approval_state='EXPIRED',updated_at=now()
            WHERE employee_id=%s AND session_id=%s AND approval_state='PENDING_APPROVAL' AND expires_at<=now()''', (owner,session_id))
        return await self.sql('''SELECT proposal_id AS id,reviewed_payload AS payload,action_type,
            created_at,expires_at,approval_state,execution_state FROM store_ops.approvals
            WHERE employee_id=%s AND session_id=%s ORDER BY created_at DESC LIMIT 20''', (owner,session_id))

    async def decide(self, owner, session_id, proposal_id, approve):
        # The queue insert and decision commit in ONE statement/transaction.
        await self.sql('''WITH decision AS (
            UPDATE store_ops.approvals SET
                approval_state=CASE WHEN expires_at<=now() THEN 'EXPIRED' WHEN %s THEN 'APPROVED' ELSE 'REJECTED' END,
                execution_state=CASE WHEN expires_at>now() AND %s THEN 'QUEUED' ELSE 'NOT_STARTED' END,
                approved_by=CASE WHEN expires_at>now() AND %s THEN employee_id ELSE NULL END,
                approved_at=CASE WHEN expires_at>now() AND %s THEN now() ELSE NULL END,updated_at=now()
            WHERE proposal_id=%s AND employee_id=%s AND session_id=%s AND approval_state='PENDING_APPROVAL'
            RETURNING proposal_id,approval_state)
            INSERT INTO store_ops.approval_outbox(approval_id,generation)
            SELECT proposal_id,0 FROM decision WHERE approval_state='APPROVED' ON CONFLICT DO NOTHING''',
            (approve,approve,approve,approve,proposal_id,owner,session_id))
        rows = await self.sql('''SELECT approval_state,execution_state,result_task_id AS task_id
            FROM store_ops.approvals WHERE proposal_id=%s AND employee_id=%s AND session_id=%s''', (proposal_id,owner,session_id))
        if not rows:
            raise PermissionError('Proposal not found for this employee/session')
        return rows[0]

    async def recover(self):
        p = ApprovalPolicy.load()
        # Reject/expire all unstarted work; expired active attempts are settled after lease expiry.
        await self.sql('''UPDATE store_ops.approvals SET approval_state='EXPIRED',updated_at=now()
            WHERE approval_state='PENDING_APPROVAL' AND expires_at<=now()''')
        await self.sql('''UPDATE store_ops.approvals SET execution_state='FAILED',last_error='EXPIRED',updated_at=now()
            WHERE approval_state='APPROVED' AND expires_at<=now() AND
            (execution_state IN ('QUEUED','RETRYABLE_FAILURE') OR
             (execution_state='EXECUTING' AND lease_expires_at<=now()))''')
        await self.sql('''UPDATE store_ops.approvals SET
            execution_state=CASE WHEN retry_count+1>=%s THEN 'FAILED' ELSE 'RETRYABLE_FAILURE' END,
            retry_count=retry_count+1,last_error='LEASE_EXPIRED',updated_at=now(),
            next_attempt_at=now()+least(%s,%s*power(2,least(retry_count,20)))*interval '1 second',
            lease_token=NULL,lease_expires_at=NULL
            WHERE approval_state='APPROVED' AND execution_state='EXECUTING' AND lease_expires_at<=now()
            AND expires_at>now()''', (p.retries,p.backoff_cap,p.backoff))
        await self.sql('''INSERT INTO store_ops.approval_outbox(approval_id,generation)
            SELECT proposal_id,retry_count FROM store_ops.approvals
            WHERE approval_state='APPROVED' AND execution_state='RETRYABLE_FAILURE'
            AND next_attempt_at<=now() AND expires_at>now() ON CONFLICT DO NOTHING''')

    async def dispatch_claim(self, limit=20):
        p = ApprovalPolicy.load()
        token = uuid4().hex
        return await self.sql('''WITH due AS (
            SELECT o.approval_id,o.generation FROM store_ops.approval_outbox o
            JOIN store_ops.approvals a ON a.proposal_id=o.approval_id
            WHERE a.approval_state='APPROVED' AND a.expires_at>now()
              AND a.retry_count=o.generation AND a.execution_state IN ('QUEUED','RETRYABLE_FAILURE')
              AND o.run_id IS NULL AND o.next_attempt_at<=now()
              AND (o.lease_expires_at IS NULL OR o.lease_expires_at<=now())
            ORDER BY o.next_attempt_at LIMIT %s FOR UPDATE OF o SKIP LOCKED)
            UPDATE store_ops.approval_outbox o SET lease_token=%s,lease_expires_at=now()+%s*interval '1 second'
            FROM due WHERE o.approval_id=due.approval_id AND o.generation=due.generation RETURNING o.*''', (limit,token,p.lease))

    async def dispatched(self, row, run_id):
        await self.sql('''WITH submitted AS (
            UPDATE store_ops.approval_outbox SET run_id=%s,submitted_at=now(),lease_token=NULL,lease_expires_at=NULL
            WHERE approval_id=%s AND generation=%s AND lease_token=%s AND lease_expires_at>now() RETURNING approval_id,generation)
            UPDATE store_ops.approvals a SET execution_state='QUEUED',updated_at=now()
            FROM submitted s WHERE a.proposal_id=s.approval_id AND a.retry_count=s.generation
            AND a.execution_state='RETRYABLE_FAILURE' ''', (run_id,row['approval_id'],row['generation'],row['lease_token']))

    async def dispatch_failed(self, row):
        # Submission can be ambiguous: retain the SAME generation/token for every retry.
        p = ApprovalPolicy.load()
        await self.sql('''WITH failed AS (
            UPDATE store_ops.approval_outbox SET dispatch_count=dispatch_count+1,last_error='WORKFLOW_SUBMISSION_FAILED',
            next_attempt_at=now()+least(%s,%s*power(2,least(dispatch_count,20)))*interval '1 second',
            lease_token=NULL,lease_expires_at=NULL WHERE approval_id=%s AND generation=%s AND lease_token=%s
            AND lease_expires_at>now() RETURNING approval_id,generation,dispatch_count)
            UPDATE store_ops.approvals a SET execution_state='FAILED',last_error='WORKFLOW_SUBMISSION_FAILED',updated_at=now()
            FROM failed f WHERE a.proposal_id=f.approval_id AND a.retry_count=f.generation AND f.dispatch_count>=%s
            AND a.execution_state IN ('QUEUED','RETRYABLE_FAILURE')''',
            (p.backoff_cap,p.backoff,row['approval_id'],row['generation'],row['lease_token'],p.retries))

    async def submitted_runs(self):
        return await self.sql('''SELECT o.* FROM store_ops.approval_outbox o JOIN store_ops.approvals a
            ON a.proposal_id=o.approval_id AND a.retry_count=o.generation
            WHERE o.run_id IS NOT NULL AND a.execution_state IN ('QUEUED','RETRYABLE_FAILURE')
            AND a.approval_state='APPROVED' ORDER BY o.submitted_at LIMIT 100''')

    async def terminal_run(self, row):
        p = ApprovalPolicy.load()
        await self.sql('''UPDATE store_ops.approvals SET retry_count=retry_count+1,
            execution_state=CASE WHEN retry_count+1>=%s THEN 'FAILED' ELSE 'RETRYABLE_FAILURE' END,
            next_attempt_at=now()+least(%s,%s*power(2,least(retry_count,20)))*interval '1 second',
            last_error='WORKFLOW_TERMINATED_WITHOUT_RESULT',updated_at=now()
            WHERE proposal_id=%s AND retry_count=%s AND execution_state IN ('QUEUED','RETRYABLE_FAILURE')''',
            (p.retries,p.backoff_cap,p.backoff,row['approval_id'],row['generation']))

    async def execution_claim(self, approval_id):
        p = ApprovalPolicy.load()
        await self.recover()
        rows = await self.sql('''UPDATE store_ops.approvals SET execution_state='EXECUTING',lease_token=%s,
            lease_expires_at=now()+%s*interval '1 second',execution_started_at=coalesce(execution_started_at,now()),
            last_attempt_at=now(),updated_at=now()
            WHERE proposal_id=%s AND approval_state='APPROVED' AND approved_by=employee_id AND approved_at IS NOT NULL
            AND execution_state IN ('QUEUED','RETRYABLE_FAILURE') AND next_attempt_at<=now()
            AND expires_at>now() AND retry_count<%s
            RETURNING *''', (uuid4().hex,p.lease,approval_id,p.retries))
        return rows[0] if rows else None

    async def executable(self, row):
        return bool(await self.sql('''SELECT proposal_id FROM store_ops.approvals WHERE proposal_id=%s
            AND lease_token=%s AND lease_expires_at>now() AND expires_at>now()
            AND approval_state='APPROVED' AND execution_state='EXECUTING' ''', (row['proposal_id'],row['lease_token'])))

    async def execution_finish(self, row, task_id=None, error=None, retryable=False):
        p = ApprovalPolicy.load()
        return await self.sql('''UPDATE store_ops.approvals SET
            execution_state=CASE WHEN %s::text IS NOT NULL THEN 'EXECUTED'
                WHEN %s AND retry_count+1<%s AND expires_at>now() THEN 'RETRYABLE_FAILURE' ELSE 'FAILED' END,
            result_task_id=%s,retry_count=retry_count+CASE WHEN %s::text IS NULL THEN 1 ELSE 0 END,
            last_error=%s,next_attempt_at=now()+least(%s,%s*power(2,least(retry_count,20)))*interval '1 second',
            executed_at=CASE WHEN %s::text IS NOT NULL THEN now() ELSE NULL END,updated_at=now(),
            lease_token=NULL,lease_expires_at=NULL
            WHERE proposal_id=%s AND lease_token=%s AND lease_expires_at>now() AND execution_state='EXECUTING'
            RETURNING execution_state,result_task_id''',
            (task_id,retryable,p.retries,task_id,task_id,error,p.backoff_cap,p.backoff,task_id,row['proposal_id'],row['lease_token']))
