#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reproduce the three-app workflow with real MCP calls, after human installation."""
import argparse
import json
from pathlib import Path
import selectors
import subprocess
import time

ROOT = Path(__file__).resolve().parent
APPS = ['preflight-checker', 'failure-to-regression', 'workflow-evaluator']
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--home', type=Path, required=True)
parser.add_argument('--evidence', type=Path, required=True)
parser.add_argument('--prepare', action='store_true', help='Publish packages locally and prepare human approval requests')
parser.add_argument('--packages', type=Path, help='Directory containing the three 0.1.0 packages')
options = parser.parse_args()
base = [str(options.binary.resolve()), '--home', str(options.home.resolve()), '--collection', 'quality-demo']
EVIDENCE = options.evidence.resolve()
EVIDENCE.mkdir(parents=True, exist_ok=True)
events = EVIDENCE / ('prepare-events.jsonl' if options.prepare else 'events.jsonl')
if events.exists():
    raise SystemExit('Evidence already exists; choose a new directory for another run')


def log(kind, **data):
    with events.open('a') as stream:
        stream.write(json.dumps({'time': time.time(), 'kind': kind, **data}) + '\n')


def save(name, value):
    (EVIDENCE / name).write_text(json.dumps(value, indent=2) + '\n')


def cli(*args):
    command = base + list(map(str, args))
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    log('cli', command=command, stdout=result.stdout, stderr=result.stderr, returncode=result.returncode)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


class MCP:
    def __init__(self, actor="quality-builder"):
        self.proc = subprocess.Popen(base + ["--actor", actor, "mcp"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.poller = selectors.DefaultSelector()
        self.poller.register(self.proc.stdout, selectors.EVENT_READ)
        self.seq = 0
        log("mcp_start", pid=self.proc.pid)
        self.request("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                     "clientInfo": {"name": "rhyven-demo-recorder", "version": "1"}})
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = self.request("tools/list", {})
        assert [t["name"] for t in tools["tools"]] == ["rhyven_categories", "rhyven_describe", "rhyven_call"]

    def send(self, message):
        log("mcp_send", message=message)
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params):
        self.seq += 1
        self.send({"jsonrpc": "2.0", "id": self.seq, "method": method, "params": params})
        if not self.poller.select(120):
            raise TimeoutError("MCP response timed out")
        response = json.loads(self.proc.stdout.readline())
        log("mcp_receive", message=response)
        assert response.get("id") == self.seq and "error" not in response, response
        return response["result"]

    def tool(self, name, arguments, allow_error=False):
        response = self.request("tools/call", {"name": name, "arguments": arguments})
        result = json.loads(response["content"][0]["text"])
        if response.get("isError") and not allow_error:
            raise RuntimeError(result)
        return result

    def call(self, category, function, args, **kwargs):
        return self.tool("rhyven_call", {"category": category, "function": function, "args": args}, **kwargs)

    def close(self):
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        log("mcp_stop", pid=self.proc.pid, returncode=self.proc.returncode)
        self.poller.close()


if options.prepare:
    if not options.packages:
        parser.error('--prepare needs --packages')
    cli('init')
    mcp = MCP()
    try:
        reviews = []
        for app in APPS:
            cli('app', 'publish', options.packages / (app+'-0.1.0.rhyven.json'))
            review = mcp.call('rhyven/marketplace', 'action_prepare_install', {'app':'rhyven/'+app})
            blocked = mcp.call('rhyven/marketplace', 'action_apply', {'request_id':review['request_id']}, allow_error=True)
            assert blocked['code'] == 'approval_required', blocked
            reviews.append(review)
        save('install-reviews.json', reviews)
        for review in reviews:
            print(' '.join(base + ['approve', review['request_id']]), flush=True)
    finally:
        mcp.close()
    raise SystemExit(0)

PREFLIGHT='rhyven/preflight-checker'
FAILURES='rhyven/failure-to-regression'
EVALUATOR='rhyven/workflow-evaluator'
checks=[{'id':'readme','kind':'exists','path':'README.md'}, {'id':'config','kind':'exists','path':'config.json'}]
cases=[
    {'id':'healthy','files':[{'path':'README.md','content':'# Sample\n'},{'path':'config.json','content':'{"enabled":true}'}],'expected_pass':True},
    {'id':'missing-readme','files':[{'path':'config.json','content':'{}'}],'expected_pass':False},
    {'id':'broken-json','files':[{'path':'README.md','content':'# Sample\n'},{'path':'config.json','content':'{broken'}],'expected_pass':False},
]
save('fixtures.json', cases)
mcp=MCP()
try:
    save('categories.json', mcp.tool('rhyven_categories', {}))
    for app in APPS:
        save(app+'-description.json', mcp.tool('rhyven_describe', {'category':'rhyven/'+app}))
    baseline=mcp.call(PREFLIGHT,'action_save_policy',{'name':'release','version':'1','checks':checks})
    missed=mcp.call(PREFLIGHT,'action_run',{'policy_hash':baseline['policy_hash'],'files':cases[2]['files']})
    assert missed['passed'] is True
    failure=mcp.call(FAILURES,'action_record_failure',{'title':'Broken JSON accepted','project':'sample-release',
        'symptom':'The release checker accepts malformed config.json','reproduction':'Supply config.json containing {broken and a README.md',
        'source_app':PREFLIGHT,'source_record_id':missed['run_id']})
    regression=mcp.call(FAILURES,'action_add_regression',{'failure_id':failure['id'],'case_id':cases[2]['id'],
        'files':cases[2]['files'],'expected_pass':False,'notes':'This must fail even when both required files exist.'})
    suite=mcp.call(EVALUATOR,'action_save_suite',{'name':'release','version':'1','cases':cases})
    def evaluate(policy):
        observations=[{'case_id':case['id'],'report':mcp.call(PREFLIGHT,'action_run',{'policy_hash':policy['policy_hash'],'files':case['files']})} for case in suite['cases']]
        return mcp.call(EVALUATOR,'action_evaluate',{'suite_hash':suite['suite_hash'],'observations':observations})
    before=evaluate(baseline)
    candidate=mcp.call(PREFLIGHT,'action_save_policy',{'name':'release','version':'2',
        'checks':checks+[{'id':'json','kind':'json_valid','path':'config.json'}]})
    after=evaluate(candidate)
    comparison=mcp.call(EVALUATOR,'action_compare',{'baseline_id':before['evaluation_id'],'candidate_id':after['evaluation_id']})
    assert (before['correct'],after['correct'],comparison['total'])==(2,3,3),comparison
    assert comparison['improved_without_regressions'] and comparison['regressed_cases']==[],comparison
    fixed=mcp.call(FAILURES,'action_mark_fixed',{'id':failure['id'],'expected_revision':failure['revision'],
        'fix_summary':'Policy version 2 validates JSON as well as requiring files.',
        'evaluation_id':after['evaluation_id'],'suite_hash':suite['suite_hash']})
    stale=mcp.call(FAILURES,'action_reopen',{'id':failure['id'],'expected_revision':failure['revision']},allow_error=True)
    assert 'code' in stale,stale
    for name,value in [('baseline-policy',baseline),('candidate-policy',candidate),('missed',missed),('failure',failure),
                       ('regression',regression),('suite',suite),('before',before),('after',after),('comparison',comparison),('fixed',fixed),('stale-revision',stale)]:
        save(name+'.json',value)
finally:
    mcp.close()
reader=MCP('quality-reviewer')
try:
    persisted=reader.call(EVALUATOR,'action_get_evaluation',{'evaluation_id':after['evaluation_id']})
    policy=reader.call(PREFLIGHT,'action_get_policy',{'policy_hash':candidate['policy_hash']})
    fixed_again=reader.call(FAILURES,'object_failure_get',{'id':failure['id']})
    repeated=reader.call(PREFLIGHT,'action_run',{'policy_hash':policy['policy_hash'],'files':cases[2]['files']})
    assert persisted==after and policy==candidate
    assert fixed_again['data']['status']=='fixed' and repeated['passed'] is False
    save('handoff.json',{'evaluation':persisted,'policy':policy,'failure':fixed_again,'repeated_check':repeated})
finally:
    reader.close()
save('summary.json',{'runtime':'0.5.5','collection':'quality-demo','apps':['rhyven/'+a for a in APPS],
    'baseline_correct':2,'candidate_correct':3,'cases':3,'regressions':0,'second_mcp_session_verified':True,
    'kind':'Prepared sample; real MCP calls; versioned policy improvement, not executable code modification',
    'suite_hash':suite['suite_hash']})
print('PASS: three apps, same fixtures, 2/3 to 3/3, no regressions, persisted handoff')
