# SPDX-FileCopyrightText: 2026 Rhyven contributors
# SPDX-License-Identifier: Apache-2.0
import concurrent.futures
import json
from pathlib import Path
import sys
import tempfile
import unittest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from main import Mailbox
MANIFEST = json.loads((APP / 'app.json').read_text())


def normalized(name, values):
    props = MANIFEST['actions'][name]['input']['properties']
    return {**{k: v['default'] for k, v in props.items() if 'default' in v}, **values}


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1_800_000_000
        self.mail = Mailbox(self.temp.name, lambda: self.now)

    def call(self, name, actor='alice', request=None, **args):
        return self.mail.call(name, normalized(name, args), {'actor': actor, 'request_id': request})

    def test_snapshot_subscription_schedule_history_threads_and_dates(self):
        self.call('channel_create', channel='release', description='Release work')
        self.call('subscribe', 'bob', channel='release')
        first = self.call('send', channel='release', body='Release RECOVERY plan', message_key='first')
        self.call('subscribe', 'carol', channel='release')
        self.assertEqual(self.call('inbox', 'carol')['items'], [])
        self.assertEqual(self.call('inbox', 'bob')['items'][0]['message']['id'], first['id'])
        later = self.call('send', channel='release', body='Future follow-up', message_key='later', reply_to=first['id'], available_at=self.now + 10)
        self.assertEqual(self.call('history', channel='release', search='recovery release')['total'], 1)
        self.assertEqual(len(self.call('thread', message_id=first['id'])['items']), 1)
        self.now += 10
        self.assertEqual(len(self.call('thread', message_id=first['id'])['items']), 2)
        self.assertEqual(self.call('history', channel='release', since=self.now)['total'], 0)  # since is creation, not delivery
        self.assertEqual(later['thread_id'], first['id'])
        self.call('unsubscribe', 'bob', channel='release')
        self.call('send', channel='release', body='Only Carol now', message_key='third')
        self.assertEqual(len(self.call('inbox', 'bob')['items']), 2)  # retained existing delivery
        self.assertEqual(len(self.call('inbox', 'carol')['items']), 2)

    def test_deduplication_survives_restart_and_conflicts_roll_back(self):
        msg = self.call('send_direct', recipient='bob', body='Inspect task', message_key='one', request='request-one')
        self.mail = Mailbox(self.temp.name, lambda: self.now)
        self.assertEqual(msg, self.call('send_direct', recipient='bob', body='Inspect task', message_key='one', request='request-one'))
        self.assertEqual(msg, self.call('send_direct', recipient='bob', body='Inspect task', message_key='one', request='new-transport-request'))
        with self.assertRaisesRegex(ValueError, 'idempotency_conflict'):
            self.call('send_direct', recipient='bob', body='Changed', message_key='one')
        self.assertEqual(len(self.call('inbox', 'bob')['items']), 1)

    def test_competing_claims_expiration_acknowledgement_and_actor_routing(self):
        msg = self.call('send_direct', recipient='bob', body='Process once logically', message_key='one')
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            claims = list(pool.map(lambda _: self.call('claim', 'bob', lease_seconds=10), range(2)))
        self.assertEqual(sorted(len(x['items']) for x in claims), [0, 1])
        lease = next(x['items'][0] for x in claims if x['items'])
        with self.assertRaises(ValueError):
            self.call('acknowledge', 'carol', message_id=msg['id'], lease_token=lease['lease_token'])
        self.now += 10
        with self.assertRaisesRegex(ValueError, 'lease_expired'):
            self.call('acknowledge', 'bob', message_id=msg['id'], lease_token=lease['lease_token'])
        renewed = self.call('claim', 'bob')['items'][0]
        self.assertNotEqual(lease['lease_token'], renewed['lease_token'])
        with self.assertRaises(ValueError):
            self.call('acknowledge', 'bob', message_id=msg['id'], lease_token=lease['lease_token'])
        done = self.call('acknowledge', 'bob', message_id=msg['id'], lease_token=renewed['lease_token'])
        self.assertEqual(done, self.call('acknowledge', 'bob', message_id=msg['id'], lease_token=renewed['lease_token']))
        self.assertEqual(self.call('inbox', 'bob')['items'], [])

    def test_failure_before_commit_does_not_publish_partial_messages(self):
        base = self.mail.dispatch
        def fail(db, action, args, actor, now):
            base(db, action, args, actor, now)
            raise RuntimeError('interrupted before commit')
        self.mail.dispatch = fail
        with self.assertRaises(RuntimeError):
            self.call('send_direct', recipient='bob', body='Uncommitted', message_key='one', request='one')
        self.mail = Mailbox(self.temp.name, lambda: self.now)
        self.assertEqual(self.call('inbox', 'bob')['items'], [])
        self.call('send_direct', recipient='bob', body='Uncommitted', message_key='one', request='one')
        self.assertEqual(len(self.call('inbox', 'bob')['items']), 1)

    def test_claim_retry_is_stable_and_new_poll_needs_new_request(self):
        msg = self.call('send_direct', recipient='bob', body='Durable lease', message_key='one')
        first = self.call('claim', 'bob', request='claim-one', lease_seconds=1)
        self.mail = Mailbox(self.temp.name, lambda: self.now)
        self.assertEqual(first, self.call('claim', 'bob', request='claim-one', lease_seconds=1))
        self.now += 1
        self.assertEqual(first, self.call('claim', 'bob', request='claim-one', lease_seconds=1))
        next_ = self.call('claim', 'bob', request='claim-two')['items'][0]
        self.assertEqual(next_['message']['id'], msg['id'])
        self.assertNotEqual(next_['lease_token'], first['items'][0]['lease_token'])

    def test_direct_threads_do_not_mix_conversations(self):
        msg = self.call('send_direct', recipient='bob', body='Question', message_key='one')
        reply = self.call('send_direct', 'bob', recipient='alice', body='Answer', message_key='two', reply_to=msg['id'])
        self.assertEqual(reply['thread_id'], msg['id'])
        self.assertEqual(len(self.call('thread', 'bob', message_id=reply['id'])['items']), 2)
        with self.assertRaises(ValueError):
            self.call('thread', 'carol', message_id=msg['id'])
        with self.assertRaises(ValueError):
            self.call('send_direct', recipient='carol', body='Wrong thread', message_key='three', reply_to=msg['id'])

    def test_large_unicode_pages_do_not_lease_messages_the_agent_cannot_receive(self):
        for index in range(12):
            self.call('send_direct', recipient='bob', body='📝' * 4000,
                      links=['🔗' * 512] * 16, message_key=str(index))
        first = self.call('claim', 'bob', limit=50)
        self.assertLess(len(json.dumps(first).encode()), 900_000)
        self.assertGreater(len(first['items']), 0)
        self.assertLess(len(first['items']), 12)
        pages = [first]
        for _ in range(12):
            page = self.call('claim', 'bob', limit=50)
            if not page['items']:
                break
            pages.append(page)
        ids = [item['message']['id'] for page in pages for item in page['items']]
        self.assertEqual(len(ids), 12)
        self.assertEqual(len(set(ids)), 12)


if __name__ == '__main__':
    unittest.main()
