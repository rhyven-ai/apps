# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('review_app',Path(__file__).parents[1]/'main.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class ReviewTests(unittest.TestCase):
    def test_harness_roundtrip_unknown_usage_retry_and_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            r=app.Reviews(directory,lambda:100)
            context={'actor':'lead','request_id':'start'}
            initial=r.call('start',{'question':'Cache parsed files?'},context)
            self.assertEqual(initial,r.call('start',{'question':'Cache parsed files?'},context))
            identity=initial['review']['id']
            args=dict(review_id=identity,task_id='1',approach='Hash the bytes',assumptions='Local files',tradeoffs='Extra read',checks='Change content',model='harness-selected')
            result=r.call('submit',args,{'actor':'reviewer'})
            self.assertFalse(result['review']['usage_reported'])
            with self.assertRaises(ValueError):r.call('submit',{**args,'approach':'Different'}, {})
            with self.assertRaises(ValueError):r.call('decide',dict(review_id=identity,selected_tasks=['2'],rationale='missing'),{})
            final=r.call('decide',dict(review_id=identity,selected_tasks=['1'],rationale='Test invalidation first'),{'actor':'lead'})
            self.assertEqual(final['review']['status'],'decided')
            self.assertEqual(final,app.Reviews(directory).call('get',{'review_id':identity},{}))
    def test_expiry_cancellation_and_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            r=app.Reviews(directory,lambda:1)
            identity=r.call('start',{'question':'q','timeout_seconds':30}, {})['review']['id']
            r.clock=lambda:40
            self.assertEqual(r.call('get',{'review_id':identity},{})['review']['status'],'expired')
            with self.assertRaises(ValueError):r.call('submit',{'review_id':identity},{})
            self.assertEqual(r.call('cancel',{'review_id':identity},{})['review']['status'],'cancelled')
