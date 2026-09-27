# SPDX-FileCopyrightText: 2026 Rhyven contributors
# SPDX-License-Identifier: Apache-2.0
"""Real installed-app acceptance. Run with Docker and a built image ID file.
python3 apps/repo-documentation-tool/tests/integration.py /path/to/rhyven /tmp/image.id
"""
import json
import os
import secrets
from pathlib import Path
import subprocess
import socket
import time
import urllib.request
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from repository_client import AgentClient, import_files

binary=str(Path(sys.argv[1]).resolve())
image=Path(sys.argv[2]).read_text().strip()
source=Path(__file__).resolve().parents[1]

def log(text): print(text,flush=True)

with tempfile.TemporaryDirectory(prefix='code-atlas-acceptance-') as temp:
    home=Path(temp)
    def cli(*args,collection='global'):
        result=subprocess.run([binary,'--home',str(home),'--collection',collection,*args],capture_output=True,text=True,timeout=350)
        assert result.returncode==0,result.stderr
        return json.loads(result.stdout)
    bundle=home/'package.json'
    cli('app','package',str(source),'--image',image,'--out',str(bundle))
    log('Package built; running real container conformance')
    assert cli('app','test',str(bundle),'--allow-container')['passed']
    cli('install',str(bundle),'--accept-permissions')
    client=AgentClient(binary,str(home))
    def call(action,**args):return client.call(action,dict(repository='fixture',**args))
    def artifact(name):
        offset=0;out=''
        while True:
            part=call('read_artifact',name=name,offset=offset);out+=part['content'];offset=part['next_offset']
            if offset<0:return out
    try:
        tools=client.request('tools/list',{})['tools']
        assert [t['name'] for t in tools]==['rhyven_categories','rhyven_describe','rhyven_call']
        fixture=home/'fixture';(fixture/'src').mkdir(parents=True)
        (fixture/'src/model.py').write_text('def increment(value):\n    return value + 1\n\nclass Counter:\n    def count(self, value):\n        return increment(value)\n')
        (fixture/'src/main.py').write_text('from model import increment\n\ndef run():\n'+''.join('    increment(1)\n' for _ in range(110)))
        (fixture/'README.md').write_text('A fixture that increments integers; run calls increment 110 times.\n')
        assert import_files(client,'fixture',fixture)['imported']==3
        log('Imported through three-tool MCP; scanning Python')
        report=call('scan');assert report['complete'],report
        index=json.loads(artifact('structur.json'))
        symbols={s['qualified_name']:s for s in index['symbols']}
        assert set(symbols)=={'increment','Counter','Counter.count','run'},symbols.keys()
        assert symbols['increment']['start_line']==1 and symbols['Counter.count']['start_line']==5
        refs=symbols['increment']['references']
        assert len(refs)==100 and symbols['increment']['references_truncated'],symbols['increment']
        assert refs[0]['path']=='src/main.py' and refs[0]['line']==1,refs[:2]
        live=call('relations',symbol_id=symbols['increment']['id'])['symbol']
        assert len(live['references'])==100 and live['references_truncated']
        log('Real Pyright: all symbols, correct lines, references capped at 100, live refresh')
        premature=call('summary_context',id='main_flow')
        try:call('write_summary',id='main_flow',expected_hash=premature['hash'],summary='Premature')
        except RuntimeError as e: assert 'DEPENDENCIES_PENDING' in str(e),e
        else:raise AssertionError('Parent accepted before children')
        prose={
            'increment':'Returns the input value plus one; it has no persistent side effects.',
            'Counter':'Groups the count method, which delegates integer incrementing to increment.',
            'Counter.count':'Passes value to increment and returns the result without mutating the instance.',
            'run':'Calls increment with 1 one hundred ten times, discards each result, and implicitly returns None.',
            'src/model.py':'Defines increment and Counter.count, providing stateless increment operations.',
            'src/main.py':'Imports increment from model and defines a run entry point that repeatedly calls it.',
            'README.md':'Describes the increment fixture and the 110 calls made by run.',
            'src':'Contains the increment implementation and its repeated-call entry point.',
            '.':'Combines the README with the src implementation and entry point.',
            'repository':'Provides a small increment capability and a run function that exercises it repeatedly.',
            'Main flow':'When run is invoked, it calls model.increment(1) 110 times. Each call returns 2, and run discards these results. Counter.count offers a separate delegation path to increment.',
        }
        levels=[]
        while True:
            queue=call('summary_queue')
            if not queue['remaining']:break
            assert queue['items'],queue
            for item in queue['items']:
                context=call('summary_context',id=item['id'])
                assert context['ready']
                call('write_summary',id=item['id'],expected_hash=context['hash'],summary=prose[item['label']])
                levels.append(item['level'])
        assert levels[-1]=='main_flow' and levels.index('directory')>levels.index('symbol')
        rendered=artifact('ATLAS.md');assert 'Each call returns 2' in rendered and '*missing summary*' not in rendered
        index=json.loads(artifact('structur.json'));assert all(s['summary_status']=='fresh' for s in index['symbols'])
        log('Agent-written symbol → file → directory → subsystem → main flow summaries persisted')
        samples=home/'acceptance-artifacts';samples.mkdir()
        for name in ('ATLAS.md','structur.json','summaries.json'):(samples/name).write_text(artifact(name))
        # Export synthetic fixture artifacts only when a review path is requested.
        if os.environ.get('RHYVEN_TEST_ARTIFACTS'):
            review=Path(os.environ['RHYVEN_TEST_ARTIFACTS']);review.mkdir(parents=True,exist_ok=True)
            for p in samples.iterdir():(review/p.name).write_bytes(p.read_bytes())
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        token=secrets.token_urlsafe(32)
        server=subprocess.Popen([binary,'--home',str(home),'serve','--port',str(port)],env=dict(os.environ,RHYVEN_SERVE_TOKEN=token),stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            for _ in range(100):
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                except OSError:
                    assert server.poll() is None,server.stderr.read().decode()
                    time.sleep(.05)
            request=urllib.request.Request(f'http://127.0.0.1:{port}/categories/rhyven/repo-documentation-tool/functions/action_summary_queue',data=json.dumps({'repository':'fixture'}).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=60) as response:
                assert json.load(response)['remaining']==0
            log('REST and direct MCP access the same summaries')
        finally:
            server.terminate();server.wait(timeout=10)
        backup=home/'atlas.rhyven';cli('backup','global','--out',str(backup))
        cli('restore',str(backup),'--accept-permissions',collection='restored')
        restored=AgentClient(binary,str(home),'restored')
        try:assert restored.call('summary_queue',{'repository':'fixture'})['remaining']==0
        finally:restored.close()
        cli('remove','rhyven/repo-documentation-tool',collection='restored')
        cli('install',str(bundle),'--accept-permissions',collection='restored')
        restored=AgentClient(binary,str(home),'restored')
        try:assert restored.call('summary_queue',{'repository':'fixture'})['remaining']==0
        finally:restored.close()
        cli('install',str(bundle),'--accept-permissions',collection='isolated')
        other=AgentClient(binary,str(home),'isolated')
        try:assert other.call('survey',{'repository':'fixture'})['total_files']==0
        finally:other.close()
        call('put_files',files=[{'path':'src/model.py','content':'def replacement():\n    return 0\n'}])
        try:call('query')
        except RuntimeError as e:assert 'STALE_INDEX' in str(e),e
        else:raise AssertionError('Stale index accepted')
        log('Backup/restore, retained-state reinstall, collection isolation, and stale-source rejection passed')
        fixtures={
            'c':{'main.c':'int increment(int value) { return value + 1; }\nint main(void) { return increment(0); }\n'},
            'cpp':{'main.cpp':'class Counter { public: int count(int value) { return value + 1; } };\nint main() { Counter c; return c.count(0); }\n'},
            'fortran':{'main.f90':'module sample\ncontains\ninteger function increment(value)\ninteger, intent(in) :: value\nincrement = value + 1\nend function increment\nend module sample\n'},
            'go':{'go.mod':'module example.com/atlas\n\ngo 1.22\n','main.go':'package main\nfunc increment(v int) int { return v + 1 }\nfunc main() { increment(0) }\n'},
            'rust':{'Cargo.toml':'[package]\nname = "atlas_fixture"\nversion = "0.1.0"\nedition = "2021"\n','src/main.rs':'fn increment(value: i32) -> i32 { value + 1 }\nfn main() { increment(0); }\n'},
            'java':{'Hello.java':'public class Hello { public static int increment(int value) { return value + 1; } }\n'},
            'javascript':{'main.js':'function increment(value) { return value + 1; }\nclass Counter { count(value) { return increment(value); } }\n'},
            'typescript':{'main.ts':'function increment(value: number): number { return value + 1; }\nclass Counter { count(value: number): number { return increment(value); } }\n'},
        }
        for language,files in fixtures.items():
            log('Testing real '+language+' language server')
            client.call('put_files',{'repository':language,'files':[{'path':p,'content':c} for p,c in files.items()]})
            result=client.call('scan',{'repository':language})
            log(json.dumps(result))
            assert result['complete'] and result['symbols']>=1,(language,result)
        log('PASS: all eight additional language fixtures; installed app acceptance complete')
    finally:client.close()
