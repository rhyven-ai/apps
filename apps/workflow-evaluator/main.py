# SPDX-License-Identifier: Apache-2.0
"""Compare agent-supplied observations against immutable, hash-bound fixtures."""
import math
import uuid
from common import canonical, digest, require, serve, snapshot


def save_suite(store, args):
    name, version, cases = args['name'], args['version'], args['cases']
    require(isinstance(name, str) and 0 < len(name) <= 80, 'Invalid suite name')
    require(isinstance(version, str) and 0 < len(version) <= 40, 'Invalid suite version')
    require(isinstance(cases, list) and 1 <= len(cases) <= 30, 'Supply 1–30 cases')
    seen, stored = set(), []
    for case in cases:
        require(set(case) == {'id', 'files', 'expected_pass'}, 'A case needs id, files and expected_pass')
        require(isinstance(case['id'], str) and 0 < len(case['id']) <= 80 and case['id'] not in seen, 'Case IDs must be unique')
        require(type(case['expected_pass']) is bool, 'expected_pass must be boolean')
        seen.add(case['id'])
        files = snapshot(case['files'])
        stored.append(dict(case, snapshot_hash=digest(files)))
    suite = {'name': name, 'version': version, 'cases': stored}
    require(len(canonical(suite).encode()) <= 600_000, 'Suite exceeds 600 KB UTF-8')
    suite_hash = digest(suite)
    store.put('suite-version', digest([name, version]), {'suite_hash': suite_hash})
    return store.put('suite', suite_hash, dict(suite, suite_hash=suite_hash))


def evaluate(store, args):
    suite = store.get('suite', args['suite_hash'])
    observations = args['observations']
    require(isinstance(observations, list) and len(observations) == len(suite['cases']), 'Provide exactly one observation per case')
    by_id = {}
    policies = set()
    durations, outcomes = [], []
    for observation in observations:
        require(set(observation) == {'case_id', 'report'}, 'Observation needs case_id and report')
        require(observation['case_id'] not in by_id, 'Duplicate case observation')
        report = observation['report']
        require(isinstance(report, dict) and type(report.get('passed')) is bool, 'Report needs a boolean passed field')
        require(isinstance(report.get('policy_hash'), str) and len(report['policy_hash']) == 64, 'Report needs policy_hash')
        duration = report.get('duration_ms')
        require(type(duration) in {int, float} and math.isfinite(duration) and duration >= 0, 'duration_ms must be finite and nonnegative')
        policies.add(report['policy_hash'])
        by_id[observation['case_id']] = report
    require(len(policies) == 1, 'Do not mix policy versions in one evaluation')
    require(set(by_id) == {c['id'] for c in suite['cases']}, 'Observations do not match suite case IDs')
    for case in suite['cases']:
        report = by_id[case['id']]
        require(report.get('snapshot_hash') == case['snapshot_hash'], 'Observation uses a different input snapshot')
        require(isinstance(report.get('run_id'), str) and bool(report['run_id']), 'Report needs its source run_id')
        durations.append(report['duration_ms'])
        outcomes.append({'case_id': case['id'], 'correct': report['passed'] == case['expected_pass'],
                         'expected_pass': case['expected_pass'], 'actual_pass': report['passed'],
                         'source_run_id': report['run_id']})
    correct = sum(case['correct'] for case in outcomes)
    result = {'evaluation_id': str(uuid.uuid4()), 'suite_hash': suite['suite_hash'],
              'policy_hash': next(iter(policies)), 'correct': correct, 'total': len(outcomes),
              'accuracy': correct/len(outcomes), 'total_check_ms': sum(durations), 'cases': outcomes}
    return store.put('evaluation', result['evaluation_id'], result)


def compare(store, args):
    before = store.get('evaluation', args['baseline_id'])
    after = store.get('evaluation', args['candidate_id'])
    require(before['suite_hash'] == after['suite_hash'], 'Compare evaluations from the same immutable suite')
    baseline = {case['case_id']: case['correct'] for case in before['cases']}
    improved = [c['case_id'] for c in after['cases'] if c['correct'] and not baseline[c['case_id']]]
    regressed = [c['case_id'] for c in after['cases'] if not c['correct'] and baseline[c['case_id']]]
    return {'suite_hash': before['suite_hash'], 'baseline_id': before['evaluation_id'],
            'candidate_id': after['evaluation_id'], 'baseline_correct': before['correct'],
            'candidate_correct': after['correct'], 'total': after['total'],
            'improved_cases': improved, 'regressed_cases': regressed,
            'improved_without_regressions': bool(improved) and not regressed,
            'check_time_delta_ms': after['total_check_ms']-before['total_check_ms'],
            'timing_note': 'Reported check time only; excludes process, model and transport time. A single run is not a speed benchmark.'}


ACTIONS = {
    'action_save_suite': save_suite,
    'action_get_suite': lambda store, args: store.get('suite', args['suite_hash']),
    'action_evaluate': evaluate,
    'action_compare': compare,
    'action_get_evaluation': lambda store, args: store.get('evaluation', args['evaluation_id']),
    'action_list_suites': lambda store, args: store.listing('suite', args.get('limit', 20)),
    'action_list_evaluations': lambda store, args: store.listing('evaluation', args.get('limit', 20)),
}
if __name__ == '__main__':
    serve('rhyven/workflow-evaluator', ACTIONS)
