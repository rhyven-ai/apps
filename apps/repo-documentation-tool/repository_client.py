#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Rhyven contributors
# SPDX-License-Identifier: Apache-2.0
"""Explicit local file import/artifact export over Rhyven's normal three-tool MCP."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from atlas import EXTENSIONS, IGNORED

class AgentClient:
    def __init__(self,binary,home=None,collection='global'):
        command=[binary]
        if home: command+=['--home',home]
        command+=['--collection',collection,'mcp']
        self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
        self.ident=0
        self.request('initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'code-atlas-import','version':'0.1.0'}})
        self.send({'jsonrpc':'2.0','method':'notifications/initialized'})
    def send(self,payload):
        self.process.stdin.write(json.dumps(payload)+'\n');self.process.stdin.flush()
    def request(self,method,params):
        self.ident+=1;ident=self.ident
        self.send({'jsonrpc':'2.0','id':ident,'method':method,'params':params})
        while True:
            line=self.process.stdout.readline()
            if not line: raise RuntimeError('Rhyven MCP process exited')
            result=json.loads(line)
            if result.get('id')!=ident:continue
            if 'error' in result:raise RuntimeError(str(result['error']))
            return result['result']
    def call(self,function,args):
        result=self.request('tools/call',{'name':'rhyven_call','arguments':{'category':'rhyven/repo-documentation-tool','function':'action_'+function,'args':args}})
        if result.get('isError'):raise RuntimeError(str(result.get('content')))
        return json.loads(result['content'][0]['text'])
    def close(self):
        self.process.stdin.close()
        try:self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=5)


def import_files(client,repository,path):
    root=Path(path).resolve()
    batch=[];size=0;count=0;skipped=[]
    for directory,dirs,names in os.walk(root,followlinks=False):
        dirs[:]=sorted(d for d in dirs if d not in IGNORED and not (Path(directory)/d).is_symlink())
        for name in sorted(names):
            file=Path(directory)/name
            if file.is_symlink() or name.startswith('.env') or file.suffix.lower() in ('.pem','.key','.p12'):continue
            suffix=file.suffix.lower()
            if suffix not in EXTENSIONS and suffix not in ('.md','.rst','.txt','.json','.toml','.yaml','.yml','.ini','.cfg','.xml') and name not in ('Makefile','Dockerfile','go.mod','Cargo.lock','requirements.txt'):continue
            raw=file.read_bytes()
            if len(raw)>200000:raise ValueError(f'{file}: exceeds the app file limit; select a smaller source scope')
            try:content=raw.decode('utf-8')
            except UnicodeDecodeError:skipped.append(str(file));continue
            if '\x00' in content:skipped.append(str(file));continue
            item={'path':file.relative_to(root).as_posix(),'content':content}
            encoded=len(json.dumps(item).encode())
            if batch and (size+encoded>550000 or len(batch)>=100):
                client.call('put_files',{'repository':repository,'files':batch});batch=[];size=0
            batch.append(item);size+=encoded;count+=1
    if batch:client.call('put_files',{'repository':repository,'files':batch})
    return {'imported':count,'skipped_nontext':skipped,'note':'Import updates files; it does not delete previously imported paths. Use put_files delete for removals.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=['import','export']);p.add_argument('path')
    p.add_argument('--repository',required=True);p.add_argument('--binary',default='rhyven');p.add_argument('--home');p.add_argument('--collection',default='global')
    args=p.parse_args();client=AgentClient(args.binary,args.home,args.collection)
    try:
        if args.operation=='import':print(json.dumps(import_files(client,args.repository,args.path),indent=2))
        else:
            target=Path(args.path);target.mkdir(parents=True,exist_ok=True)
            for name in ('ATLAS.md','structur.json','summaries.json'):
                offset=0
                with (target/name).open('w') as f:
                    while True:
                        part=client.call('read_artifact',{'repository':args.repository,'name':name,'offset':offset})
                        f.write(part['content']);offset=part['next_offset']
                        if offset<0:break
            print(json.dumps({'exported':str(target)}))
    finally:client.close()

if __name__=='__main__':main()
