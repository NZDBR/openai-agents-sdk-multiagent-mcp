"""Real local PostgreSQL tests, never proof of live Lakebase/Jobs/MCP authorization.
Set TEST_POSTGRES_DSN to an isolated local PostgreSQL instance; CI provides one.
Every test gets an isolated schema. No workspace resources are accessed.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
from types import SimpleNamespace
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
import pytest
from agent_server.approval_store import ApprovalPolicy
from agent_server.memory import LakebaseStore
from agent_server import approval_worker as worker
from tests.test_approvals import task


@pytest.fixture
def db():
    dsn=os.getenv('TEST_POSTGRES_DSN')
    if not dsn: pytest.skip('Local PostgreSQL test DSN absent (CI supplies PostgreSQL)')
    schema='approval_test_'+uuid4().hex
    def connection(): return psycopg.connect(dsn,autocommit=True,row_factory=dict_row)
    with connection() as c: c.execute(Path('resources/schema.sql').read_text().replace('store_ops',schema))
    store=LakebaseStore.__new__(LakebaseStore);store.schema=schema
    def execute(query,params=()):
        with connection() as c:
            result=c.execute(query.replace('store_ops',schema),params)
            return result.fetchall() if result.description else []
    async def sql(query,params=()): return await asyncio.to_thread(execute,query,params)
    store.sql=sql;store.raw=execute;store.connect=connection
    yield store
    with connection() as c: c.execute('DROP SCHEMA '+schema+' CASCADE')


def run(awaitable): return asyncio.run(awaitable)


def proposal(db,approve=True):
    p=run(db.propose('employee','session',task()))['approval_id']
    if approve: run(db.decide('employee','session',p,True))
    return p


def row(db,p): return db.raw('SELECT * FROM store_ops.approvals WHERE proposal_id=%s',(p,))[0]


def age_lease(db,p):
    db.raw("UPDATE store_ops.approvals SET lease_expires_at=now()-interval '1 second' WHERE proposal_id=%s",(p,))


def due(db,p):
    db.raw("UPDATE store_ops.approvals SET next_attempt_at=now()-interval '1 second' WHERE proposal_id=%s",(p,))


def test_atomic_approval_outbox_restart_replay_and_ownership(db):
    p=proposal(db,False)
    for owner,session in [('other','session'),('employee','other')]:
        with pytest.raises(PermissionError): run(db.decide(owner,session,p,True))
    with ThreadPoolExecutor(4) as pool:
        results=list(pool.map(lambda _:run(db.decide('employee','session',p,True)),range(4)))
    assert all(r['execution_state']=='QUEUED' for r in results)
    assert len(db.raw('SELECT * FROM store_ops.approval_outbox'))==1
    restored=LakebaseStore.__new__(LakebaseStore);restored.sql=db.sql
    assert run(restored.decide('employee','session',p,True))==results[0]
    r=row(db,p)
    assert r['approved_by']=='employee' and r['approved_at'] and r['created_at'] and r['updated_at']
    assert r['idempotency_key']==p and r['reviewed_payload']==task()


def test_only_one_lease_owner_recovery_and_stale_fencing(db):
    p=proposal(db)
    with ThreadPoolExecutor(4) as pool: claims=list(pool.map(lambda _:run(db.execution_claim(p)),range(4)))
    assert sum(c is not None for c in claims)==1
    old=next(c for c in claims if c)
    age_lease(db,p);run(db.recover())
    r=row(db,p);assert r['execution_state']=='RETRYABLE_FAILURE' and r['retry_count']==1
    assert r['next_attempt_at']>r['updated_at'] and r['last_error']=='LEASE_EXPIRED'
    assert run(db.execution_claim(p)) is None
    due(db,p);new=run(db.execution_claim(p));assert new['lease_token']!=old['lease_token']
    assert run(db.execution_finish(old,task_id='STALE'))==[]
    run(db.execution_finish(new,task_id='TASK-1'))
    assert run(db.execution_finish(old,task_id='WRONG'))==[]
    assert row(db,p)['result_task_id']=='TASK-1' and row(db,p)['executed_at']
    assert run(db.execution_claim(p)) is None


def test_expiry_before_approval_rejection_and_after_approval(db,monkeypatch):
    # Clock-independent expiry by changing TTL before insertion, never editing immutable payload.
    monkeypatch.setenv('APPROVAL_TTL','1')
    pending=proposal(db,False);approved=proposal(db);rejected=proposal(db,False)
    run(db.decide('employee','session',rejected,False))
    db.raw('SELECT pg_sleep(1.05)')
    assert run(db.decide('employee','session',pending,True))['approval_state']=='EXPIRED'
    assert run(db.execution_claim(approved)) is None
    assert row(db,approved)['approval_state']=='APPROVED'
    assert row(db,approved)['execution_state']=='FAILED' and row(db,approved)['last_error']=='EXPIRED'
    assert run(db.execution_claim(rejected)) is None
    assert run(db.decide('employee','session',rejected,True))['approval_state']=='REJECTED'


def test_expiry_revalidated_immediately_before_write(db,settings,monkeypatch):
    p=proposal(db)
    calls=[]
    class Writer:
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def list_tools(self):
            from mcp.types import Tool
            return [Tool(name='create_task',inputSchema={'type':'object'})]
        async def call_tool(self,*a):calls.append(a)
    monkeypatch.setattr(worker,'app_write_mcp_client',lambda *a,**k:Writer())
    async def invalid(_):return False
    db.executable=invalid
    run(worker.execute_approval(db,settings,p))
    assert not calls and row(db,p)['execution_state']=='FAILED'


def test_reviewed_payload_identity_and_decision_are_immutable(db):
    p=proposal(db)
    for field,expression in [('reviewed_payload',"'{\"title\":\"changed\"}'::jsonb"),
                             ('tool_name',"'different'"),('employee_id',"'other'"),
                             ('idempotency_key',"'different'"),('approval_state',"'REJECTED'")]:
        with pytest.raises(psycopg.Error):
            db.raw(f'UPDATE store_ops.approvals SET {field}={expression} WHERE proposal_id=%s',(p,))
    assert row(db,p)['reviewed_payload']==task()


def test_bounded_retry_backoff_and_sanitized_errors(db,settings,monkeypatch):
    monkeypatch.setenv('APPROVAL_RETRIES','2')
    p=proposal(db)
    async def timeout(*args):raise TimeoutError('SECRET credential payload')
    monkeypatch.setattr(worker,'write_task',timeout)
    run(worker.execute_approval(db,settings,p))
    first=row(db,p);assert first['retry_count']==1 and first['execution_state']=='RETRYABLE_FAILURE'
    assert first['last_error']=='TRANSIENT_TRANSPORT' and first['next_attempt_at']>first['updated_at']
    assert run(db.execution_claim(p)) is None
    due(db,p);run(worker.execute_approval(db,settings,p))
    assert row(db,p)['retry_count']==2 and row(db,p)['execution_state']=='FAILED'
    assert run(db.execution_claim(p)) is None


def test_permanent_error_no_retry(db,settings,monkeypatch):
    p=proposal(db)
    async def forbidden(*args):raise PermissionError('SECRET')
    monkeypatch.setattr(worker,'write_task',forbidden)
    run(worker.execute_approval(db,settings,p));run(db.recover())
    assert row(db,p)['last_error']=='PERMANENT_OR_UNCONFIRMED'
    assert row(db,p)['execution_state']=='FAILED' and run(db.execution_claim(p)) is None


def test_dispatch_after_app_crash_and_ambiguous_submission(db):
    p=proposal(db);tokens=[]
    class Jobs:
        def run_now(self,**kw):tokens.append(kw['idempotency_token']);return SimpleNamespace(run_id=99)
        def get_run(self,**kw):return SimpleNamespace(state=SimpleNamespace(life_cycle_state='RUNNING'))
    actual=db.dispatched
    async def crash(*args):raise RuntimeError('App lost submission response')
    db.dispatched=crash
    run(worker.dispatch_approvals(db,Jobs(),123))
    db.raw("UPDATE store_ops.approval_outbox SET next_attempt_at=now()-interval '1 second'")
    db.dispatched=actual
    run(worker.dispatch_approvals(db,Jobs(),123));run(worker.dispatch_approvals(db,Jobs(),123))
    assert len(tokens)==2 and tokens[0]==tokens[1]
    assert db.raw('SELECT run_id FROM store_ops.approval_outbox')[0]['run_id']==99
    assert row(db,p)['execution_state']=='QUEUED'


def test_dispatch_lease_restart_and_fencing(db):
    proposal(db)
    old=run(db.dispatch_claim())[0]
    assert run(db.dispatch_claim())==[]
    db.raw("UPDATE store_ops.approval_outbox SET lease_expires_at=now()-interval '1 second'")
    new=run(db.dispatch_claim())[0]
    run(db.dispatched(old,1));assert db.raw('SELECT run_id FROM store_ops.approval_outbox')[0]['run_id'] is None
    run(db.dispatched(new,2));assert db.raw('SELECT run_id FROM store_ops.approval_outbox')[0]['run_id']==2


def test_terminal_workflow_before_claim_requeues_with_new_generation(db):
    p=proposal(db)
    class Jobs:
        def run_now(self,**kw):return SimpleNamespace(run_id=10)
        def get_run(self,**kw):return SimpleNamespace(state=SimpleNamespace(life_cycle_state='TERMINATED'))
    run(worker.dispatch_approvals(db,Jobs(),123));run(worker.dispatch_approvals(db,Jobs(),123))
    assert row(db,p)['execution_state']=='RETRYABLE_FAILURE'
    due(db,p);run(db.recover())
    assert [r['generation'] for r in db.raw('SELECT * FROM store_ops.approval_outbox ORDER BY generation')]==[0,1]


def test_write_succeeded_but_result_lost_replays_same_external_task(db,settings,monkeypatch,tmp_path):
    from opstask.repository import TaskRepository
    repo=TaskRepository(tmp_path/'tasks.db')
    payload=dict(task(),store_id='DEMO-001');p=run(db.propose('employee','session',payload))['approval_id']
    run(db.decide('employee','session',p,True))
    ids=[]
    async def provider(settings,r,store):
        created=repo.create(**r['reviewed_payload'],idempotency_key=r['idempotency_key']);ids.append(created.task_id)
        if len(ids)==1:raise TimeoutError('External task exists, response lost')
        return created.task_id
    monkeypatch.setattr(worker,'write_task',provider)
    run(worker.execute_approval(db,settings,p));due(db,p)
    run(worker.execute_approval(db,settings,p))
    assert ids[0]==ids[1]==row(db,p)['result_task_id']
    assert len(repo.list('DEMO-001').tasks)==2
    # Actual successful external write followed by database persistence failure.
    q=run(db.propose('employee','session',payload))['approval_id'];run(db.decide('employee','session',q,True))
    actual=db.execution_finish
    async def broken(*a,**kw):raise ConnectionError('Database unavailable')
    db.execution_finish=broken
    with pytest.raises(ConnectionError):run(worker.execute_approval(db,settings,q))
    age_lease(db,q);run(db.recover());due(db,q);db.execution_finish=actual
    run(worker.execute_approval(db,settings,q))
    assert row(db,q)['execution_state']=='EXECUTED' and ids[-1]==ids[-2]
    assert len(repo.list('DEMO-001').tasks)==3


def test_public_projection_hides_internal_execution_data(db):
    proposal(db)
    public=run(db.proposals('employee','session'))[0]
    assert set(public)=={'id','payload','action_type','created_at','expires_at','approval_state','execution_state'}
    assert run(db.proposals('other','session'))==[]


def test_persisted_states_survive_new_store_instances(db):
    p=proposal(db,False)
    def restored():
        obj=LakebaseStore.__new__(LakebaseStore);obj.sql=db.sql;return obj
    assert run(restored().proposals('employee','session'))[0]['approval_state']=='PENDING_APPROVAL'
    run(restored().decide('employee','session',p,True))
    assert run(restored().proposals('employee','session'))[0]['execution_state']=='QUEUED'
    claim=run(restored().execution_claim(p))
    run(restored().execution_finish(claim,error='TRANSIENT_TRANSPORT',retryable=True))
    assert run(restored().proposals('employee','session'))[0]['execution_state']=='RETRYABLE_FAILURE'
    due(db,p);claim=run(restored().execution_claim(p));run(restored().execution_finish(claim,task_id='TASK'))
    assert run(restored().proposals('employee','session'))[0]['execution_state']=='EXECUTED'


def test_submission_retries_are_bounded_and_sanitized(db,monkeypatch):
    monkeypatch.setenv('APPROVAL_RETRIES','2');p=proposal(db)
    class Jobs:
        def run_now(self,**kw):raise ConnectionError('SECRET token')
    for _ in range(2):
        run(worker.dispatch_approvals(db,Jobs(),123))
        db.raw("UPDATE store_ops.approval_outbox SET next_attempt_at=now()-interval '1 second'")
    assert row(db,p)['execution_state']=='FAILED'
    assert row(db,p)['last_error']=='WORKFLOW_SUBMISSION_FAILED'
    assert run(db.dispatch_claim())==[]


def test_expired_execution_lease_is_fenced_without_replacement(db):
    p=proposal(db);claim=run(db.execution_claim(p));age_lease(db,p)
    assert not run(db.executable(claim))
    assert run(db.execution_finish(claim,task_id='LATE'))==[]


def test_worker_revalidates_persisted_action_before_writer(db,settings,monkeypatch):
    p=proposal(db);claim=run(db.execution_claim(p))
    calls=[]
    monkeypatch.setattr(worker,'app_write_mcp_client',lambda *a,**k:calls.append(k))
    for changed in [dict(action_type='DELETE_TASK'),dict(tool_name='delete_task'),dict(idempotency_key='other'),dict(store_id='wrong')]:
        with pytest.raises(worker.PermanentExecutionError):run(worker.write_task(settings,dict(claim,**changed),db))
    assert not calls


def test_migration_expires_legacy_pending_and_quarantines_ambiguous_writes(db):
    # Execute the migration against a separate pre-refactor schema, not a mocked parser.
    schema='legacy_test_'+uuid4().hex
    with db.connect() as c:
        c.execute('CREATE SCHEMA '+schema)
        c.execute('CREATE TABLE '+schema+'.approvals(id TEXT PRIMARY KEY,owner_id TEXT,session_id TEXT,payload JSONB,status TEXT,external_id TEXT,created_at TIMESTAMPTZ DEFAULT now(),decided_at TIMESTAMPTZ)')
        for state in ['pending','rejected','created','executing','needs_reconciliation']:
            from psycopg.types.json import Jsonb
            c.execute('INSERT INTO '+schema+'.approvals(id,owner_id,session_id,payload,status) VALUES (%s,%s,%s,%s,%s)',(state,'employee','session',Jsonb(task()),state))
        c.execute("SELECT set_config(%s,'create_task',false)",(schema+'.migration_tool_name',))
        c.execute(Path('resources/migrations/002_durable_approvals.sql').read_text().replace('store_ops',schema))
        rows={r['proposal_id']:r for r in c.execute('SELECT * FROM '+schema+'.approvals')}
        assert rows['pending']['approval_state']=='EXPIRED'
        assert rows['rejected']['approval_state']=='REJECTED'
        assert rows['created']['execution_state']=='EXECUTED'
        assert rows['executing']['execution_state']==rows['needs_reconciliation']['execution_state']=='FAILED'
        assert not c.execute('SELECT * FROM '+schema+'.approval_outbox').fetchall()
        c.execute('DROP SCHEMA '+schema+' CASCADE')


def test_frontend_review_fields_and_no_internal_metadata():
    source=Path('e2e-chatbot-app-next/client/src/components/store-task-review.tsx').read_text()
    for field in ['created_at','expires_at','approval_state','execution_state','View details','JSON.stringify(p.payload']:
        assert field in source
    for field in ['employee_id','tool_name','idempotency_key','retry_count','lease_token','last_error']:
        assert field not in source


def test_retry_classifier_and_limits(monkeypatch):
    import httpx
    for status,retryable in [(403,False),(400,False),(409,False),(429,True),(503,True)]:
        error=httpx.HTTPStatusError('SECRET',request=httpx.Request('POST','https://example.invalid'),response=httpx.Response(status))
        assert worker.classify(error)[1] is retryable
    from mcp.shared.exceptions import McpError
    from mcp.types import ErrorData, CONNECTION_CLOSED
    assert worker.classify(McpError(ErrorData(code=CONNECTION_CLOSED,message='secret')))[1]
    assert not worker.classify(McpError(ErrorData(code=-32602,message='secret')))[1]
    assert worker.classify(ExceptionGroup('secret',[TimeoutError(),ConnectionError()]))[1]
    assert not worker.classify(ExceptionGroup('secret',[TimeoutError(),PermissionError()]))[1]
    monkeypatch.setenv('APPROVAL_LEASE','40')
    with pytest.raises(ValueError):ApprovalPolicy.load()


def test_audit_history_retains_each_attempt_and_result(db):
    p=proposal(db);first=run(db.execution_claim(p))
    run(db.execution_finish(first,error='TRANSIENT_TRANSPORT',retryable=True));due(db,p)
    second=run(db.execution_claim(p));run(db.execution_finish(second,task_id='TASK-AUDIT'))
    events=db.raw('SELECT * FROM store_ops.approval_events WHERE proposal_id=%s ORDER BY event_id',(p,))
    assert events[0]['approval_state']=='PENDING_APPROVAL'
    assert sum(e['execution_state']=='EXECUTING' for e in events)==2
    assert any(e['last_error']=='TRANSIENT_TRANSPORT' for e in events)
    assert events[-1]['result_task_id']=='TASK-AUDIT'
    assert all(e['occurred_at'] for e in events)
    r=row(db,p)
    assert r['approved_by']=='employee' and all(r[k] for k in ['created_at','approved_at','execution_started_at','last_attempt_at','executed_at','updated_at'])


def test_outbox_failure_rolls_back_approval_decision(db):
    p=proposal(db,False)
    db.raw('ALTER TABLE store_ops.approval_outbox ADD CONSTRAINT reject_enqueue CHECK (generation<0)')
    with pytest.raises(psycopg.Error):run(db.decide('employee','session',p,True))
    assert row(db,p)['approval_state']=='PENDING_APPROVAL'
    assert row(db,p)['approved_at'] is None


def test_real_expiry_during_tool_discovery_prevents_mutation(db,settings,monkeypatch):
    monkeypatch.setenv('APPROVAL_TTL','1');p=proposal(db);writes=[]
    class Writer:
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def list_tools(self):
            from mcp.types import Tool
            await db.sql('SELECT pg_sleep(1.05)')
            return [Tool(name='create_task',inputSchema={'type':'object'})]
        async def call_tool(self,*a):writes.append(a)
    monkeypatch.setattr(worker,'app_write_mcp_client',lambda *a,**k:Writer())
    run(worker.execute_approval(db,settings,p))
    assert not writes and row(db,p)['execution_state']=='FAILED'


def test_poll_response_serializes_only_review_fields(db):
    from agent_server.agent import response
    proposal(db)
    public=run(db.proposals('employee','session'))
    result=response('Task proposals',{'proposals':public}).model_dump(mode='json')
    item=result['custom_outputs']['proposals'][0]
    assert isinstance(item['created_at'],str) and isinstance(item['expires_at'],str)
    assert not {'employee_id','session_id','lease_token','retry_count','tool_name','idempotency_key'} & set(item)


def test_scheduled_only_topology_and_worker_secret_bindings():
    import inspect
    import json
    from agent_server.actions import decide_task
    from scripts.validate_deployment import load_bundle, validate_schema
    handler=inspect.getsource(decide_task)
    assert 'run_now' not in handler and 'app_write_mcp_client' not in handler
    for target in ['dev','prod','demo']:
        bundle=load_bundle(target);validate_schema(bundle)
        jobs=bundle['resources']['jobs']
        assert jobs['store_operations_approval_dispatch']['schedule']['pause_status']=='PAUSED'
        assert jobs['store_operations_approval_dispatch']['max_concurrent_runs']==1
        execution=jobs['store_operations_approval_execution']
        assert execution['run_as']['service_principal_name']=='${var.approval_service_principal}'
        params=execution['tasks'][0]['notebook_task']['base_parameters']
        config=json.loads(params['deployment_config'])
        assert config['DATABRICKS_HOST']=='${var.workspace_host}'
        assert params['approval_id']=='{{job.parameters.approval_id}}'
        assert params['policy_config']=='${var.approval_policy}'
        assert execution['tasks'][0]['max_retries']==0
        app=bundle['resources']['apps']['store_operations']
        assert 'opstask-write-mcp' not in {r['name'] for r in app['resources']}
        assert 'DEMO_OPSTASK_WRITE_TOKEN' not in {e['name'] for e in app['config']['env']}
