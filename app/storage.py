"""SQLite for local use; PostgreSQL/Lakebase via a securely supplied DSN."""
import os
import sqlite3
from contextlib import contextmanager

SCHEMA = (
    'CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, session TEXT, role TEXT, content TEXT, sequence BIGINT)',
    'CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY, session TEXT, title TEXT, status TEXT, external_id TEXT)',
    'CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, session TEXT, title TEXT)',
    'CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY, owner TEXT, content TEXT)',
)

class Connection:
    def __init__(self, raw, postgres=False):
        self.raw, self.postgres = raw, postgres

    def execute(self, sql, params=()):
        return self.raw.execute(sql.replace('?', '%s') if self.postgres else sql, params)

    def executemany(self, sql, rows):
        for row in rows:
            self.execute(sql, row)

@contextmanager
def connect(path):
    dsn = os.getenv('LAKEBASE_DSN')
    if dsn:
        import psycopg
        from psycopg.rows import dict_row
        raw = psycopg.connect(dsn, row_factory=dict_row, sslmode='verify-full')
    else:
        raw = sqlite3.connect(path, timeout=30)
        raw.row_factory = sqlite3.Row
    db = Connection(raw, bool(dsn))
    try:
        for statement in SCHEMA:
            db.execute(statement)
        # Upgrade the earlier local demo without deleting its data.
        if not dsn:
            columns = {r['name'] for r in raw.execute('PRAGMA table_info(messages)')}
            for name, kind in [('id', 'TEXT'), ('sequence', 'BIGINT')]:
                if name not in columns:
                    raw.execute(f'ALTER TABLE messages ADD COLUMN {name} {kind}')
            if 'external_id' not in {r['name'] for r in raw.execute('PRAGMA table_info(approvals)')}:
                raw.execute('ALTER TABLE approvals ADD COLUMN external_id TEXT')
        yield db
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()
