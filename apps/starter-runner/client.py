# SPDX-License-Identifier: Apache-2.0
"""Human terminal client for the optional Starter Runner; Rhyven stays generic."""
import argparse
import json
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description='Optional starter harness client. Existing agent users can skip it.')
    parser.add_argument('--rhyven', default='rhyven')
    parser.add_argument('--home')
    parser.add_argument('--collection', default='global')
    sub = parser.add_subparsers(dest='command', required=True)
    chat = sub.add_parser('chat', help='Start a goal and answer questions interactively')
    chat.add_argument('goal')
    for command in ('resume', 'status', 'cancel'):
        sub.add_parser(command).add_argument('run_id')
    sub.add_parser('questions', help='List pending user questions without invoking a model')
    answer = sub.add_parser('answer')
    answer.add_argument('question_id')
    answer.add_argument('text')
    args = parser.parse_args()
    base = [args.rhyven, '--collection', args.collection, '--actor', 'user']
    if args.home:
        base += ['--home', args.home]

    def call(category, function, values):
        body = json.dumps({'category': category, 'function': function, 'args': values})
        result = subprocess.run(base + ['call', 'rhyven_call', body], capture_output=True, text=True)
        if result.returncode:
            raise SystemExit(result.stderr.strip())
        return json.loads(result.stdout)

    def answer_question(identity, reply):
        question = call('rhyven/user-questions', 'object_question_get', {'id': identity})
        return call('rhyven/user-questions', 'action_answer', {'id': identity,
                    'expected_revision': question['revision'], 'answer': reply})

    if args.command == 'questions':
        print(json.dumps(call('rhyven/user-questions', 'object_question_query', {'filters': {'status': 'pending'}}), indent=2))
        return
    if args.command == 'answer':
        print(json.dumps(answer_question(args.question_id, args.text), indent=2))
        return
    initial = {'goal': args.goal} if args.command == 'chat' else {'run_id': args.run_id}
    run = call('rhyven/starter-runner', 'action_start' if args.command == 'chat' else 'action_' + args.command, initial)
    print(json.dumps(run, indent=2))
    if args.command in ('status', 'cancel'):
        return
    while run['status'] in ('queued', 'running', 'waiting'):
        if run['status'] == 'waiting':
            question = call('rhyven/user-questions', 'object_question_get', {'id': run['question_id']})['data']
            print('\n' + question['question'])
            for choice in question['choices']:
                print('  - ' + choice)
            try:
                reply = input('Your answer (blank leaves the run waiting): ').strip()
            except (EOFError, KeyboardInterrupt):
                return
            if not reply:
                return
            answer_question(run['question_id'], reply)
            run = call('rhyven/starter-runner', 'action_resume', {'run_id': run['run_id']})
        time.sleep(1)
        run = call('rhyven/starter-runner', 'action_status', {'run_id': run['run_id']})
    print(json.dumps(run, indent=2))


if __name__ == '__main__':
    main()
