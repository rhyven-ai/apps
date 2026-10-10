# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).parents[1]))
spec=importlib.util.spec_from_file_location('onboarding_app',Path(__file__).parents[1]/'main.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class MonitorTests(unittest.TestCase):
    def test_documents_are_not_approval_and_handoff_requires_review(self):
        with tempfile.TemporaryDirectory() as directory:
            r=app.Monitor(directory,lambda:100)
            r.call('open',dict(customer_id='demo',requirements=['contact'],deadline=200),{})
            data=dict(customer_id='demo',event_id='doc1',kind='document',source='file:123',requirement='contact')
            customer=r.call('ingest',data,{})['customer']
            self.assertEqual(customer['requirements'][0]['status'],'needs_review')
            self.assertEqual(customer,r.call('ingest',data,{})['customer'])
            with self.assertRaises(ValueError):r.call('ingest',{**data,'source':'different'},{})
            with self.assertRaises(ValueError):r.call('handoff',dict(customer_id='demo',expected_revision=2),{})
            customer=r.call('review',dict(customer_id='demo',expected_revision=2,requirement='contact',accepted=True,note='Confirmed source',questions=[]),{})['customer']
            with self.assertRaises(ValueError):r.call('review',dict(customer_id='demo',expected_revision=2),{})
            result=r.call('handoff',dict(customer_id='demo',expected_revision=customer['revision'],links=['task:1','knowledge:1']),{})
            self.assertEqual(result['customer']['status'],'handed_off')
            self.assertEqual(result,app.Monitor(directory).call('get',{'customer_id':'demo'},{}))
    def test_deadline_dedup_restart_leases_pause(self):
        with tempfile.TemporaryDirectory() as directory:
            r=app.Monitor(directory,lambda:100)
            r.call('open',dict(customer_id='demo',requirements=['contact'],deadline=99),{})
            r.tick();r.tick()
            claim=r.call('claim',{'lease_seconds':5},{'actor':'one'})['items']
            self.assertEqual(len(claim),2)
            self.assertEqual(r.call('claim',{}, {'actor':'two'})['items'],[])
            r=app.Monitor(directory,lambda:106)
            reclaimed=r.call('claim',{}, {'actor':'two'})['items']
            with self.assertRaises(ValueError):r.call('acknowledge',dict(event_id=claim[0]['event']['id'],lease_token=claim[0]['lease_token']),{'actor':'one'})
            for item in reclaimed:r.call('acknowledge',dict(event_id=item['event']['id'],lease_token=item['lease_token']),{'actor':'two'})
            r.call('pause',{'paused':True},{})
            self.assertEqual(r.call('claim',{}, {})['items'],[])
            r.call('pause',{'paused':False},{})
            r.tick()
            self.assertEqual(r.call('claim',{}, {})['items'],[])
    def test_webhook_failure_keeps_inbox_and_retries_without_leaking_secrets(self):
        from unittest.mock import patch, Mock
        with tempfile.TemporaryDirectory() as directory:
            r=app.Monitor(directory,lambda:100)
            r.call('open',dict(customer_id='demo',requirements=['contact'],deadline=200),{})
            opener=Mock();opener.open.side_effect=RuntimeError('secret should never be stored')
            with patch.dict(app.os.environ,{'RHYVEN_SECRET_ONBOARDING_WEBHOOK':'https://runner.example.test/events','RHYVEN_SECRET_ONBOARDING_TOKEN':'test-token'}), patch.object(app.urllib.request,'build_opener',return_value=opener):
                r.tick();r.tick()
                self.assertEqual(opener.open.call_count,1)
                request=opener.open.call_args[0][0]
                self.assertEqual(request.get_header('Authorization'),'Bearer test-token')
                self.assertNotIn(b'detail',request.data)
            items=r.call('claim',{}, {})['items']
            self.assertEqual(len(items),1)
            self.assertEqual(items[0]['notification_attempts'],1)
            self.assertNotIn('secret',items[0]['notification_error'])
