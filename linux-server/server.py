"""Remote PC B relay. One inbound TCP port, distinct A and B bearer tokens.
All jobs are allowlisted. This component NEVER runs Windows commands.
"""
import json
import math
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
from sw_schema import validate_recipe
from pydantic import BaseModel, ConfigDict, Field

DB_PATH = Path(os.environ.get('HUB_DB', './jobs.sqlite3'))
A_TOKEN = os.environ.get('HUB_A_TOKEN', '')
B_TOKEN = os.environ.get('HUB_B_TOKEN', '')
if len(A_TOKEN) < 32 or len(B_TOKEN) < 32 or secrets.compare_digest(A_TOKEN, B_TOKEN):
    raise RuntimeError('Set independent HUB_A_TOKEN and HUB_B_TOKEN (minimum 32 characters each)')

VALID_OPERATIONS = {'ping', 'system_info', 'solidworks_status', 'create_blank_part', 'create_box', 'sw_recipe'}


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
        cols = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
        if "progress" not in cols:
            db.execute("ALTER TABLE jobs ADD COLUMN progress TEXT")
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
    diagnostics: dict[str, Any] | None = None


class JobProgress(BaseModel):
    model_config = ConfigDict(extra='forbid')
    stage: str = Field(min_length=1, max_length=64, pattern='^[a-z0-9_]+$')
    step: int | None = Field(default=None, ge=0, le=100)
    detail: str | None = Field(default=None, max_length=200)


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    recipe: dict[str, Any]


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
    elif payload.operation == 'create_box':
        params = payload.params
        required = {'name', 'length_mm', 'width_mm', 'height_mm'}
        if set(params) != required:
            raise HTTPException(400, 'create_box requires exactly name, length_mm, width_mm, height_mm')
        if not isinstance(params['name'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,50}', params['name']):
            raise HTTPException(400, 'Invalid part name')
        for key in ('length_mm', 'width_mm', 'height_mm'):
            value = params[key]
            if type(value) not in (int, float) or not math.isfinite(value) or not 1 <= value <= 500:
                raise HTTPException(400, f'{key} must be a finite number between 1 and 500 mm')
    elif payload.operation == 'sw_recipe':
        if set(payload.params) not in ({'recipe'}, {'recipe', 'revision_of'}):
            raise HTTPException(400, 'sw_recipe requires recipe and optional revision_of')
        if 'revision_of' in payload.params:
            try:
                uuid.UUID(payload.params['revision_of'])
            except (ValueError, TypeError, AttributeError):
                raise HTTPException(400, 'revision_of must be a UUID') from None
        if len(json.dumps(payload.params, ensure_ascii=False)) > 50000:
            raise HTTPException(413, 'Recipe too large')
        try:
            validate_recipe(payload.params['recipe'])
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
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
    stored_params = json.loads(row['params'])
    return {'job_id': row['id'], 'operation': row['operation'], 'status': row['status'],
            'result': json.loads(row['result']) if row['result'] else None,
            'progress': json.loads(row['progress']) if row['progress'] else None,
            'request': stored_params if row['operation'] == 'sw_recipe' else None,
            'created': row['created'], 'updated': row['updated']}


@app.post('/api/jobs/{job_id}/revise')
def revise_recipe(job_id: str, request: RevisionRequest,
                  authorization: str | None = Header(default=None)):
    """Submit a new validated recipe without modifying the original CAD output."""
    require_auth(authorization, A_TOKEN)
    with database() as db:
        parent = db.execute('SELECT operation,params,status FROM jobs WHERE id=?',
                            (job_id,)).fetchone()
    if not parent or parent['operation'] != 'sw_recipe':
        raise HTTPException(404, 'Source modeling job not found')
    if parent['status'] not in ('done', 'error', 'interrupted'):
        raise HTTPException(409, 'Source job is not finished')
    original = json.loads(parent['params'])['recipe']
    revised = request.recipe
    try:
        validate_recipe(revised)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if revised['doc_type'] != original['doc_type']:
        raise HTTPException(400, 'Cannot change doc_type during revision')
    if revised['name'] == original['name']:
        raise HTTPException(400, 'Revision requires a new output name')
    if len(json.dumps(revised, ensure_ascii=False)) > 50000:
        raise HTTPException(413, 'Recipe too large')
    return submit_job(JobRequest(operation='sw_recipe', params={
        'recipe': revised, 'revision_of': job_id
    }), authorization)


@app.post('/agent/jobs/{job_id}/progress')
def agent_progress(job_id: str, payload: JobProgress,
                   authorization: str | None = Header(default=None)):
    require_auth(authorization, B_TOKEN)
    with database() as db:
        cursor = db.execute(
            "UPDATE jobs SET progress=?, updated=? WHERE id=? AND status='running'",
            (json.dumps(payload.model_dump(), ensure_ascii=False), time.time(), job_id))
        if cursor.rowcount != 1:
            raise HTTPException(409, 'Job not running')
    return {'saved': True}


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
