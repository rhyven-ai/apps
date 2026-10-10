# SPDX-License-Identifier: Apache-2.0
"""Store review tasks and proposals. The connected harness performs delegation."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
import uuid


class Reviews:
    def __init__(self, directory, clock=time.time):
        self.path = Path(directory) / 'reviews.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS receipts(actor TEXT, request TEXT, fingerprint TEXT, result TEXT, PRIMARY KEY(actor,request));
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute('PRAGMA synchronous=FULL')
        return db

    def call(self, action, args, context):
        fingerprint = hashlib.sha256(json.dumps([action, args], sort_keys=True).encode()).hexdigest()
        request = context.get('request_id')
        actor = context.get('actor', 'agent')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if request:
                old = db.execute('SELECT fingerprint,result FROM receipts WHERE actor=? AND request=?', (actor, request)).fetchone()
                if old:
                    if old[0] != fingerprint:
                        raise ValueError('request_id already used with different arguments')
                    return json.loads(old[1])
            now = int(self.clock())
            if action == 'start':
                if db.execute('SELECT count(*) FROM reviews').fetchone()[0] >= 1000:
                    raise ValueError('Review limit reached; archive this collection before starting more')
                perspectives = args.get('perspectives', ['simple approach', 'failure cases', 'reuse existing code'])
                if not 1 <= len(perspectives) <= 3 or len(set(perspectives)) != len(perspectives):
                    raise ValueError('Choose one to three distinct perspectives')
                review = dict(id=str(uuid.uuid4()), question=args['question'], context=args.get('context', ''),
                              constraints=args.get('constraints', ''), status='open', created_at=now,
                              deadline=now + args.get('timeout_seconds', 600),
                              max_output_tokens=args.get('max_output_tokens', 600),
                              tasks=[dict(id=str(i+1), perspective=p, status='pending', proposal=None) for i, p in enumerate(perspectives)],
                              decision=None, usage_reported=False, reported_input_tokens=0, reported_output_tokens=0)
                db.execute('INSERT INTO reviews VALUES(?,?)', (review['id'], json.dumps(review)))
            else:
                row = db.execute('SELECT body FROM reviews WHERE id=?', (args['review_id'],)).fetchone()
                if not row:
                    raise ValueError('Review not found')
                review = json.loads(row[0])
                if review['status'] == 'open' and now >= review['deadline']:
                    review['status'] = 'expired'
                if action == 'submit':
                    if review['status'] != 'open':
                        raise ValueError('Review is not open')
                    task = next((t for t in review['tasks'] if t['id'] == args['task_id']), None)
                    if not task:
                        raise ValueError('Task not found')
                    proposal = {k: args[k] for k in ('approach', 'assumptions', 'tradeoffs', 'checks', 'model')}
                    proposal.update(input_tokens=args.get('input_tokens'), output_tokens=args.get('output_tokens'), latency_ms=args.get('latency_ms'), submitted_by=actor)
                    if task['proposal'] is not None and task['proposal'] != proposal:
                        raise ValueError('Proposal already recorded; start a new review to revise it')
                    if proposal['output_tokens'] is not None and proposal['output_tokens'] > review['max_output_tokens']:
                        raise ValueError('Reported output exceeds task token budget')
                    task.update(status='submitted', proposal=proposal)
                    submitted = [t['proposal'] for t in review['tasks'] if t['proposal']]
                    review['usage_reported'] = len(submitted) == len(review['tasks']) and all(p['input_tokens'] is not None and p['output_tokens'] is not None for p in submitted)
                    review['reported_input_tokens'] = sum(p['input_tokens'] or 0 for p in submitted)
                    review['reported_output_tokens'] = sum(p['output_tokens'] or 0 for p in submitted)
                elif action == 'decide':
                    if review['status'] not in ('open', 'expired'):
                        raise ValueError('Review already closed')
                    selected = args.get('selected_tasks', [])
                    if any(not any(t['id'] == i and t['proposal'] for t in review['tasks']) for i in selected):
                        raise ValueError('Selected tasks must have submitted proposals')
                    review['decision'] = dict(selected_tasks=selected, rationale=args['rationale'], decided_by=actor, decided_at=now)
                    review['status'] = 'decided'
                elif action == 'cancel':
                    if review['status'] == 'decided':
                        raise ValueError('A decided review cannot be cancelled')
                    review['status'] = 'cancelled'
                elif action != 'get':
                    raise ValueError('Unknown action')
                db.execute('UPDATE reviews SET body=? WHERE id=?', (json.dumps(review), review['id']))
            result = {'review': review, 'delegation': 'calling_harness', 'usage_is_self_reported': True}
            if request:
                db.execute('INSERT INTO receipts VALUES(?,?,?,?)', (actor, request, fingerprint, json.dumps(result)))
            return result


if __name__ == '__main__':
    try:
        request = json.loads(sys.stdin.readline(1_048_577))
        context = request['context']
        result = Reviews(context['data_dir']).call(request['function'].removeprefix('action_'), request['args'], context)
        print(json.dumps({'result': result}))
    except Exception as error:
        print(json.dumps({'error': {'code': 'APP_ERROR', 'message': str(error)}}))
