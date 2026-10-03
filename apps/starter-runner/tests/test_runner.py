# SPDX-License-Identifier: Apache-2.0
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

APP=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(APP))
from main import Runner, Model, WORK, KNOWLEDGE, QUESTIONS


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.binary=os.environ.get('RHYVEN_TEST_BINARY',str(APP.parents[1]/'target/release/rhyven'))
        if not Path(self.binary).is_file():self.skipTest('Set RHYVEN_TEST_BINARY to a built runtime')
        repo=APP.parents[1]
        for package in [repo/'catalog/work-management.json',repo/'catalog/project-knowledge.json',repo/'apps/user-questions/app.json']:
            subprocess.run([self.binary,'--workspace',str(self.root/'state'),'install',str(package),'--accept-permissions'],check=True,stdout=subprocess.DEVNULL)
        self.decisions=[]
        self.calls=[]
        self.runner=Runner(self.root/'runner',self.peer,lambda context,timeout:(self.decisions.pop(0),100))

    def tearDown(self):self.temp.cleanup()

    def peer(self,category,function,args,actor='runner'):
        self.calls.append((category,function,args))
        out=subprocess.run([self.binary,'--workspace',str(self.root/'state'),'--actor',actor,'call','rhyven_call',json.dumps({'category':category,'function':function,'args':args})],capture_output=True,text=True)
        if out.returncode:raise RuntimeError(out.stderr)
        return json.loads(out.stdout)

    def start(self,**kwargs):
        return self.runner.action('start',dict(goal='Prepare a release note',**kwargs),{'actor':'user','request_id':'goal-one'})['run_id']

    def test_phase_question_answer_restart_and_knowledge(self):
        identity=self.start()
        self.decisions=[{'kind':'plan','phases':[{'title':'Find requirements','criteria':'Confirm audience'},{'title':'Write note','criteria':'Provide a note for the confirmed audience'}]},
                        {'kind':'ask','question':'Who is the audience?','choices':['Developers','Everyone']}]
        self.runner.tick();self.runner.tick()
        run=self.runner.runs[identity]
        self.assertEqual(run['status'],'waiting')
        question=self.peer(QUESTIONS,'object_question_get',{'id':run['question_id']})
        with self.assertRaises(RuntimeError):
            self.peer(QUESTIONS,'action_answer',{'id':question['id'],'expected_revision':question['revision'],'answer':'Forged'})
        self.peer(QUESTIONS,'action_answer',{'id':question['id'],'expected_revision':question['revision'],'answer':'Developers'},actor='user')
        self.runner=Runner(self.root/'runner',self.peer,lambda c,t:(self.decisions.pop(0),100))
        self.runner.action('resume',{'run_id':identity},{'actor':'user'})
        self.decisions=[{'kind':'complete_phase','summary':'Audience is developers','evidence':'User answer'}, {'kind':'complete_phase','summary':'Release note: use the shared interface to add apps.','evidence':'Draft provided for the requested audience'}]
        self.runner.tick();self.runner.tick()
        self.assertEqual(self.runner.runs[identity]['status'],'completed')
        for phase in self.runner.runs[identity]['phases']:
            self.assertEqual(self.peer(WORK,'object_task_get',{'id':phase['task_id']})['data']['status'],'done')
        self.assertEqual(self.peer(KNOWLEDGE,'object_note_query',{'filters':{'topic':identity}})['total'],2)

    def test_budget_cancellation_and_restart_pause(self):
        identity=self.start(max_steps=1)
        self.decisions=[{'kind':'plan','phases':[{'title':'Draft','criteria':'Write a draft'}]}]
        self.runner.tick();self.runner.tick()
        self.assertEqual(self.runner.runs[identity]['status'],'paused')
        with self.assertRaises(ValueError):self.runner.action('resume',{'run_id':identity},{'actor':'user'})
        self.runner.action('cancel',{'run_id':identity},{'actor':'user'})
        self.assertFalse(self.runner.tick())
        self.assertEqual(self.runner.runs[identity]['status'],'cancelled')

    def test_unknown_model_operation_cannot_call_tools(self):
        identity=self.start()
        self.decisions=[{'kind':'shell','command':'echo forbidden'}]
        self.runner.tick()
        self.assertEqual(self.runner.runs[identity]['status'],'failed')
        self.assertEqual([c[1] for c in self.calls],['object_project_create'])

    def test_question_expiry_revision_and_protected_fields(self):
        expired=self.peer(QUESTIONS,'action_ask',{'question':'Too late?', 'expires_at':1})
        with self.assertRaises(RuntimeError):
            self.peer(QUESTIONS,'action_answer',{'id':expired['id'],'expected_revision':expired['revision'],'answer':'yes'},actor='user')
        result=self.peer(QUESTIONS,'action_expire',{'id':expired['id'],'expected_revision':expired['revision']})
        self.assertEqual(result['data']['status'],'expired')
        question=self.peer(QUESTIONS,'action_ask',{'question':'Continue?'})
        with self.assertRaises(RuntimeError):
            self.peer(QUESTIONS,'object_question_update',{'id':question['id'],'expected_revision':question['revision'],'patch':{'answer':'forged'}})
        self.peer(QUESTIONS,'action_answer',{'id':question['id'],'expected_revision':question['revision'],'answer':'yes'},actor='user')
        with self.assertRaises(RuntimeError):
            self.peer(QUESTIONS,'action_answer',{'id':question['id'],'expected_revision':question['revision'],'answer':'no'},actor='user')

    def test_crash_replays_phase_completion_without_duplicates(self):
        identity=self.start()
        self.decisions=[{'kind':'plan','phases':[{'title':'First','criteria':'Draft'},{'title':'Second','criteria':'Review'}]},
                        {'kind':'complete_phase','summary':'Draft ready','evidence':'Draft provided'}]
        self.runner.tick()
        original=self.runner.peer
        crashed=False
        def fail_after_commit(category,function,args):
            nonlocal crashed
            result=original(category,function,args)
            if function=='action_assign' and args.get('request_id','').endswith('begin-1') and not crashed:
                crashed=True
                raise RuntimeError('Simulated process interruption after peer commit')
            return result
        self.runner.peer=fail_after_commit
        self.runner.tick()
        self.assertEqual(self.runner.runs[identity]['status'],'failed')
        self.runner=Runner(self.root/'runner',self.peer,lambda c,t:(self.decisions.pop(0),100))
        self.runner.action('resume',{'run_id':identity},{'actor':'user'})
        self.runner.tick()
        self.assertEqual(self.runner.runs[identity]['phase'],1)
        self.assertEqual(self.peer(KNOWLEDGE,'object_note_query',{'filters':{'topic':identity}})['total'],1)
        self.decisions=[{'kind':'complete_phase','summary':'Reviewed','evidence':'Review supplied'}]
        self.runner.tick()
        self.assertEqual(self.runner.runs[identity]['status'],'completed')
        self.assertEqual(self.peer(KNOWLEDGE,'object_note_query',{'filters':{'topic':identity}})['total'],2)

    def test_start_dedup_and_model_redirect_policy(self):
        identity=self.start()
        self.assertEqual(self.start(),identity)
        with self.assertRaises(ValueError):self.runner.action('start',{'goal':'different'},{'actor':'user','request_id':'goal-one'})
        for url in ['http://example.com/api','https://user:password@example.com/api','https://example.com/api?key=x']:
            with self.assertRaises(ValueError):Model({'endpoint':url,'model':'test'})
        Model({'endpoint':'http://127.0.0.1:9999/v1/chat/completions','model':'local'})


if __name__=='__main__':unittest.main()
