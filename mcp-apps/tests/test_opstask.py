from concurrent.futures import ThreadPoolExecutor
import pytest
from opstask.repository import TaskRepository
ARGS=dict(title='Synthetic follow-up',store_id='DEMO-001',assignee='DEMO-MANAGER',due_date='2030-01-15',idempotency_key='approval-1')
def test_atomic_replay_conflict_and_restart(tmp_path):
    path=tmp_path/'tasks.db';repo=TaskRepository(path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:repo.create(**ARGS),range(8)))
    assert len({r.task_id for r in results})==1 and sum(not r.replayed for r in results)==1
    restored=TaskRepository(path)
    assert restored.create(**ARGS).task_id==results[0].task_id
    with pytest.raises(ValueError,match='conflict'): restored.create(**dict(ARGS,title='Different task'))
    assert len(repo.list('DEMO-001').tasks)==2
    first=repo.list('DEMO-001',limit=1);second=repo.list('DEMO-001',limit=1,cursor=first.next_cursor)
    assert first.tasks[0].task_id != second.tasks[0].task_id
    with pytest.raises(ValueError): repo.list('DEMO-002',cursor=first.next_cursor)
    with pytest.raises(ValueError): repo.get('unknown')
    with pytest.raises(ValueError): repo.create(**dict(ARGS,store_id='unknown'))
    with pytest.raises(ValueError): repo.create(**dict(ARGS,due_date='invalid'))
