"""Native Lakebase sessions and OAuth-rotating Lakebase persistence; no SQLite."""
import asyncio
import hashlib
import json
import os
import re
from contextlib import asynccontextmanager
from uuid import uuid4

from databricks_ai_bridge.lakebase import LakebaseClient
from databricks_openai.agents import AsyncDatabricksSession


def scoped_session(owner, conversation):
    return hashlib.sha256(f'{owner}:{conversation}'.encode()).hexdigest()


from agent_server.approval_store import ApprovalPersistence


class LakebaseStore(ApprovalPersistence):
    def __init__(self, endpoint):
        self.schema = os.getenv('STORE_OPS_SCHEMA', 'store_ops')
        if not re.fullmatch(r'[a-z_][a-z0-9_]*', self.schema):
            raise ValueError('STORE_OPS_SCHEMA must be a simple SQL identifier')
        self.client = LakebaseClient(autoscaling_endpoint=endpoint)
        self.endpoint = endpoint

    def session(self, owner, conversation):
        return AsyncDatabricksSession(session_id=scoped_session(owner, conversation), autoscaling_endpoint=self.endpoint, schema=os.getenv('LAKEBASE_AGENT_MEMORY_SCHEMA'), create_tables=False)

    async def sql(self, query, params=()):
        query = query.replace('store_ops.', self.schema + '.')
        return await asyncio.to_thread(self.client.execute, query, params)

    @asynccontextmanager
    async def lock(self, session_id):
        context = self.client.pool.connection()
        connection = await asyncio.to_thread(context.__enter__)
        try:
            row = await asyncio.to_thread(lambda: connection.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired', (session_id,)).fetchone())
            if not row['acquired']:
                raise RuntimeError('Conversation already has an active turn; retry after it completes')
            try:
                yield
            finally:
                await asyncio.to_thread(connection.execute, 'SELECT pg_advisory_unlock(hashtextextended(%s,0))', (session_id,))
        finally:
            await asyncio.to_thread(context.__exit__, None, None, None)

    async def preferences(self, owner):
        return await self.sql('SELECT id,content FROM store_ops.memories WHERE owner_id=%s ORDER BY created_at LIMIT 30', (owner,))

    async def remember(self, owner, content, consent):
        if consent is not True:
            raise PermissionError('Explicit human consent is required')
        memory_id = uuid4().hex
        await self.sql('INSERT INTO store_ops.memories(id,owner_id,content) VALUES (%s,%s,%s)', (memory_id, owner, content))
        return {'memory_id': memory_id}

    async def forget(self, owner, memory_id):
        rows = await self.sql('DELETE FROM store_ops.memories WHERE id=%s AND owner_id=%s RETURNING id', (memory_id, owner))
        if not rows:
            raise PermissionError('Memory not found for this employee')
        return {'status': 'deleted'}

    def close(self):
        self.client.close()
