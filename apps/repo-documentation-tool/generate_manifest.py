# SPDX-FileCopyrightText: 2026 Rhyven contributors
# SPDX-License-Identifier: Apache-2.0
"""Generate the closed Rhyven action schemas; commit the generated app.json."""
import json
from pathlib import Path

def obj(properties,required=None):
    return {'type':'object','properties':properties,'required':list(properties) if required is None else required,'additionalProperties':False}
def arr(items,n=100): return {'type':'array','items':items,'maxItems':n}
def string(n=2000): return {'type':'string','maxLength':n}
def integer(lo=0,hi=100000000): return {'type':'integer','minimum':lo,'maximum':hi}
bool_={'type':'boolean'}
s=string(); short=string(500); hash_=string(64)
position=obj({'line':integer(),'character':integer()})
location=obj({'path':short,'line':integer(1),'character':integer(),'end_line':integer(1),'end_character':integer(),'encoding':string(16)})
relations=obj({k:short for k in ('definitions','references','callers','callees')})
symbol=obj({'id':short,'name':short,'qualified_name':s,'kind':short,'path':short,'start_line':integer(1),'end_line':integer(1),'position':position,'sha256':hash_,'engine':short,
    'summary':s,'summary_status':short,'definitions':arr(location),'references':arr(location),'references_truncated':bool_,'callers':arr(location),'callees':arr(location),'relationships':relations,'dependencies':arr(short)})
entry=obj({k:symbol['properties'][k] for k in ('id','name','qualified_name','kind','path','start_line','end_line','sha256','summary','summary_status')})
file=obj({'path':short,'bytes':integer(),'lines':integer(),'language':short,'sha256':hash_,'kind':short})
repository={'repository':string(64)}
actions={}
def action(name,description,inputs,output,required=()):
    actions[name]={'description':description,'input':obj(dict(repository,**inputs),['repository',*required]),'output':output}
action('put_files','Import selected UTF-8 repository files in batches into private app state; no host directory mount or repository code execution.',{'files':arr(obj({'path':short,'content':string(200000)})),'delete':arr(short)},obj({'repository':short,'files':integer(),'revision':hash_}),['files'])
action('survey','Survey tree, file sizes, README/config paths and detected language-server availability. Paginated.',{'offset':integer(),'limit':integer(1,100)},obj({'repository':short,'revision':hash_,'files':arr(file),'total_files':integer(),'total_bytes':integer(),'languages':arr(obj({'language':short,'files':integer(),'server':short,'available':bool_}),20),'readmes':arr(short),'configs':arr(short),'tree':string(60000),'truncated':bool_}))
action('scan','Scan a page of source files; select matching LSPs, persist structur.json, and return next_offset. Repeat until -1. Missing engines/coverage are explicit.',{'offset':integer(),'limit':integer(1,50),'relationships':bool_},obj({'revision':hash_,'files_scanned':integer(),'symbols':integer(),'complete':bool_,'issues':arr(s),'next_offset':integer(-1),'artifact':short}))
action('query','Search stored function/class symbols and summaries before reading source. Use read_symbol or relations for full relationships.',{'text':short,'offset':integer(),'limit':integer(1,100)},obj({'items':arr(entry),'total':integer(),'offset':integer()}))
action('read_file','Read a selected README, config or source excerpt from the imported snapshot.',{'path':short,'offset':integer(),'limit':integer(1,200)},obj({'path':short,'source':string(60000),'start_line':integer(1),'next_offset':integer(-1),'sha256':hash_}),['path'])
action('read_symbol','Read one symbol and its source lines selectively. Line numbers are one-based; LSP character positions use the reported encoding.',{'symbol_id':short,'offset':integer(),'limit':integer(1,200)},obj({'symbol':symbol,'source':string(60000),'source_start_line':integer(1),'source_end_line':integer(),'source_truncated':bool_}),['symbol_id'])
action('relations','Refresh one symbol’s definitions, up to 100 references, and callers/callees where the language server supports them.',{'symbol_id':short},obj({'symbol':symbol}),['symbol_id'])
action('summary_queue','Get ready summary targets in dependency order: symbols, files, directories, subsystems, main flow. The calling agent writes summaries.',{'limit':integer(1,100)},obj({'items':arr(obj({'id':short,'level':short,'label':s,'hash':hash_,'status':short})),'remaining':integer()}))
action('summary_context','Read a summary target and paginated child summaries. Use returned hash to prevent stale writes; read source only as needed.',{'id':short,'offset':integer(),'limit':integer(1,100)},obj({'id':short,'level':short,'hash':hash_,'ready':bool_,'source':string(60000),'source_truncated':bool_,'children':arr(obj({'id':short,'summary':s,'status':short})),'children_total':integer(),'next_offset':integer(-1),'instruction':s}),['id'])
action('write_summary','Store an agent-written summary only after child summaries are fresh. Changing a child invalidates its parents.',{'id':short,'expected_hash':hash_,'summary':s},obj({'id':short,'status':short}),['id','expected_hash','summary'])
action('configure_subsystems','Group existing directories into named subsystems before writing subsystem/main-flow summaries. All source files must be covered.',{'subsystems':arr(obj({'name':string(64),'directories':arr(short)}),50)},obj({'subsystems':integer()}),['subsystems'])
action('build_atlas','Render ATLAS.md and structur.json with freshness and coverage; never invent missing summaries.',{},obj({'artifacts':arr(short,3),'summaries_remaining':integer()}))
action('read_artifact','Read a bounded chunk of ATLAS.md, structur.json or summaries.json; follow next_offset until -1.',{'name':{'type':'string','enum':['ATLAS.md','structur.json','summaries.json']},'offset':integer(),'limit':integer(1,60000)},obj({'name':short,'content':string(60000),'offset':integer(),'next_offset':integer(-1),'sha256':hash_,'total_characters':integer()}),['name'])
p={'format':2,'name':'rhyven/repo-documentation-tool','publisher':'rhyven','display_name':'Rhyven Repo Documentation Tool','version':'0.1.1','description':'Repository survey, language-server symbol/reference indexing and agent-written hierarchical code summaries.','hosting':{'mode':'local'},'execution':{'driver':'container','protocol':'rhyven.container/1','image':'sha256:'+'0'*64,'timeout_seconds':300,'memory_mb':2048,'cpus':2},'permissions':['state.read','state.write','container.execute'],'objects':{},'actions':actions,'guide':Path(__file__).with_name('GUIDE.md').read_text(),'tests':[
 {'operation':'execute','args':{'action':'put_files','args':{'repository':'conformance','files':[{'path':'sample.py','content':'def greet(name):\n    return "Hello " + name\n'}]}},'expect':{'files':1}},
 {'operation':'execute','args':{'action':'survey','args':{'repository':'conformance'}},'expect':{'total_files':1}},
 {'operation':'execute','args':{'action':'scan','args':{'repository':'conformance'}},'expect':{'symbols':1,'next_offset':-1}},
]}
Path(__file__).with_name('app.json').write_text(json.dumps(p,indent=2)+'\n')
