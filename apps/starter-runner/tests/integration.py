# SPDX-License-Identifier: Apache-2.0
"""Real container/service acceptance with a deterministic model HTTP endpoint."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import threading
import time


class ModelFixture(BaseHTTPRequestHandler):
    calls = 0

    def log_message(self, *args):
        pass

    def do_POST(self):
        assert self.path == '/v1/chat/completions'
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        context = json.loads(body['messages'][-1]['content'])
        if not context['phases']:
            decision = {'kind': 'plan', 'phases': [{'title': 'Release note', 'criteria': 'Confirm audience and write a note'}]}
        elif not any('answer' in entry for entry in context['history']):
            decision = {'kind': 'ask', 'question': 'Who is this for?', 'choices': ['Developers', 'Everyone']}
        else:
            decision = {'kind': 'complete_phase', 'summary': 'Developers can extend an existing harness with Rhyven apps.', 'evidence': 'User selected Developers; note drafted here.'}
        type(self).calls += 1
        response = json.dumps({'choices': [{'message': {'content': json.dumps(decision)}}], 'usage': {'total_tokens': 100}}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def main():
    binary = str(Path(sys.argv[1]).resolve())
    image = Path(sys.argv[2]).read_text().strip()
    source = Path(__file__).resolve().parents[1]
    repo = source.parents[1]
    gateway = subprocess.check_output(['docker', 'network', 'inspect', 'bridge', '--format', '{{(index .IPAM.Config 0).Gateway}}'], text=True).strip()
    server = ThreadingHTTPServer(('0.0.0.0', 0), ModelFixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    environment = dict(os.environ, RHYVEN_SECRET_MODEL_CONFIG=json.dumps({
        'endpoint': f'http://{gateway}:{server.server_port}/v1/chat/completions', 'model': 'fixture'}))
    app = 'rhyven/starter-runner'
    with tempfile.TemporaryDirectory(prefix='rhyven-starter-') as directory:
        home = Path(directory)

        def cli(*args, collection='demo'):
            result = subprocess.run([binary, '--home', str(home), '--collection', collection,
                                     '--actor', 'user', *args], env=environment, capture_output=True, text=True, timeout=90)
            if result.returncode:
                raise RuntimeError(result.stderr)
            return json.loads(result.stdout)

        def call(category, function, args, **context):
            return cli('call', 'rhyven_call', json.dumps(dict(category=category, function=function, args=args)), **context)

        def wait(identity, desired):
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                run = call(app, 'action_status', {'run_id': identity})
                if run['status'] == desired:
                    return run
                assert run['status'] not in ('failed', 'paused', 'cancelled'), run
                time.sleep(.2)
            raise AssertionError(run)

        for package in (repo/'catalog/work-management.json', repo/'catalog/project-knowledge.json', repo/'apps/user-questions/app.json'):
            cli('install', str(package), '--accept-permissions')
        package = home/'starter.json'
        cli('app', 'package', str(source), '--image', image, '--out', str(package))
        cli('install', str(package), '--accept-permissions')
        cli('daemon', 'start')
        try:
            cli('service', 'start', app)
            run = call(app, 'action_start', {'goal': 'Draft a release note'})
            identity = run['run_id']
            run = wait(identity, 'waiting')
            question = call('rhyven/user-questions', 'object_question_get', {'id': run['question_id']})
            assert question['data']['asked_by'].startswith('_rhyven_service_')
            before = ModelFixture.calls
            time.sleep(.5)
            assert ModelFixture.calls == before, 'Waiting must not poll the model'
            cli('service', 'stop', app)
            cli('service', 'start', app)
            assert call(app, 'action_status', {'run_id': identity})['status'] == 'waiting'
            call('rhyven/user-questions', 'action_answer', {'id': question['id'], 'expected_revision': question['revision'], 'answer': 'Developers'})
            call(app, 'action_resume', {'run_id': identity})
            run = wait(identity, 'completed')
            assert ModelFixture.calls == 3
            task = call('rhyven/work-management', 'object_task_get', {'id': run['phases'][0]['task_id']})
            assert task['data']['status'] == 'done'
            assert call('rhyven/project-knowledge', 'object_note_query', {'filters': {'topic': identity}})['total'] == 1
            archive = home/'backup.rhyven'
            cli('backup', 'demo', '--out', str(archive))
            cli('restore', str(archive), '--accept-permissions', collection='restored')
            cli('service', 'start', app, collection='restored')
            assert call(app, 'action_status', {'run_id': identity}, collection='restored')['status'] == 'completed'
            cli('service', 'stop', app, collection='restored')
            cli('service', 'stop', app)
            print('PASS: container, model HTTP, restricted callbacks, human question, restart, completion and backup/restore')
        finally:
            cli('daemon', 'stop')
            # Stop acknowledges the request; wait for the supervisor to finish
            # its final state writes before removing the isolated test home.
            deadline = time.monotonic() + 15
            while (home/'supervisor/control.sock').exists():
                if time.monotonic() >= deadline:
                    raise AssertionError('Supervisor did not finish shutdown')
                time.sleep(.05)
            server.shutdown()
            thread.join()


if __name__ == '__main__':
    main()
