# SPDX-FileCopyrightText: 2026 Rhyven contributors
# SPDX-License-Identifier: Apache-2.0
"""Bounded stdio LSP client. Server commands are app-owned, never repository input."""
import json
import os
from pathlib import Path
import selectors
import signal
import shutil
import subprocess
import time
import tempfile
from urllib.parse import unquote, urlparse

SERVERS = {
    'python': ['pyright-langserver', '--stdio'],
    'c': ['clangd', '--background-index', '--enable-config=false'],
    'cpp': ['clangd', '--background-index', '--enable-config=false'],
    'fortran': ['fortls', '--disable_autoupdate', '--nthreads=1'],
    'go': ['gopls', 'serve'],
    'rust': ['rust-analyzer'],
    'java': ['jdtls'],
    'javascript': ['typescript-language-server', '--stdio'],
    'typescript': ['typescript-language-server', '--stdio'],
}
LANGUAGE_IDS = {'cpp':'cpp','fortran':'fortran','javascript':'javascript','typescript':'typescript'}
SETTINGS = {
    'python': {'analysis': {'autoSearchPaths': False, 'diagnosticMode':'workspace', 'useLibraryCodeForTypes':False}},
    'rust-analyzer': {'cargo':{'buildScripts':{'enable':False}},'procMacro':{'enable':False},'checkOnSave':False},
    'java': {'import': {'gradle':{'enabled':False},'maven':{'enabled':False}},'autobuild':{'enabled':False}},
    'gopls': {'expandWorkspaceToModule':False, 'directoryFilters':['-.git','-node_modules']},
}

class LspError(Exception):
    pass


def available(language):
    return language in SERVERS and shutil.which(SERVERS[language][0]) is not None


class Client:
    def __init__(self, root, language, deadline, cache):
        # Servers may generate Cargo.lock, indexes or project metadata. Analyze a
        # disposable copy so those writes never mutate the imported snapshot/hash.
        cache.mkdir(parents=True, exist_ok=True)
        self.workspace = tempfile.TemporaryDirectory(prefix='workspace-', dir=cache)
        self.root = Path(self.workspace.name) / 'source'
        shutil.copytree(root, self.root)
        self.deadline = deadline
        self.sequence = 0
        self.buffer = b''
        self.settings = SETTINGS
        self.capabilities = {}
        self.encoding = 'utf-16'
        self.process = None
        self.own_group = os.environ.get('RHYVEN_SCRIPT_ACTION') != '1'
        command = list(SERVERS[language])
        if language == 'java':
            command += ['-data', str(cache / 'jdt-workspace'), '-configuration', str(cache / 'jdt-config'), '--jvm-arg=-Xms128m', '--jvm-arg=-Xmx1024m', '--jvm-arg=-Duser.home='+str(cache)]
        env = dict(os.environ, XDG_CACHE_HOME=str(cache), GOPATH=str(cache/'go'), GOCACHE=str(cache/'go-build'), GOPROXY='off', GOSUMDB='off', GOTOOLCHAIN='local', CARGO_HOME=str(cache/'cargo'))
        cache.mkdir(parents=True, exist_ok=True)
        try:
            self.process = subprocess.Popen(command, cwd=self.root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0, start_new_session=self.own_group)
            self.selector = selectors.DefaultSelector()
            self.selector.register(self.process.stdout, selectors.EVENT_READ)
            initialization = {'settings':SETTINGS, 'preferences':{'allowLocalPluginLoads':False}, 'hostInfo':'code-atlas'}
            if language=='rust': initialization=SETTINGS['rust-analyzer']
            if language in ('javascript','typescript'):
                initialization.update(disableAutomaticTypingAcquisition=True,maxTsServerMemory=768)
                server = Path(shutil.which(command[0])).resolve()
                tsserver = server.parents[2] / 'typescript/lib/tsserver.js'
                if not tsserver.is_file():
                    raise LspError('Install TypeScript alongside typescript-language-server')
                initialization['tsserver']={'path':str(tsserver),'useSyntaxServer':'never'}
            result = self.request('initialize', {'processId':os.getpid(), 'rootUri':self.root.as_uri(), 'workspaceFolders':[{'uri':self.root.as_uri(),'name':self.root.name}],
                'capabilities':{'general':{'positionEncodings':['utf-16']}, 'workspace':{'configuration':True,'workspaceFolders':True}, 'textDocument':{'documentSymbol':{'hierarchicalDocumentSymbolSupport':True},'callHierarchy':{'dynamicRegistration':False}}},
                'initializationOptions':initialization}, timeout=40)
            self.capabilities = result.get('capabilities',{})
            self.encoding = self.capabilities.get('positionEncoding','utf-16')
            self.notify('initialized', {})
            self.notify('workspace/didChangeConfiguration', {'settings':SETTINGS})
        except Exception:
            self.close()
            raise

    def send(self, message):
        data=json.dumps(message).encode()
        payload=f'Content-Length: {len(data)}\r\n\r\n'.encode()+data
        while payload:
            written=self.process.stdin.write(payload)
            if not written: raise LspError('Language server input closed')
            payload=payload[written:]
        self.process.stdin.flush()

    def notify(self, method, params):
        self.send({'jsonrpc':'2.0','method':method,'params':params})

    def receive(self, until):
        while True:
            if b'\r\n\r\n' in self.buffer:
                header, body = self.buffer.split(b'\r\n\r\n',1)
                try:
                    size=int(next(line.split(b':',1)[1] for line in header.split(b'\r\n') if line.lower().startswith(b'content-length:')))
                except (ValueError,StopIteration) as exc:
                    raise LspError('Invalid LSP framing') from exc
                if size < 0 or size > 16*1024*1024:
                    raise LspError('LSP response exceeds 16 MiB')
                if len(body)>=size:
                    self.buffer=body[size:]
                    return json.loads(body[:size])
            if len(self.buffer)>17*1024*1024:
                raise LspError('LSP buffer limit exceeded')
            remaining=min(until,self.deadline)-time.monotonic()
            if remaining<=0 or not self.selector.select(remaining):
                raise LspError('LSP request timed out; scan coverage is incomplete')
            chunk=os.read(self.process.stdout.fileno(),65536)
            if not chunk:
                raise LspError('Language server exited before responding')
            self.buffer+=chunk

    def request(self, method, params, timeout=12):
        self.sequence+=1
        ident=self.sequence
        self.send({'jsonrpc':'2.0','id':ident,'method':method,'params':params})
        until=min(self.deadline,time.monotonic()+timeout)
        while True:
            message=self.receive(until)
            if 'method' in message:
                if 'id' in message:
                    name=message['method']
                    if name=='workspace/configuration':
                        result=[]
                        for item in message.get('params',{}).get('items',[]):
                            value=SETTINGS
                            for key in item.get('section','').split('.'):
                                value=value.get(key,{}) if isinstance(value,dict) else {}
                            result.append(value)
                    elif name=='workspace/workspaceFolders':
                        result=[{'uri':self.root.as_uri(),'name':self.root.name}]
                    elif name=='workspace/applyEdit':
                        result={'applied':False,'failureReason':'Atlas analysis is read-only'}
                    elif name in ('client/registerCapability','window/workDoneProgress/create','client/unregisterCapability'):
                        result=None
                    else:
                        self.send({'jsonrpc':'2.0','id':message['id'],'error':{'code':-32601,'message':'Client operation unavailable'}})
                        continue
                    self.send({'jsonrpc':'2.0','id':message['id'],'result':result})
                continue
            if message.get('id')==ident:
                if 'error' in message:
                    raise LspError(str(message['error'].get('message','Language server request failed')))
                return message.get('result')

    def open(self, relative, language):
        file=self.root/relative
        self.notify('textDocument/didOpen', {'textDocument':{'uri':file.as_uri(),'languageId':LANGUAGE_IDS.get(language,language),'version':1,'text':file.read_text()}})

    def close(self):
        process=self.process
        if process is not None:
            if process.poll() is None:
                if self.own_group: os.killpg(process.pid,signal.SIGTERM)
                else: process.terminate()
                try: process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    if self.own_group: os.killpg(process.pid,signal.SIGKILL)
                    else: process.kill()
                    process.wait(timeout=2)
            for stream in (process.stdin,process.stdout):
                if stream: stream.close()
        if hasattr(self,'selector'): self.selector.close()
        if hasattr(self,'workspace'): self.workspace.cleanup()

    def location(self, loc):
        uri=loc.get('uri',loc.get('targetUri',''))
        parsed=urlparse(uri)
        if parsed.scheme!='file' or parsed.netloc not in ('','localhost'):
            return None
        try:
            relative=Path(unquote(parsed.path)).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return None
        span=loc.get('range',loc.get('targetSelectionRange',loc.get('targetRange',{})))
        if not span: return None
        return {'path':relative,'line':span['start']['line']+1,'character':span['start']['character'],
                'end_line':span['end']['line']+1,'end_character':span['end']['character'], 'encoding':self.encoding}

    def locations(self, values):
        if isinstance(values,dict): values=[values]
        unique={}
        for value in values or []:
            loc=self.location(value)
            if loc: unique[json.dumps(loc,sort_keys=True)]=loc
        result=sorted(unique.values(),key=lambda v:(v['path'],v['line'],v['character']))
        return result[:100], len(result)>100
