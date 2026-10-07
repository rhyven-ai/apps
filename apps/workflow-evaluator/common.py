# SPDX-License-Identifier: Apache-2.0
"""JSON action transport and collection-local immutable records."""
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import sqlite3
import sys
from datetime import datetime, timezone


class AppError(Exception):
    def __init__(self, message, code='INVALID_ARGUMENT'):
        super().__init__(message)
        self.code = code


def require(condition, message):
    if not condition:
        raise AppError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('Non-finite JSON value')
    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError('Non-finite JSON value')
        return parsed
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant, parse_float=finite_float)


def snapshot(files):
    require(isinstance(files, list) and len(files) <= 100, 'Supply at most 100 snapshot files')
    result = {}
    size = 0
    for item in files:
        require(isinstance(item, dict) and set(item) == {'path', 'content'}, 'Each file needs path and content')
        path, content = item['path'], item['content']
        require(isinstance(path, str) and 0 < len(path) <= 200, 'Invalid file path')
        pure = PurePosixPath(path)
        require(not pure.is_absolute() and str(pure) == path and '..' not in pure.parts
                and path != '.' and '\\' not in path and '\x00' not in path, 'Use normalized relative POSIX paths')
        require(path not in result, 'Duplicate snapshot path')
        require(isinstance(content, str), 'File content must be text')
        size += len(content.encode())
        require(size <= 400_000, 'Snapshot exceeds 400 KB UTF-8')
        result[path] = content
    return result


class Store:
    def __init__(self, directory):
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(root/'quality.sqlite3', timeout=10)
        self.db.execute('CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(kind,id))')

    def put(self, kind, identifier, value):
        encoded = canonical(value)
        with self.db:
            old = self.db.execute('SELECT payload FROM records WHERE kind=? AND id=?', (kind, identifier)).fetchone()
            if old:
                require(old[0] == encoded, 'Immutable record already exists with different content')
            else:
                self.db.execute('INSERT INTO records VALUES (?,?,?,?)', (kind, identifier, encoded, datetime.now(timezone.utc).isoformat()))
        return value

    def get(self, kind, identifier):
        row = self.db.execute('SELECT payload FROM records WHERE kind=? AND id=?', (kind, identifier)).fetchone()
        if not row:
            raise AppError('Record not found in this app and collection', 'NOT_FOUND')
        return json.loads(row[0])

    def listing(self, kind, limit=20):
        require(type(limit) is int and 1 <= limit <= 100, 'Limit must be between 1 and 100')
        rows = self.db.execute('SELECT payload FROM records WHERE kind=? ORDER BY created_at DESC, id DESC LIMIT ?', (kind, limit))
        return {'items': [{key: value for key, value in json.loads(row[0]).items() if key not in {'checks', 'cases'}} for row in rows]}

    def close(self):
        self.db.close()


def serve(category, actions):
    store = None
    try:
        raw = sys.stdin.buffer.readline(1_048_577)
        require(len(raw) <= 1_048_576, 'Request exceeds 1 MiB')
        request = strict_json(raw.decode())
        require(isinstance(request, dict), 'Request must be an object')
        require(isinstance(request.get('args', {}), dict), 'Arguments must be an object')
        require(request.get('protocol') == 'rhyven.action/1' and request.get('category') == category, 'Unsupported action contract')
        function = request.get('function', '')
        require(function in actions, 'Unknown action')
        directory = os.environ.get('RHYVEN_DATA_DIR') or request.get('context', {}).get('data_dir')
        require(isinstance(directory, str) and bool(directory), 'RHYVEN_DATA_DIR is required')
        store = Store(directory)
        result = actions[function](store, request.get('args', {}))
        print(canonical({'result': result}))
    except AppError as error:
        print(canonical({'error': {'code': error.code, 'message': str(error)}}))
    except (ValueError, TypeError, KeyError, RecursionError):
        print(canonical({'error': {'code': 'INVALID_ARGUMENT', 'message': 'Invalid action input'}}))
    except (OSError, sqlite3.Error):
        print(canonical({'error': {'code': 'APP_ERROR', 'message': 'Unable to read or write collection state'}}))
    finally:
        if store:
            store.close()
