# SPDX-FileCopyrightText: 2026 Rhyven contributors
# SPDX-License-Identifier: Apache-2.0
"""One Rhyven action per invocation. No custom MCP server, network API, or model key."""
import json
import os
import sys
from atlas import Atlas, AtlasError


def handle(request):
    if request.get('protocol') not in ('rhyven.container/1', 'rhyven.action/1'):
        raise AtlasError('INVALID_ARGUMENT','Unsupported execution protocol')
    args=request.get('args',{})
    app=Atlas(os.environ.get('RHYVEN_DATA_DIR','/data'),args.get('repository'))
    action=request.get('function','').removeprefix('action_')
    if action=='put_files': return app.put_files(args['files'],args.get('delete',[]))
    if action=='survey': return app.survey(args.get('offset',0),args.get('limit',100))
    if action=='scan': return app.scan(args.get('offset',0),args.get('limit',10),args.get('relationships',True))
    if action=='query': return app.query(args.get('text',''),args.get('offset',0),args.get('limit',20))
    if action=='read_file': return app.read_file(args['path'],args.get('offset',0),args.get('limit',100))
    if action=='read_symbol': return app.read_symbol(args['symbol_id'],args.get('offset',0),args.get('limit',100))
    if action=='relations': return app.live(args['symbol_id'])
    if action=='summary_queue': return app.queue(args.get('limit',20))
    if action=='summary_context': return app.context(args['id'],args.get('offset',0),args.get('limit',50))
    if action=='write_summary': return app.summarize(args['id'],args['expected_hash'],args['summary'])
    if action=='configure_subsystems': return app.configure(args['subsystems'])
    if action=='build_atlas': return app.export()
    if action=='read_artifact': return app.artifact(args['name'],args.get('offset',0),args.get('limit',60000))
    raise AtlasError('NOT_FOUND','Unknown action')


if __name__=='__main__':
    try:
        line=sys.stdin.buffer.readline(1000001)
        if len(line)>1000000: raise AtlasError('LIMIT_EXCEEDED','Request exceeds 1,000,000 bytes; import fewer files')
        result={'result':handle(json.loads(line))}
        encoded=json.dumps(result)
        if len(encoded.encode())>900000: raise AtlasError('LIMIT_EXCEEDED','Response too large; request a smaller page')
        print(encoded)
    except AtlasError as exc:
        print(json.dumps({'error':{'code':exc.code,'message':str(exc)}}))
    except Exception as exc:
        print(json.dumps({'error':{'code':'APP_ERROR','message':str(exc)[:500]}}))
