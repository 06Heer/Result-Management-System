"""A tiny JSON-file backed data layer that replaces SQLAlchemy for this app.

Each "table" is a JSON array of plain dict records stored in its own file
under DATA_DIR. Records are loaded into memory, mutated through the model
wrapper classes in rdms.models, and written back to disk immediately
(read-modify-write, atomic via write-to-temp + rename) on every change.
"""
import json
import os
import tempfile
import threading

_lock = threading.RLock()

DATA_DIR = None  # set by init_store()

COLLECTIONS = [
    'users', 'student_profiles', 'departments', 'programs', 'courses',
    'results', 'attendance', 'announcements', 'audit_logs', 'exam_schedules',
    'learning_resources', 'resource_progress',
]


def init_store(data_dir):
    global DATA_DIR
    DATA_DIR = data_dir
    os.makedirs(DATA_DIR, exist_ok=True)
    for name in COLLECTIONS:
        path = _path(name)
        if not os.path.exists(path):
            _atomic_write(path, [])


def _path(name):
    return os.path.join(DATA_DIR, f'{name}.json')


def _atomic_write(path, data):
    dirn = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix='.tmp-', dir=dirn)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def load(name):
    with _lock:
        try:
            with open(_path(name)) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []


def save(name, rows):
    with _lock:
        _atomic_write(_path(name), rows)


def next_id(rows):
    return (max((r['id'] for r in rows), default=0)) + 1
