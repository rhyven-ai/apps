# SPDX-FileCopyrightText: 2026 Rhyven contributors
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from atlas import Atlas, AtlasError
from lsp import Client, LspError

class AtlasTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=Atlas(self.temp.name,'fixture')
        self.off=patch('atlas.available',return_value=False);self.off.start()
        self.app.put_files([
            {'path':'src/math.py','content':'class Counter:\n    def count(self, value):\n        def adjust(x):\n            return x + 1\n        return adjust(value)\n\nasync def a():\n    return 1\n'},
            {'path':'README.md','content':'Counter example.\n'},
        ])
    def tearDown(self):
        self.off.stop();self.temp.cleanup()
    def test_symbols_lines_nested_async_and_partial_status(self):
        report=self.app.scan()
        self.assertFalse(report['complete'])
        symbols=self.app.load_index()['symbols']
        self.assertEqual([(s['qualified_name'],s['start_line']) for s in symbols],[('Counter',1),('Counter.count',2),('Counter.count.adjust',3),('a',7)])
        self.assertEqual(symbols[-1]['position'],{'line':6,'character':10})
        self.assertTrue(all(s['relationships']['references']=='not_scanned' for s in symbols))
        self.assertTrue((self.app.output/'structur.json').exists())
        self.assertTrue((self.app.output/'summaries.json').exists())
    def test_bottom_up_and_transitive_invalidation(self):
        self.app.scan()
        ctx=self.app.context('main_flow')
        with self.assertRaises(AtlasError) as e:self.app.summarize('main_flow',ctx['hash'],'Premature summary')
        self.assertEqual(e.exception.code,'DEPENDENCIES_PENDING')
        seen=[]
        while self.app.queue()['remaining']:
            queue=self.app.queue()['items'];self.assertTrue(queue)
            for n in queue:
                seen.append(n['level']);self.app.summarize(n['id'],n['hash'],'Summary of '+n['label'])
        self.assertEqual(seen[-1],'main_flow')
        self.assertLess(seen.index('directory'),seen.index('subsystem'))
        self.assertIn('Summary of Main flow',self.app.artifact('ATLAS.md')['content'])
        child=self.app.load_index()['symbols'][0]
        ctx=self.app.context(child['id'])
        self.app.summarize(child['id'],ctx['hash'],'Revised symbol summary')
        self.assertFalse(self.app.graph()['main_flow']['fresh'])
        self.assertNotIn('Summary of Main flow',self.app.artifact('ATLAS.md')['content'])
    def test_source_change_rejects_stale_summary_and_references(self):
        self.app.scan(); item=self.app.queue()['items'][0]
        self.app.put_files([{'path':'src/math.py','content':'def replacement():\n    return 2\n'}])
        with self.assertRaises(AtlasError) as e:self.app.query()
        self.assertEqual(e.exception.code,'STALE_INDEX')
        with self.assertRaises(AtlasError):self.app.artifact('ATLAS.md')
        self.app.scan()
        with self.assertRaises(AtlasError):self.app.summarize(item['id'],item['hash'],'Stale work')
        self.assertEqual(self.app.query()['items'][0]['name'],'replacement')
    def test_path_and_symlink_rejection(self):
        for path in ('../bad','/tmp/bad','x/../bad','a\\b','.git/config','./bad','x//b'):
            with self.assertRaises(AtlasError):self.app.put_files([{'path':path,'content':'x'}])
        (self.app.source/'escape').symlink_to('/etc/passwd')
        with self.assertRaises(AtlasError):self.app.survey()
    def test_invalid_python_and_failed_server_remain_partial(self):
        self.app.put_files([{'path':'src/broken.py','content':'def broken(\n'}])
        with patch('atlas.available',return_value=True), patch('atlas.Client',side_effect=LspError('startup failed')):
            result=self.app.scan()
        self.assertFalse(result['complete'])
        self.assertEqual(self.app.load_index()['coverage']['src/broken.py']['status'],'partial')
        self.assertEqual(len(self.app.load_index()['symbols']),4)

    def test_reference_limit_deduplication_and_external_exclusion(self):
        client=Client.__new__(Client);client.root=self.app.source.resolve();client.encoding='utf-16'
        refs=[{'uri':(self.app.source/'src/math.py').as_uri(),'range':{'start':{'line':i,'character':2},'end':{'line':i,'character':7}}} for i in range(130)]
        refs+=[refs[0],{'uri':'file:///etc/passwd','range':refs[0]['range']}]
        result,truncated=client.locations(refs)
        self.assertEqual(len(result),100);self.assertTrue(truncated)
        self.assertEqual(result[0]['line'],1);self.assertEqual(result[-1]['line'],100)
    def test_pagination_and_subsystems(self):
        self.app.put_files([{'path':'other/main.py','content':'def run():\n    return 3\n'}])
        first=self.app.scan(limit=1);self.assertEqual(first['next_offset'],1)
        self.assertFalse(self.app.context('file:src/math.py')['ready'])
        self.app.scan(offset=1,limit=1)
        self.app.configure([{'name':'whole','directories':['.']}])
        self.assertIn('subsystem:whole',self.app.graph())
        with self.assertRaises(AtlasError):self.app.configure([{'name':'incomplete','directories':['src']}])
        a=self.app.artifact('structur.json',limit=30)
        b=self.app.artifact('structur.json',offset=a['next_offset'],limit=30)
        self.assertEqual(a['content']+b['content'],(self.app.output/'structur.json').read_text()[:60])

if __name__=='__main__':unittest.main()
