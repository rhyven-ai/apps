# SPDX-License-Identifier: Apache-2.0
"""Persist onboarding events and work leases; optionally notify a configured runner."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import urllib.request
from urllib.parse import urlsplit
import uuid
from rhyven_service import Service


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Monitor:
    def __init__(self, directory, clock=time.time):
        self.path = Path(directory) / 'onboarding.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.stopping = threading.Event()
        self.worker = None
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS customers(id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, id TEXT UNIQUE, fingerprint TEXT, body TEXT, owner TEXT DEFAULT '', token TEXT DEFAULT '', lease_until INTEGER DEFAULT 0, acknowledged INTEGER DEFAULT 0, attempts INTEGER DEFAULT 0, next_attempt INTEGER DEFAULT 0, notified INTEGER DEFAULT 0, notification_error TEXT DEFAULT '');
                CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1), paused INTEGER DEFAULT 0, last_error TEXT DEFAULT '');
                INSERT OR IGNORE INTO settings(id) VALUES(1);
                CREATE TABLE IF NOT EXISTS receipts(actor TEXT, request TEXT, fingerprint TEXT, result TEXT, PRIMARY KEY(actor,request));
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        return db

    @staticmethod
    def customer(db, identity):
        row = db.execute('SELECT body FROM customers WHERE id=?', (identity,)).fetchone()
        if not row:
            raise ValueError('Customer not found')
        return json.loads(row['body'])

    def event(self, db, identity, customer, kind, detail):
        fingerprint = hashlib.sha256(json.dumps([customer, kind, detail], sort_keys=True).encode()).hexdigest()
        old = db.execute('SELECT fingerprint FROM events WHERE id=?', (identity,)).fetchone()
        if old:
            if old[0] != fingerprint:
                raise ValueError('Event ID already used with different content')
            return False
        if db.execute('SELECT count(*) FROM events').fetchone()[0] >= 10000:
            raise ValueError('Event limit reached; archive this collection')
        event = dict(id=identity, customer_id=customer, kind=kind, detail=detail, created_at=int(self.clock()))
        db.execute('INSERT INTO events(id,fingerprint,body) VALUES(?,?,?)', (identity, fingerprint, json.dumps(event)))
        return True

    def call(self, action, args, context):
        actor = context.get('actor', 'agent')
        request = context.get('request_id')
        fingerprint = hashlib.sha256(json.dumps([action, args], sort_keys=True).encode()).hexdigest()
        now = int(self.clock())
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if request:
                old = db.execute('SELECT fingerprint,result FROM receipts WHERE actor=? AND request=?', (actor, request)).fetchone()
                if old:
                    if old[0] != fingerprint:
                        raise ValueError('request_id already used')
                    return json.loads(old[1])
            if action == 'health':
                result = dict(ok=True, paused=bool(db.execute('SELECT paused FROM settings').fetchone()[0]), webhook_configured=bool(os.environ.get('RHYVEN_SECRET_ONBOARDING_WEBHOOK') and os.environ.get('RHYVEN_SECRET_ONBOARDING_TOKEN')), last_error=db.execute('SELECT last_error FROM settings').fetchone()[0])
            elif action == 'open':
                identity = args['customer_id']
                if db.execute('SELECT 1 FROM customers WHERE id=?', (identity,)).fetchone():
                    raise ValueError('Customer already exists')
                if db.execute('SELECT count(*) FROM customers').fetchone()[0] >= 1000:
                    raise ValueError('At most 1,000 customers per collection')
                requirements = args['requirements']
                if not requirements or len(set(requirements)) != len(requirements):
                    raise ValueError('Requirements must be nonempty and unique')
                customer = dict(id=identity, requirements=[dict(name=n, status='missing', source='', note='') for n in requirements], deadline=args['deadline'], status='collecting', revision=1, questions=[], links=[])
                db.execute('INSERT INTO customers VALUES(?,?)', (identity, json.dumps(customer)))
                self.event(db, 'open:'+identity, identity, 'opened', '')
                result = {'customer': customer}
            elif action in ('get', 'ingest', 'review', 'handoff'):
                customer = self.customer(db, args['customer_id'])
                if action == 'ingest':
                    if customer['status'] == 'handed_off':
                        raise ValueError('Customer already handed off')
                    detail = json.dumps({'source': args['source'], 'requirement': args.get('requirement', ''), 'text': args.get('text', '')}, sort_keys=True)
                    requirement = args.get('requirement')
                    target = next((r for r in customer['requirements'] if r['name'] == requirement), None)
                    if requirement and not target:
                        raise ValueError('Unknown requirement')
                    added = self.event(db, args['event_id'], customer['id'], args['kind'], detail)
                    if added:
                        if target:
                            target.update(status='needs_review', source=args['source'], note='')
                        customer['revision'] += 1
                elif action in ('review', 'handoff'):
                    if args['expected_revision'] != customer['revision']:
                        raise ValueError('Revision changed; read the customer again')
                    if customer['status'] == 'handed_off':
                        raise ValueError('Customer already handed off')
                    if action == 'review':
                        target = next((r for r in customer['requirements'] if r['name'] == args['requirement']), None)
                        if not target:
                            raise ValueError('Unknown requirement')
                        if args['accepted'] and not target['source']:
                            raise ValueError('An accepted requirement needs a source event')
                        target.update(status='accepted' if args['accepted'] else 'missing', note=args['note'])
                        customer['questions'] = args.get('questions', [])
                        customer['links'] = args.get('links', [])
                    else:
                        if not all(r['status'] == 'accepted' for r in customer['requirements']) or customer['questions']:
                            raise ValueError('Requirements or questions remain open')
                        customer['status'] = 'handed_off'
                        customer['links'] = args.get('links', customer['links'])
                    customer['revision'] += 1
                    self.event(db, f"review:{customer['id']}:{customer['revision']}", customer['id'], action, args.get('note', ''))
                if action != 'get':
                    db.execute('UPDATE customers SET body=? WHERE id=?', (json.dumps(customer), customer['id']))
                result = {'customer': customer}
            elif action == 'pause':
                db.execute('UPDATE settings SET paused=?', (int(args['paused']),))
                result = {'paused': args['paused']}
            elif action == 'claim':
                if db.execute('SELECT paused FROM settings').fetchone()[0]:
                    result = {'items': []}
                else:
                    rows = db.execute('SELECT * FROM events WHERE acknowledged=0 AND lease_until<=? ORDER BY seq LIMIT ?', (now, args.get('limit', 10))).fetchall()
                    items = []
                    for row in rows:
                        token = uuid.uuid4().hex
                        until = now + args.get('lease_seconds', 60)
                        db.execute('UPDATE events SET owner=?,token=?,lease_until=? WHERE id=?', (actor, token, until, row['id']))
                        items.append(dict(event=json.loads(row['body']), lease_token=token, lease_until=until, notification_attempts=row['attempts'], notification_error=row['notification_error']))
                    result = {'items': items}
            elif action == 'acknowledge':
                row = db.execute('SELECT * FROM events WHERE id=?', (args['event_id'],)).fetchone()
                if not row or row['owner'] != actor or row['token'] != args['lease_token']:
                    raise ValueError('Lease belongs to another claim')
                if not row['acknowledged'] and row['lease_until'] <= now:
                    raise ValueError('Lease expired')
                db.execute('UPDATE events SET acknowledged=1 WHERE id=?', (args['event_id'],))
                result = {'acknowledged': True}
            else:
                raise ValueError('Unknown action')
            if request:
                db.execute('INSERT INTO receipts VALUES(?,?,?,?)', (actor, request, fingerprint, json.dumps(result)))
            return result

    def tick(self):
        now = int(self.clock())
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT paused FROM settings').fetchone()[0]:
                return
            for row in db.execute('SELECT body FROM customers'):
                customer = json.loads(row[0])
                if customer['status'] != 'handed_off' and customer['deadline'] <= now:
                    self.event(db, f"deadline:{customer['id']}:{customer['deadline']}", customer['id'], 'deadline', '')
        endpoint = os.environ.get('RHYVEN_SECRET_ONBOARDING_WEBHOOK', '')
        token = os.environ.get('RHYVEN_SECRET_ONBOARDING_TOKEN', '')
        if not endpoint or not token:
            return
        url = urlsplit(endpoint)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
            raise ValueError('Runner webhook requires an operator-configured HTTPS endpoint')
        # Secrets and endpoint are operator configuration, never event-controlled data.
        with self.connect() as db:
            row = db.execute('SELECT * FROM events WHERE acknowledged=0 AND notified=0 AND attempts<5 AND next_attempt<=? ORDER BY seq LIMIT 1', (now,)).fetchone()
        if not row:
            return
        event = json.loads(row['body'])
        body = json.dumps({k: event[k] for k in ('id', 'customer_id', 'kind')}).encode()
        request = urllib.request.Request(endpoint, data=body, headers={'Content-Type': 'application/json', 'Authorization': 'Bearer '+token, 'Idempotency-Key': event['id']}, method='POST')
        error = ''
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open(request, timeout=5) as response:
                if not 200 <= response.status < 300:
                    raise ValueError('Runner rejected notification')
        except Exception:
            # Do not record URLs, tokens or response bodies in customer-visible state.
            error = 'Runner notification failed; check operator configuration and runner logs'
        with self.connect() as db:
            db.execute('UPDATE events SET attempts=attempts+1,next_attempt=?,notified=?,notification_error=? WHERE id=?', (now + min(3600, 30 * 2**row['attempts']), int(not error), error, row['id']))

    def start(self, _service):
        def loop():
            while not self.stopping.wait(1):
                try:
                    self.tick()
                    with self.connect() as db:
                        db.execute("UPDATE settings SET last_error=''")
                except Exception:
                    # Keep inbox actions available; expose the failure without secret content.
                    with self.connect() as db:
                        db.execute("UPDATE settings SET last_error='Background check failed; inspect capacity and operator configuration'")
        self.worker = threading.Thread(target=loop, daemon=True)
        self.worker.start()

    def stop(self, _service):
        self.stopping.set()
        if self.worker:
            self.worker.join(timeout=6)


def main():
    monitor = Monitor(os.environ.get('RHYVEN_DATA_DIR', '/data'))
    names = ('health', 'open', 'get', 'ingest', 'review', 'handoff', 'pause', 'claim', 'acknowledge')
    actions = {'action_'+n: (lambda args, context, service, n=n: monitor.call(n, args, context)) for n in names}
    Service(actions, start=monitor.start, stop=monitor.stop).run()


if __name__ == '__main__':
    main()
