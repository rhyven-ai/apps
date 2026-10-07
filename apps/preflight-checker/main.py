# SPDX-License-Identifier: Apache-2.0
"""Bounded checks on supplied source snapshots. Never executes project code."""
import ast
import time
import uuid
from common import canonical, digest, require, serve, snapshot, strict_json


def save_policy(store, args):
    name, version, checks = args['name'], args['version'], args['checks']
    require(isinstance(name, str) and 0 < len(name) <= 80, 'Invalid policy name')
    require(isinstance(version, str) and 0 < len(version) <= 40, 'Invalid policy version')
    require(isinstance(checks, list) and 1 <= len(checks) <= 100, 'Supply 1–100 checks')
    seen = set()
    for check in checks:
        require(isinstance(check, dict), 'Invalid check')
        require(set(check) <= {'id', 'kind', 'path', 'text', 'keys', 'expected_json'}, 'Unknown check field')
        require(isinstance(check['id'], str) and 0 < len(check['id']) <= 80 and check['id'] not in seen, 'Check IDs must be unique')
        seen.add(check['id'])
        snapshot([{'path': check['path'], 'content': ''}])
        kind = check['kind']
        require(kind in {'exists', 'contains', 'not_contains', 'json_valid', 'json_equals', 'python_syntax'}, 'Unsupported check kind')
        extras = set(check)-{'id', 'kind', 'path'}
        if kind in {'contains', 'not_contains'}:
            require(extras == {'text'} and isinstance(check['text'], str) and 0 < len(check['text']) <= 4000, 'Text checks require nonempty text only')
        elif kind == 'json_equals':
            require(extras == {'keys', 'expected_json'}, 'JSON equality requires keys and expected_json')
            require(isinstance(check['keys'], list) and len(check['keys']) <= 16 and all(isinstance(k, str) and len(k) <= 100 for k in check['keys']), 'Invalid JSON key path')
            require(isinstance(check['expected_json'], str) and len(check['expected_json']) <= 4000, 'Expected JSON is too large')
            strict_json(check['expected_json'])
        else:
            require(not extras, 'This check kind accepts no extra fields')
    policy = {'name': name, 'version': version, 'checks': checks}
    policy_hash = digest(policy)
    # Bind a human-readable version to immutable contents, including across processes.
    store.put('policy-version', digest([name, version]), {'policy_hash': policy_hash})
    return store.put('policy', policy_hash, dict(policy, policy_hash=policy_hash))


def check_file(check, files):
    text = files.get(check['path'])
    if text is None:
        return False, 'Required file is missing'
    kind = check['kind']
    if kind == 'exists':
        return True, 'File exists'
    if kind in {'contains', 'not_contains'}:
        found = check['text'] in text
        passed = found if kind == 'contains' else not found
        return passed, 'Text condition matched' if passed else 'Text condition did not match'
    try:
        if kind == 'python_syntax':
            ast.parse(text, filename=check['path'])
            return True, 'Python syntax is valid; code was not executed'
        value = strict_json(text)
        if kind == 'json_valid':
            return True, 'JSON is valid'
        for key in check['keys']:
            if not isinstance(value, dict) or key not in value:
                return False, 'JSON key is missing'
            value = value[key]
        passed = canonical(value) == canonical(strict_json(check['expected_json']))
        return passed, 'JSON value matched' if passed else 'JSON value differs'
    except (ValueError, SyntaxError, RecursionError):
        return False, 'File syntax is invalid'


def run(store, args):
    policy = store.get('policy', args['policy_hash'])
    files = snapshot(args['files'])
    started = time.perf_counter_ns()
    checks = []
    for check in policy['checks']:
        passed, message = check_file(check, files)
        checks.append({'id': check['id'], 'path': check['path'], 'passed': passed, 'message': message})
    result = {'run_id': str(uuid.uuid4()), 'policy_hash': policy['policy_hash'],
              'policy_name': policy['name'], 'policy_version': policy['version'],
              'snapshot_hash': digest(files), 'passed': all(c['passed'] for c in checks),
              'checks': checks, 'failed_checks': [c['id'] for c in checks if not c['passed']],
              'duration_ms': (time.perf_counter_ns()-started)/1_000_000}
    return store.put('run', result['run_id'], result)


ACTIONS = {
    'action_save_policy': save_policy,
    'action_run': run,
    'action_get_policy': lambda store, args: store.get('policy', args['policy_hash']),
    'action_get_run': lambda store, args: store.get('run', args['run_id']),
    'action_list_policies': lambda store, args: store.listing('policy', args.get('limit', 20)),
    'action_list_runs': lambda store, args: store.listing('run', args.get('limit', 20)),
}
if __name__ == '__main__':
    serve('rhyven/preflight-checker', ACTIONS)
