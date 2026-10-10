# SPDX-License-Identifier: Apache-2.0
"""Run the same regression tests against two supplied Python source snapshots."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from rhyven_service import Service


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def checked_files(files):
    result = {}
    if not 1 <= len(files) <= 128:
        raise ValueError('Supply 1..128 files per snapshot')
    for item in files:
        name, content = item['path'], item['content']
        path = PurePosixPath(name)
        if (path.is_absolute() or any(p in ('.', '..') for p in name.split('/')) or '\\' in name
                or not name or len(name) > 200 or name in result or len(content.encode()) > 65536
                or '.git' in path.parts or any(ord(c) < 32 for c in name)):
            raise ValueError('Invalid, duplicate or oversized source path')
        result[name] = content
    if sum(len(v.encode()) for v in result.values()) > 262144:
        raise ValueError('Snapshot exceeds 256 KiB')
    return result


def run_stage(directory, source, regression, selector, timeout, cancel):
    for name, content in {**source, **regression}.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    report = directory / '.verification.xml'
    log = directory / '.verification.log'
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(directory), 'TMPDIR': str(directory),
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}
    command = [sys.executable, str(Path(__file__).with_name('pytest_worker.py')), '-q', '--tb=short', '-c', '/dev/null',
               '--override-ini=addopts=', '--junitxml=' + str(report), *selector]
    started = time.monotonic()
    with log.open('wb') as output:
        process = subprocess.Popen(command, cwd=directory, env=env, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        interrupted = None
        while process.poll() is None:
            if cancel.is_set() or time.monotonic() - started >= timeout:
                interrupted = 'cancelled' if cancel.is_set() else 'timeout'
                break
            time.sleep(.05)
        # Kill descendants too, including test processes left behind after pytest exits.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    result = dict(status=interrupted or 'inconclusive', exit_code=process.returncode,
                  duration_ms=int((time.monotonic()-started)*1000), tests=0, failures=0, errors=0, skipped=0,
                  log=log.read_bytes()[:8000].decode('utf-8', errors='replace'))
    if interrupted:
        return result
    try:
        if report.stat().st_size > 1024 * 1024:
            raise ValueError('Oversized test report')
        xml = report.read_bytes()
        if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
            raise ValueError('Unsafe test report')
        root = ET.fromstring(xml)
        cases = root.findall('.//testcase')
        failures = root.findall('.//testcase/failure')
        errors = root.findall('.//testcase/error')
        skipped = root.findall('.//testcase/skipped')
        result.update(tests=len(cases), failures=len(failures), errors=len(errors), skipped=len(skipped))
        if process.returncode == 0 and cases and not failures and not errors and not skipped:
            result['status'] = 'passed'
        elif process.returncode == 1 and failures and not errors and not skipped and all('AssertionError' in (f.text or '') or 'assert ' in (f.text or '') for f in failures):
            result['status'] = 'assertion_failed'
        else:
            result['status'] = 'setup_or_test_error'
    except (OSError, ET.ParseError, ValueError):
        result['status'] = 'setup_or_test_error'
    return result


def compare(inputs, directory, cancel):
    baseline, candidate, regression = (checked_files(inputs[k]) for k in ('baseline', 'candidate', 'regression'))
    if set(regression) & (set(baseline) | set(candidate)):
        raise ValueError('Regression files must not overwrite snapshot files')
    if not all(name.endswith('.py') and Path(name).name.startswith('test_') for name in regression):
        raise ValueError('Regression inputs must be test_*.py files')
    timeout = inputs.get('timeout_seconds', 15)
    if not 1 <= timeout <= 30:
        raise ValueError('Stage timeout must be 1..30 seconds')
    hashes = {key: sha(inputs[key]) for key in ('baseline', 'candidate', 'regression')}
    report = dict(hashes=hashes, environment=dict(python=platform.python_version(), pytest=__import__('pytest').__version__, platform=platform.machine()), stages=[], outcome='inconclusive')
    for label, source, tests, selector in [('baseline', baseline, regression, sorted(regression)),
                                          ('candidate', candidate, regression, sorted(regression)),
                                          ('suite', candidate, {}, ['.'])]:
        if cancel.is_set():
            report['outcome'] = 'cancelled'
            break
        with tempfile.TemporaryDirectory(prefix=label+'-', dir=directory) as work:
            stage = run_stage(Path(work), source, tests, selector, timeout, cancel)
        stage['name'] = label
        report['stages'].append(stage)
        if stage['status'] in ('cancelled', 'timeout'):
            report['outcome'] = stage['status']
            break
    if len(report['stages']) == 3:
        before, after, suite = (s['status'] for s in report['stages'])
        if before == 'assertion_failed' and after == 'passed' and suite == 'passed':
            report['outcome'] = 'supplied_case_verified'
        elif before == 'passed':
            report['outcome'] = 'not_reproduced'
        elif after == 'assertion_failed' or suite == 'assertion_failed':
            report['outcome'] = 'candidate_failed'
    report['limits'] = 'Tests execute supplied code. Results are evidence for these inputs, not a proof of correctness or security. No dependencies are installed.'
    return report


class Verifier:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'verification.sqlite3'
        self.lock = threading.Lock()
        self.cancels = {}
        with self.connect() as db:
            db.executescript('PRAGMA journal_mode=WAL; CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE, status TEXT, inputs TEXT, report TEXT);')
            db.execute("UPDATE jobs SET status='interrupted' WHERE status='running'")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute('PRAGMA synchronous=FULL')
        return db

    def call(self, action, args, context):
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if action == 'prepare':
                for key in ('baseline', 'candidate', 'regression'):
                    checked_files(args[key])
                fingerprint = sha([args, platform.python_version(), __import__('pytest').__version__, hashlib.sha256(Path(__file__).read_bytes()).hexdigest()])
                row = db.execute('SELECT id FROM jobs WHERE fingerprint=?', (fingerprint,)).fetchone()
                if row:
                    identity = row[0]
                else:
                    if db.execute('SELECT count(*) FROM jobs').fetchone()[0] >= 100:
                        raise ValueError('At most 100 comparisons per collection')
                    identity = str(uuid.uuid4())
                    db.execute('INSERT INTO jobs VALUES(?,?,?,?,NULL)', (identity, fingerprint, 'prepared', json.dumps(args)))
            else:
                identity = args['run_id']
                row = db.execute('SELECT status,inputs FROM jobs WHERE id=?', (identity,)).fetchone()
                if not row:
                    raise ValueError('Run not found')
                if action == 'run':
                    if row[0] == 'running':
                        pass
                    elif row[0] not in ('prepared', 'interrupted'):
                        raise ValueError('Run already completed; use get to read it')
                    else:
                        if self.cancels:
                            raise ValueError('One active comparison at a time')
                        cancel = threading.Event()
                        self.cancels[identity] = cancel
                        db.execute("UPDATE jobs SET status='running' WHERE id=?", (identity,))
                        db.commit()
                        threading.Thread(target=self.work, args=(identity, json.loads(row[1]), cancel), daemon=True).start()
                elif action == 'cancel':
                    if identity in self.cancels:
                        self.cancels[identity].set()
                    elif row[0] in ('prepared', 'interrupted'):
                        db.execute("UPDATE jobs SET status='cancelled' WHERE id=?", (identity,))
                elif action != 'get':
                    raise ValueError('Unknown action')
            row = db.execute('SELECT fingerprint,status,report FROM jobs WHERE id=?', (identity,)).fetchone()
            return dict(run_id=identity, input_sha256=row[0], status=row[1], report=json.loads(row[2]) if row[2] else None)

    def work(self, identity, inputs, cancel):
        try:
            result = compare(inputs, self.directory, cancel)
        except Exception as error:
            result = {'outcome': 'inconclusive', 'error': str(error)}
        with self.lock, self.connect() as db:
            db.execute('UPDATE jobs SET status=?,report=? WHERE id=?', ('cancelled' if cancel.is_set() else 'completed', json.dumps(result), identity))
            self.cancels.pop(identity, None)

    def stop(self, _service):
        with self.lock:
            for cancel in self.cancels.values():
                cancel.set()


def main():
    verifier = Verifier(os.environ.get('RHYVEN_DATA_DIR', '/data'))
    actions = {'action_'+name: (lambda args, context, service, name=name: verifier.call(name, args, context)) for name in ('prepare', 'run', 'get', 'cancel')}
    Service(actions, stop=verifier.stop).run()


if __name__ == '__main__':
    main()
