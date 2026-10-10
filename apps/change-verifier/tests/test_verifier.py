# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
sys.path.insert(0,str(Path(__file__).parents[1]))
spec=importlib.util.spec_from_file_location('verifier_app',Path(__file__).parents[1]/'main.py')
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

def files(code,existing='from calc import add\ndef test_existing(): assert add(0, 0) == 0\n'):
    return [{'path':'calc.py','content':code},{'path':'test_existing.py','content':existing}]
def inputs():
    return dict(baseline=files('def add(a,b): return a-b\n'),candidate=files('def add(a,b): return a+b\n'),regression=[{'path':'test_regression.py','content':'from calc import add\ndef test_bug(): assert add(1,2) == 3\n'}],timeout_seconds=5)

class VerifierTests(unittest.TestCase):
    def test_real_bug_fix_and_non_reproduction(self):
        with tempfile.TemporaryDirectory() as directory:
            result=app.compare(inputs(),directory,threading.Event())
            self.assertEqual(result['outcome'],'supplied_case_verified',result)
            changed=inputs();changed['baseline']=changed['candidate']
            self.assertEqual(app.compare(changed,directory,threading.Event())['outcome'],'not_reproduced')
    def test_setup_error_regression_and_timeout_are_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            data=inputs();data['regression'][0]['content']='import missing_test_dependency\n'
            self.assertEqual(app.compare(data,directory,threading.Event())['outcome'],'inconclusive')
            data=inputs();data['candidate']=files('def add(a,b): return 3\n')
            self.assertEqual(app.compare(data,directory,threading.Event())['outcome'],'candidate_failed')
            data=inputs();data['timeout_seconds']=1;data['regression'][0]['content']='import time\ndef test_wait(): time.sleep(10)\n'
            self.assertEqual(app.compare(data,directory,threading.Event())['outcome'],'timeout')
    def test_paths_durable_jobs_cancel_and_changed_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):app.checked_files([{'path':'../escape','content':'x'}])
            r=app.Verifier(directory);first=r.call('prepare',inputs(),{})
            self.assertEqual(first,r.call('prepare',inputs(),{}))
            data=inputs();data['baseline'][0]['content']+='\n# changed\n'
            self.assertNotEqual(first['run_id'],r.call('prepare',data,{})['run_id'])
            r.call('run',{'run_id':first['run_id']},{})
            for _ in range(200):
                result=r.call('get',{'run_id':first['run_id']},{})
                if result['status']!='running':break
                time.sleep(.05)
            self.assertEqual(result['report']['outcome'],'supplied_case_verified',result)
            self.assertEqual(result,app.Verifier(directory).call('get',{'run_id':first['run_id']},{}))
            next_run=r.call('prepare',data,{})
            self.assertEqual(r.call('cancel',{'run_id':next_run['run_id']},{})['status'],'cancelled')
