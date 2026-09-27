# SPDX-FileCopyrightText: 2026 Rhyven contributors
# SPDX-License-Identifier: Apache-2.0
"""Durable local agent inboxes. No outbound network and no agent execution."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

from rhyven_service import Service

PAGE_BYTES = 400_000  # Leave room for the service and MCP response envelopes.


def bounded_page(items):
    result, size = [], 0
    for item in items:
        size += len(json.dumps(item).encode())
        if size > PAGE_BYTES:
            break
        result.append(item)
    return result


class Mailbox:
    def __init__(self, directory, clock=time.time):
        self.path = Path(directory) / 'messages.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS channels (
                    name TEXT PRIMARY KEY, description TEXT NOT NULL, created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS subscriptions (
                    channel TEXT NOT NULL REFERENCES channels(name), recipient TEXT NOT NULL,
                    PRIMARY KEY(channel, recipient));
                CREATE TABLE IF NOT EXISTS messages (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    sender TEXT NOT NULL, message_key TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    channel TEXT NOT NULL, recipient TEXT NOT NULL, body TEXT NOT NULL,
                    thread_id TEXT NOT NULL, links TEXT NOT NULL,
                    created_at INTEGER NOT NULL, available_at INTEGER NOT NULL,
                    UNIQUE(sender, message_key));
                CREATE TABLE IF NOT EXISTS deliveries (
                    message_id TEXT NOT NULL REFERENCES messages(id), recipient TEXT NOT NULL,
                    lease_token TEXT NOT NULL DEFAULT '', lease_until INTEGER NOT NULL DEFAULT 0,
                    acknowledged_at INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(message_id, recipient));
                CREATE INDEX IF NOT EXISTS inbox ON deliveries(recipient, acknowledged_at, lease_until);
                CREATE TABLE IF NOT EXISTS receipts (
                    actor TEXT NOT NULL, request TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    result TEXT NOT NULL, PRIMARY KEY(actor, request));
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        return db

    def call(self, action, args, context):
        actor = context['actor']
        now = int(self.clock())
        request = context.get('request_id')
        fingerprint = self.fingerprint([action, args])
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            if request:
                old = db.execute('SELECT fingerprint,result FROM receipts WHERE actor=? AND request=?', (actor, request)).fetchone()
                if old:
                    if old['fingerprint'] != fingerprint:
                        raise ValueError('idempotency_conflict: request_id already used for different arguments')
                    return json.loads(old['result'])
            result = self.dispatch(db, action, args, actor, now)
            if request:
                db.execute('INSERT INTO receipts VALUES (?,?,?,?)', (actor, request, fingerprint, json.dumps(result)))
            db.commit()
            return result
        finally:
            db.close()

    @staticmethod
    def fingerprint(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    @staticmethod
    def message(row):
        return {**{key: row[key] for key in ('id', 'sender', 'channel', 'recipient', 'body', 'thread_id', 'created_at', 'available_at')},
                'links': json.loads(row['links'])}

    @staticmethod
    def channel(db, name):
        row = db.execute('SELECT * FROM channels WHERE name=?', (name,)).fetchone()
        if not row:
            raise ValueError('not_found: channel')
        return row

    def dispatch(self, db, action, args, actor, now):
        if action == 'health':
            return {'ok': db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'}
        if action == 'channel_create':
            name = args['channel']
            if not name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in name):
                raise ValueError('invalid_argument: channel must contain lowercase letters, digits, hyphens or underscores')
            old = db.execute('SELECT * FROM channels WHERE name=?', (name,)).fetchone()
            if old:
                if old['description'] != args['description']:
                    raise ValueError('conflict: channel exists with a different description')
                return dict(old)
            db.execute('INSERT INTO channels VALUES (?,?,?)', (name, args['description'], now))
            return dict(self.channel(db, name))
        if action == 'channels':
            rows = db.execute('SELECT * FROM channels ORDER BY name LIMIT ? OFFSET ?', (args['limit'], args['offset']))
            return {'items': [dict(row) for row in rows], 'total': db.execute('SELECT COUNT(*) FROM channels').fetchone()[0]}
        if action in ('subscribe', 'unsubscribe'):
            name = args['channel']
            self.channel(db, name)
            if action == 'subscribe':
                db.execute('INSERT OR IGNORE INTO subscriptions VALUES (?,?)', (name, actor))
            else:
                db.execute('DELETE FROM subscriptions WHERE channel=? AND recipient=?', (name, actor))
            return {'channel': name, 'recipient': actor, 'subscribed': action == 'subscribe'}
        if action in ('send', 'send_direct'):
            fingerprint = self.fingerprint([action, args])
            old = db.execute('SELECT * FROM messages WHERE sender=? AND message_key=?', (actor, args['message_key'])).fetchone()
            if old:
                if old['fingerprint'] != fingerprint:
                    raise ValueError('idempotency_conflict: message_key already used with different content')
                return self.message(old)
            channel, recipient = args.get('channel', ''), args.get('recipient', '')
            if action == 'send':
                self.channel(db, channel)
                recipients = [r[0] for r in db.execute('SELECT recipient FROM subscriptions WHERE channel=?', (channel,))]
                if len(recipients) > 1000:
                    raise ValueError('capacity: channel exceeds 1000 recipients')
            else:
                recipients = [recipient]
            identity = uuid.uuid4().hex
            thread_id = identity
            if args['reply_to']:
                parent = db.execute('SELECT * FROM messages WHERE id=?', (args['reply_to'],)).fetchone()
                if not parent or parent['channel'] != channel:
                    raise ValueError('not_found: reply target in this conversation')
                if not channel and {parent['sender'], parent['recipient']} != {actor, recipient}:
                    raise ValueError('invalid_argument: direct reply must have the same participants')
                thread_id = parent['thread_id']
            db.execute('INSERT INTO messages(id,sender,message_key,fingerprint,channel,recipient,body,thread_id,links,created_at,available_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (identity, actor, args['message_key'], fingerprint, channel, recipient, args['body'], thread_id, json.dumps(args['links']), now, args['available_at'] or now))
            db.executemany('INSERT INTO deliveries(message_id,recipient) VALUES (?,?)', [(identity, who) for who in recipients])
            return self.message(db.execute('SELECT * FROM messages WHERE id=?', (identity,)).fetchone())
        if action in ('inbox', 'claim'):
            clause = 'AND d.lease_until<=?' if action == 'claim' else ''
            parameters = [actor, now] + ([now] if action == 'claim' else []) + [args['limit']]
            rows = db.execute(f'''SELECT m.*, d.lease_until FROM deliveries d JOIN messages m ON m.id=d.message_id
                WHERE d.recipient=? AND d.acknowledged_at=0 AND m.available_at<=? {clause}
                ORDER BY m.seq LIMIT ?''', parameters).fetchall()
            items = []
            size = 0
            for row in rows:
                item = {'message': self.message(row), 'lease_until': row['lease_until']}
                if action == 'claim':
                    token = uuid.uuid4().hex
                    item.update(lease_token=token, lease_until=now + args['lease_seconds'])  # gitleaks:allow -- generated UUID, not a credential literal
                size += len(json.dumps(item).encode())
                if size > PAGE_BYTES:
                    break
                if action == 'claim':
                    db.execute('UPDATE deliveries SET lease_token=?,lease_until=? WHERE message_id=? AND recipient=?', (token, item['lease_until'], row['id'], actor))
                items.append(item)
            return {'recipient': actor, 'items': items}
        if action == 'acknowledge':
            row = db.execute('SELECT * FROM deliveries WHERE message_id=? AND recipient=?', (args['message_id'], actor)).fetchone()
            if not row or row['lease_token'] != args['lease_token']:
                raise ValueError('invalid_argument: lease token does not belong to this recipient/message')
            if row['acknowledged_at']:
                return {'message_id': args['message_id'], 'acknowledged_at': row['acknowledged_at']}
            if row['lease_until'] <= now:
                raise ValueError('lease_expired: claim again with a new request_id')
            db.execute('UPDATE deliveries SET acknowledged_at=? WHERE message_id=? AND recipient=?', (now, args['message_id'], actor))
            return {'message_id': args['message_id'], 'acknowledged_at': now}
        if action == 'history':
            self.channel(db, args['channel'])
            words = args['search'].casefold().split()
            db.create_function('search_words', 1, lambda body: all(word in body.casefold() for word in words))
            where = 'channel=? AND available_at<=? AND created_at>=? AND search_words(body)'
            params = (args['channel'], now, args['since'])
            total = db.execute('SELECT COUNT(*) FROM messages WHERE ' + where, params).fetchone()[0]
            rows = db.execute('SELECT * FROM messages WHERE ' + where + ' ORDER BY seq DESC LIMIT ? OFFSET ?', (*params, args['limit'], args['offset']))
            return {'items': bounded_page(self.message(row) for row in rows), 'total': total}
        if action == 'thread':
            parent = db.execute('SELECT * FROM messages WHERE id=? AND available_at<=?', (args['message_id'], now)).fetchone()
            if not parent:
                raise ValueError('not_found: message')
            if not parent['channel'] and actor not in (parent['sender'], parent['recipient']):
                raise ValueError('permission: caller is not a direct conversation participant')
            rows = db.execute('SELECT * FROM messages WHERE thread_id=? AND available_at<=? ORDER BY seq LIMIT ? OFFSET ?', (parent['thread_id'], now, args['limit'], args['offset']))
            return {'items': bounded_page(self.message(row) for row in rows)}
        raise ValueError('not_found: action')


def main():
    mailbox = Mailbox(os.environ.get('RHYVEN_DATA_DIR', '/data'))
    names = ('health', 'channel_create', 'channels', 'subscribe', 'unsubscribe', 'send', 'send_direct', 'inbox', 'claim', 'acknowledge', 'history', 'thread')
    actions = {'action_' + name: (lambda args, context, service, name=name: mailbox.call(name, args, context)) for name in names}
    Service(actions).run()


if __name__ == '__main__':
    main()
