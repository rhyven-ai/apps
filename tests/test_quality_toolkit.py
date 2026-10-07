# SPDX-License-Identifier: Apache-2.0
"""Exercise real per-call processes and durable state, without Docker or models."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASE_CHECKS = [{'id':'readme','kind':'exists','path':'README.md'}, {'id':'config','kind':'exists','path':'config.json'}]
CASES = [
    {'id':'healthy','files':[{'path':'README.md','content':'# Sample\n'},{'path':'config.json','content':'{"enabled":true}'}],'expected_pass':True},
    {'id':'missing-readme','files':[{'path':'config.json','content':'{}'}],'expected_pass':False},
    {'id':'broken-json','files':[{'path':'README.md','content':'# Sample\n'},{'path':'config.json','content':'{broken'}],'expected_pass':False},
]


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def call(self, app, action, args, error=False, collection='one'):
        folder=self.root/collection/app
        request={'protocol':'rhyven.action/1','category':'rhyven/'+app,'function':'action_'+action,'args':args}
        result=subprocess.run([sys.executable,str(ROOT/'apps'/app/'main.py')],input=json.dumps(request)+'\n',capture_output=True,text=True,
                              env=dict(os.environ,RHYVEN_DATA_DIR=str(folder)),timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(result.stdout)
        self.assertIn('error' if error else 'result',value,value)
        return value.get('error' if error else 'result')

    def policy(self, version='1', checks=None):
        return self.call('preflight-checker','save_policy',{'name':'release','version':version,'checks':checks or BASE_CHECKS})

    def run_policy(self, policy, files):
        return self.call('preflight-checker','run',{'policy_hash':policy['policy_hash'],'files':files})

    def suite(self, version='1'):
        return self.call('workflow-evaluator','save_suite',{'name':'release','version':version,'cases':CASES})

    def evaluate(self, suite, policy):
        observations=[{'case_id':case['id'],'report':self.run_policy(policy,case['files'])} for case in suite['cases']]
        result=self.call('workflow-evaluator','evaluate',{'suite_hash':suite['suite_hash'],'observations':observations})
        return result, observations

    def test_improvement_and_second_process_handoff(self):
        suite=self.suite();baseline=self.policy()
        before,_=self.evaluate(suite,baseline)
        candidate=self.policy('2', BASE_CHECKS+[{'id':'json','kind':'json_valid','path':'config.json'}])
        after,_=self.evaluate(suite,candidate)
        comparison=self.call('workflow-evaluator','compare',{'baseline_id':before['evaluation_id'],'candidate_id':after['evaluation_id']})
        self.assertEqual((before['correct'],after['correct'],comparison['total']),(2,3,3))
        self.assertEqual(comparison['improved_cases'],['broken-json'])
        self.assertTrue(comparison['improved_without_regressions'])
        self.assertEqual(self.call('workflow-evaluator','get_evaluation',{'evaluation_id':after['evaluation_id']}),after)
        self.assertEqual(self.call('workflow-evaluator','get_evaluation',{'evaluation_id':after['evaluation_id']},error=True,collection='two')['code'],'NOT_FOUND')

    def test_new_failure_prevents_clean_improvement_claim(self):
        suite=self.suite();before,_=self.evaluate(suite,self.policy())
        candidate=self.policy('2',[{'id':'json','kind':'json_valid','path':'config.json'}])
        after,_=self.evaluate(suite,candidate)
        result=self.call('workflow-evaluator','compare',{'baseline_id':before['evaluation_id'],'candidate_id':after['evaluation_id']})
        self.assertFalse(result['improved_without_regressions'])
        self.assertEqual(result['regressed_cases'],['missing-readme'])

    def test_immutable_policy_and_suite_versions(self):
        first=self.policy();self.assertEqual(self.policy(),first)
        self.call('preflight-checker','save_policy',{'name':'release','version':'1','checks':BASE_CHECKS[:1]},error=True)
        self.suite()
        self.call('workflow-evaluator','save_suite',{'name':'release','version':'1','cases':CASES[:1]},error=True)
        self.assertEqual(self.call('preflight-checker','get_policy',{'policy_hash':first['policy_hash']}),first)

    def test_different_suites_cannot_be_compared(self):
        policy=self.policy();a,_=self.evaluate(self.suite('1'),policy);b,_=self.evaluate(self.suite('2'),policy)
        self.call('workflow-evaluator','compare',{'baseline_id':a['evaluation_id'],'candidate_id':b['evaluation_id']},error=True)

    def test_missing_duplicate_changed_and_mixed_observations_rejected(self):
        suite=self.suite();_,rows=self.evaluate(suite,self.policy())
        for invalid in [rows[:2],[rows[0],rows[0],rows[2]]]:
            self.call('workflow-evaluator','evaluate',{'suite_hash':suite['suite_hash'],'observations':invalid},error=True)
        for key,value in [('snapshot_hash','a'*64),('policy_hash','b'*64),('duration_ms',-1),('passed','yes'),('case_id','unknown')]:
            invalid=copy.deepcopy(rows)
            if key=='case_id':invalid[0][key]=value
            else:invalid[0]['report'][key]=value
            self.call('workflow-evaluator','evaluate',{'suite_hash':suite['suite_hash'],'observations':invalid},error=True)

    def test_all_check_types_and_no_source_execution(self):
        sentinel=self.root/'must-not-exist'
        checks=[{'id':'exists','kind':'exists','path':'a.py'},
                {'id':'contains','kind':'contains','path':'a.py','text':'pathlib'},
                {'id':'not_contains','kind':'not_contains','path':'a.py','text':'eval('},
                {'id':'syntax','kind':'python_syntax','path':'a.py'},
                {'id':'json','kind':'json_valid','path':'config.json'},
                {'id':'value','kind':'json_equals','path':'config.json','keys':['enabled'],'expected_json':'true'}]
        policy=self.policy(checks=checks)
        files=[{'path':'a.py','content':f'import pathlib\npathlib.Path({str(sentinel)!r}).touch()\n'}, {'path':'config.json','content':'{"enabled":true}'}]
        self.assertTrue(self.run_policy(policy,files)['passed']);self.assertFalse(sentinel.exists())
        files[1]['content']='{"enabled":1}'
        self.assertEqual(self.run_policy(policy,files)['failed_checks'],['value'])
        for content in ['{"x":1,"x":2}','{"x":NaN}','{"x":1e999}','{broken']:
            files[1]['content']=content
            self.assertIn('json',self.run_policy(policy,files)['failed_checks'])
        files[0]['content']='def broken('
        self.assertIn('syntax',self.run_policy(policy,files)['failed_checks'])

    def test_snapshot_paths_limits_and_empty_policies(self):
        policy=self.policy()
        for files in [[{'path':'../secret','content':'x'}],[{'path':'/secret','content':'x'}],[{'path':'./secret','content':'x'}],
                      [{'path':'a','content':'x'},{'path':'a','content':'y'}],[{'path':'a','content':'x'*400001}]]:
            self.call('preflight-checker','run',{'policy_hash':policy['policy_hash'],'files':files},error=True)
        self.call('preflight-checker','save_policy',{'name':'bad','version':'1','checks':[]},error=True)
        self.call('workflow-evaluator','save_suite',{'name':'bad','version':'1','cases':[]},error=True)

    def test_listing_summaries_do_not_dump_fixtures(self):
        self.policy();self.suite()
        self.assertNotIn('checks',self.call('preflight-checker','list_policies',{})['items'][0])
        self.assertNotIn('cases',self.call('workflow-evaluator','list_suites',{})['items'][0])
        self.call('preflight-checker','list_policies',{'limit':0},error=True)


if __name__=='__main__':
    unittest.main()
