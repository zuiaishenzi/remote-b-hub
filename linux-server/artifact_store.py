"""Authenticated screenshot attachments on disk; no image bytes in job JSON."""
import hashlib
import io
import os
from pathlib import Path
import secrets
import sqlite3
import time
from contextlib import contextmanager

from PIL import Image

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_STORE_BYTES = 256 * 1024 * 1024
TTL_SECONDS = 48 * 3600


class ArtifactStore:
    def __init__(self, db_path, directory):
        self.db_path = str(db_path)
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL, content_type TEXT NOT NULL,
                bytes INTEGER NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
                sha256 TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL)''')
        self.cleanup()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def path(self, artifact_id):
        if len(artifact_id) != 48 or any(c not in '0123456789abcdef' for c in artifact_id):
            raise ValueError('Invalid artifact id')
        return self.directory / (artifact_id + '.image')

    def cleanup(self):
        with self.connect() as db:
            expired = db.execute('SELECT id FROM artifacts WHERE expires <= ?', (time.time(),)).fetchall()
            for row in expired:
                self.path(row['id']).unlink(missing_ok=True)
            db.execute('DELETE FROM artifacts WHERE expires <= ?', (time.time(),))
        # A crash between writing a file and committing its index can leave orphans.
        cutoff = time.time() - TTL_SECONDS
        for path in self.directory.glob('*.image'):
            if path.stat().st_mtime <= cutoff:
                path.unlink(missing_ok=True)

    def put(self, job_id, content_type, content):
        if len(content) > MAX_IMAGE_BYTES:
            raise ValueError('Screenshot exceeds 5 MiB')
        if content_type not in ('image/png', 'image/jpeg'):
            raise ValueError('Only PNG and JPEG are accepted')
        with Image.open(io.BytesIO(content)) as picture:
            expected = 'PNG' if content_type == 'image/png' else 'JPEG'
            if picture.format != expected or picture.width * picture.height > 20_000_000:
                raise ValueError('Invalid screenshot format or dimensions')
            width, height = picture.size
            picture.verify()
        self.cleanup()
        identity = secrets.token_hex(24)
        now = time.time()
        row = dict(id=identity, job_id=job_id, content_type=content_type, bytes=len(content),
                   width=width, height=height, sha256=hashlib.sha256(content).hexdigest(),
                   created=now, expires=now + TTL_SECONDS)
        path = self.path(identity)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT count(*) FROM artifacts WHERE job_id=?', (job_id,)).fetchone()[0] >= 3:
                raise ValueError('At most three screenshot attachments per job')
            total = db.execute('SELECT coalesce(sum(bytes),0) FROM artifacts').fetchone()[0]
            if total + len(content) > MAX_STORE_BYTES:
                raise ValueError('Artifact store quota exceeded')
            try:
                with path.open('xb') as stream:
                    stream.write(content)
                os.chmod(path, 0o600)
                db.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?,?,?,?)', tuple(row.values()))
                db.commit()
            except Exception:
                path.unlink(missing_ok=True)
                raise
        return row

    def list(self, job_id):
        self.cleanup()
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM artifacts WHERE job_id=? ORDER BY created', (job_id,))]

    def get(self, identity):
        self.path(identity)  # Validate before accessing disk or querying.
        self.cleanup()
        with self.connect() as db:
            row = db.execute('SELECT * FROM artifacts WHERE id=?', (identity,)).fetchone()
        if row is None or not self.path(identity).is_file():
            raise FileNotFoundError('Screenshot expired or not found')
        return dict(row), self.path(identity)
