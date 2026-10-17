"""Demo SQLite storage only; atomic idempotency, never approval policy."""
import base64
import hashlib
import json
from pathlib import Path
import sqlite3
from shared.contracts import Task, Tasks, TaskCreated
from shared.demo_data import DATA, load_fixture
class TaskRepository:
    def __init__(self,database,fixture=None):
        if str(database)==':memory:': raise ValueError('Use persistent demo file storage')
        self.database=str(database);self.fixture=fixture or DATA/'initial_tasks.json'
        Path(self.database).parent.mkdir(parents=True,exist_ok=True)
        self.initialize()
    def seed(self): return load_fixture(self.fixture)
    def connect(self): return sqlite3.connect(self.database,timeout=15)
    def initialize(self):
        raw=self.seed()
        with self.connect() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS tasks(task_id TEXT PRIMARY KEY,payload TEXT NOT NULL); CREATE TABLE IF NOT EXISTS requests(request_id TEXT PRIMARY KEY,payload TEXT NOT NULL,task_id TEXT NOT NULL);')
            for task in raw['tasks']:
                t=Task.model_validate(task)
                db.execute('INSERT OR IGNORE INTO tasks VALUES (?,?)',(t.task_id,t.model_dump_json()))
    def ready(self):
        self.seed()
        with self.connect() as db:
            if db.execute('PRAGMA quick_check').fetchone()[0]!='ok': raise RuntimeError('Invalid demo task storage')
            for row in db.execute('SELECT payload FROM tasks'): Task.model_validate_json(row[0])
            db.execute('SELECT request_id FROM requests LIMIT 1')
    def get(self,task_id):
        with self.connect() as db: row=db.execute('SELECT payload FROM tasks WHERE task_id=?',(task_id,)).fetchone()
        if not row: raise ValueError('Unknown synthetic task')
        return Task.model_validate_json(row[0])
    def list(self,store_id,status='all',limit=50,cursor=None):
        if store_id not in self.seed()['stores']: raise ValueError('Unknown synthetic store')
        if status not in {'all','open','in_progress','completed'} or not 1<=limit<=100: raise ValueError('Invalid list filter')
        after=''
        if cursor:
            try:
                c=json.loads(base64.urlsafe_b64decode(cursor.encode()))
                if c['store_id']!=store_id or c['status']!=status or not isinstance(c['after'],str): raise ValueError()
                after=c['after']
            except Exception: raise ValueError('Invalid cursor or filter mismatch') from None
        with self.connect() as db:
            rows=db.execute("SELECT payload FROM tasks WHERE json_extract(payload,'$.store_id')=? AND (?='all' OR json_extract(payload,'$.status')=?) AND task_id>? ORDER BY task_id LIMIT ?",(store_id,status,status,after,limit+1)).fetchall()
        tasks=[Task.model_validate_json(row[0]) for row in rows[:limit]]
        cursor=base64.urlsafe_b64encode(json.dumps(dict(store_id=store_id,status=status,after=tasks[-1].task_id)).encode()).decode() if len(rows)>limit else None
        return Tasks(tasks=tasks,next_cursor=cursor)
    def create(self,title,store_id,assignee,due_date,idempotency_key):
        if not title.strip() or not assignee.strip() or not idempotency_key.strip(): raise ValueError('Nonblank fields required')
        if store_id not in self.seed()['stores']: raise ValueError('Unknown synthetic store')
        payload=json.dumps(dict(title=title,store_id=store_id,assignee=assignee,due_date=str(due_date)),sort_keys=True)
        task_id='DEMO-'+hashlib.sha256(idempotency_key.encode()).hexdigest()
        task=Task(task_id=task_id,title=title,store_id=store_id,assignee=assignee,due_date=due_date)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT payload,task_id FROM requests WHERE request_id=?',(idempotency_key,)).fetchone()
            if row:
                if row[0]!=payload: raise ValueError('Idempotency key payload conflict')
                return TaskCreated(task=self.get(row[1]),task_id=row[1],replayed=True)
            db.execute('INSERT INTO tasks VALUES (?,?)',(task_id,task.model_dump_json()))
            db.execute('INSERT INTO requests VALUES (?,?,?)',(idempotency_key,payload,task_id))
        return TaskCreated(task=task,task_id=task_id,replayed=False)
