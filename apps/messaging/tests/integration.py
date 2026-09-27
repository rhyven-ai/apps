# SPDX-FileCopyrightText: 2026 Rhyven contributors
# SPDX-License-Identifier: Apache-2.0
"""Standalone Docker acceptance using only the public Rhyven CLI contract.

python3 apps/messaging/tests/integration.py /path/to/rhyven /path/to/image.id
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    binary = str(Path(sys.argv[1]).resolve())
    image = Path(sys.argv[2]).read_text().strip()
    source = Path(__file__).resolve().parents[1]
    app = 'rhyven/messaging'
    with tempfile.TemporaryDirectory(prefix='rhyven-messaging-test-') as temporary:
        home = Path(temporary)

        def cli(*args, collection='demo', actor='lead'):
            result = subprocess.run(
                [binary, '--home', str(home), '--collection', collection,
                 '--actor', actor, *args], text=True, capture_output=True, timeout=180)
            if result.returncode:
                raise RuntimeError(result.stderr)
            return json.loads(result.stdout)

        def call(function, args, **context):
            return cli('call', 'rhyven_call', json.dumps({
                'category': app, 'function': 'action_' + function, 'args': args}), **context)

        package = home / 'messaging.json'
        cli('app', 'package', str(source), '--image', image, '--out', str(package))
        assert cli('app', 'test', str(package), '--allow-container')['passed']
        cli('install', str(package), '--accept-permissions')
        cli('daemon', 'start')
        try:
            cli('service', 'start', app)
            assert 'action_send_direct' in json.dumps(cli('call', 'rhyven_describe', json.dumps({'category': app})))
            first_args = {'recipient': 'worker', 'body': 'Review the example', 'message_key': 'example-1'}
            first = call('send_direct', first_args)
            assert call('send_direct', first_args) == first
            delivery = call('claim', {}, actor='worker')['items'][0]
            assert delivery['message']['id'] == first['id']
            assert call('claim', {}, actor='worker')['items'] == []
            call('acknowledge', {'message_id': first['id'], 'lease_token': delivery['lease_token']}, actor='worker')
            assert call('inbox', {}, actor='worker')['items'] == []
            pending = call('send_direct', {'recipient': 'worker', 'body': 'Continue later', 'message_key': 'example-2'})
            cli('service', 'stop', app)
            cli('service', 'start', app)
            assert call('inbox', {}, actor='worker')['items'][0]['message']['id'] == pending['id']
            archive = home / 'demo.rhyven'
            cli('backup', 'demo', '--out', str(archive))
            cli('restore', str(archive), '--accept-permissions', collection='restored')
            cli('service', 'start', app, collection='restored')
            assert call('inbox', {}, actor='worker', collection='restored')['items'][0]['message']['id'] == pending['id']
            cli('remove', app, collection='restored')
            cli('install', str(package), '--accept-permissions', collection='restored')
            cli('service', 'start', app, collection='restored')
            assert call('inbox', {}, actor='worker', collection='restored')['items'][0]['message']['id'] == pending['id']
            cli('service', 'stop', app, collection='restored')
            cli('service', 'stop', app)
            print('PASS: installed app, delivery, acknowledgement, deduplication, restart, backup/restore, retained reinstall')
        finally:
            cli('daemon', 'stop')


if __name__ == '__main__':
    main()
