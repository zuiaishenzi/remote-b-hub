"""Remote PC B relay. One inbound TCP port, distinct A and B bearer tokens.
All jobs are allowlisted. This component NEVER runs Windows commands.
"""
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

DB_PATH = Path(os.environ.get('HUB_DB', './jobs.sqlite3'))
A_TOKEN = os.environ.get('HUB_A_TOKEN', '')
B_TOKEN = os.environ.get('HUB_B_TOKEN', '')
if len(A_TOKEN) < 32 or len(B_TOKEN) < 32 or secrets.compare_digest(A_TOKEN, B_TOKEN):
    raise RuntimeError('Set independent HUB_A_TOKEN and HUB_B_TOKEN (minimum 32 characters each)')

VALID_OPERATIONS = {'ping', 'system_info', 'solidworks_status', 'create_blank_part'}


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH, timeout=10) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('''CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            operation TEXT NOT NULL,
            params TEXT NOT NULL,
            status TEXT NOT NULL,
            result TEXT,
            created REAL NOT NULL,
            updated REAL NOT NULL
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS heartbeat (
            agent_id TEXT PRIMARY KEY,
            last_seen REAL NOT NULL
        )''')
        # Never blindly retry interrupted CAD operations: they may have changed files.
        db.execute("UPDATE jobs SET status = 'interrupted', updated = ? WHERE status = 'running'", (time.time(),))
        db.commit()


@contextmanager
def database():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    finally:
        db.close()


def require_auth(provided: str | None, expected: str):
    prefix = 'Bearer '
    if not provided or not provided.startswith(prefix) or not secrets.compare_digest(provided[len(prefix):], expected):
        raise HTTPException(status_code=401, detail='Unauthorized')


class JobRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation: str
    params: dict[str, Any] = Field(default_factory=dict)


class JobResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ok: bool
    value: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


app = FastAPI(title='PC B Task Relay', docs_url=None, redoc_url=None, openapi_url=None)
init_db()


@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'pc-b-relay'}


@app.get('/api/status')
def api_status(authorization: str | None = Header(default=None)):
    require_auth(authorization, A_TOKEN)
    with database() as db:
        row = db.execute("SELECT last_seen FROM heartbeat WHERE agent_id='pc-b'").fetchone()
        queued = db.execute("SELECT count(*) AS n FROM jobs WHERE status='queued'").fetchone()['n']
    age = None if row is None else round(time.time() - row['last_seen'], 1)
    return {'agent': 'pc-b', 'online': age is not None and age < 45, 'last_seen_seconds_ago': age, 'queued_jobs': queued}


@app.post('/api/jobs')
def submit_job(payload: JobRequest, authorization: str | None = Header(default=None)):
    require_auth(authorization, A_TOKEN)
    if payload.operation not in VALID_OPERATIONS:
        raise HTTPException(400, 'Unsupported operation')
    if payload.operation == 'create_blank_part':
        if set(payload.params) != {'name'} or not isinstance(payload.params.get('name'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,50}', payload.params['name']):
            raise HTTPException(400, 'Provide name: 1-50 ASCII letters/digits/_/-')
    elif payload.params:
        raise HTTPException(400, 'This operation does not accept params')
    job_id = str(uuid.uuid4())
    now = time.time()
    with database() as db:
        waiting = db.execute("SELECT count(*) AS n FROM jobs WHERE status IN ('queued','running')").fetchone()['n']
        if waiting >= 40:
            raise HTTPException(429, 'Task queue is full')
        db.execute('INSERT INTO jobs (id,operation,params,status,result,created,updated) VALUES (?,?,?,?,?,?,?)',
                   (job_id, payload.operation, json.dumps(payload.params), 'queued', None, now, now))
    return {'job_id': job_id, 'status': 'queued'}


@app.get('/api/jobs/{job_id}')
def job_status(job_id: str, authorization: str | None = Header(default=None)):
    require_auth(authorization, A_TOKEN)
    with database() as db:
        row = db.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Unknown job')
    return {'job_id': row['id'], 'operation': row['operation'], 'status': row['status'],
            'result': json.loads(row['result']) if row['result'] else None,
            'created': row['created'], 'updated': row['updated']}


@app.get('/agent/next')
def agent_next(authorization: str | None = Header(default=None)):
    require_auth(authorization, B_TOKEN)
    with database() as db:
        db.execute('INSERT INTO heartbeat (agent_id,last_seen) VALUES (?,?) ON CONFLICT(agent_id) DO UPDATE SET last_seen=excluded.last_seen', ('pc-b',time.time()))
        db.execute('BEGIN IMMEDIATE') if not db.in_transaction else None
        job = db.execute("SELECT id,operation,params FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
        if job is not None:
            db.execute("UPDATE jobs SET status='running', updated=? WHERE id=? AND status='queued'", (time.time(), job['id']))
    if not job:
        return {'job': None}
    return {'job': {'job_id': job['id'], 'operation': job['operation'], 'params': json.loads(job['params'])}}


@app.post('/agent/jobs/{job_id}/result')
def agent_result(job_id: str, result: JobResult, authorization: str | None = Header(default=None)):
    require_auth(authorization, B_TOKEN)
    encoded = json.dumps(result.model_dump(), ensure_ascii=False, default=str)
    if len(encoded) > 65536:
        raise HTTPException(413, 'Result too large')
    with database() as db:
        cursor = db.execute('UPDATE jobs SET status=?,result=?,updated=? WHERE id=? AND status=?',
                            ('done' if result.ok else 'error', encoded, time.time(), job_id, 'running'))
        if cursor.rowcount != 1:
            raise HTTPException(409, 'Unknown or already completed job')
        db.execute('INSERT INTO heartbeat (agent_id,last_seen) VALUES (?,?) ON CONFLICT(agent_id) DO UPDATE SET last_seen=excluded.last_seen', ('pc-b',time.time()))
    return {'saved': True}
