"""Offline contract tests. All generated files live in external TemporaryDirectory."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error
import trending as t

FIX = Path(__file__).resolve().parent / 'fixtures'

def row(name='a/b', metrics=True, description='Hello &amp; <b>world</b>'):
    return (f'<article class="other Box-row"><h2><a href="/{name}"><span>a /</span>b</a></h2>'
            f'<p>{description}</p><span itemprop="programmingLanguage"><b>Python</b></span>'
            + ('<a href="/a/b/stargazers"><svg></svg>1,234</a><a href="/a/b/forks">0</a><span>12 stars today</span>' if metrics else '') + '</article>')

# Python 3.12's Windows mode=0700 temp ACL excludes some restricted sandbox
# tokens. Inherit the existing external temp parent's ACL for NEW test roots;
# do not modify existing permissions or weaken any product assertions.
_TEMP = tempfile.TemporaryDirectory
_MKDIR = os.mkdir

def external_tempdir(*args, **kwargs):
    if os.name != 'nt':
        return _TEMP(*args, **kwargs)
    def inherited_mkdir(path, mode=0o777, **options):
        return _MKDIR(path, 0o777 if mode == 0o700 else mode, **options)
    with patch.object(os, 'mkdir', side_effect=inherited_mkdir):
        return _TEMP(*args, **kwargs)

class ParserTests(unittest.TestCase):
    def test_real_fixture(self):
        repos = t.parse_trending((FIX/'trending.html').read_text(encoding='utf-8'))
        expected = json.loads((FIX/'upstream-daily.json').read_text(encoding='utf-8'))['repos']
        self.assertEqual([r['name'] for r in repos], [r['name'] for r in expected])
        for actual, source in zip(repos, expected):
            self.assertIsInstance(actual['stars'], int)
            self.assertIsInstance(actual['forks'], int)
            self.assertIsInstance(actual['stars_today'], int)
            self.assertEqual(actual['url'], 'https://github.com/'+actual['name'])
        self.assertEqual([r['stars'] for r in repos], [41646,50223,282397,53999,52188,9866,8389,95308,151654,73139,215161,76008,7732])
    def test_nested_entities_dedup_unrelated(self):
        repos = t.parse_trending('<article>unrelated</article>'+row()+row()+row('c/d',False))
        self.assertEqual([r['name'] for r in repos], ['a/b','c/d'])
        self.assertEqual(repos[0]['description'], 'Hello & world')
        self.assertEqual(repos[0]['stars'],1234)
        self.assertEqual(repos[0]['forks'],0)
        self.assertEqual(repos[0]['stars_today'],12)
        self.assertIsNone(repos[1]['stars'])
    def test_abbreviated_and_missing_metrics(self):
        repo = t.parse_trending(row().replace('1,234','1.2k').replace('12 stars','1k stars'))[0]
        self.assertIsNone(repo['stars'])
        self.assertIsNone(repo['stars_today'])
        self.assertEqual(repo['forks'],0)
        self.assertIsNone(t.parse_trending(row(metrics=False))[0]['forks'])
    def test_structural_errors_not_partial(self):
        for source in ('', '<article>unrelated</article>', row()+'<article class="Box-row"><p>bad</p></article>', row()[:-10], '<article class="Box-row"><h2><a href="/bad">bad</a></h2></article>'):
            with self.subTest(source=source[:50]), self.assertRaisesRegex(t.BriefingError,'parse.*structure|parse.*malformed'):
                t.parse_trending(source)

class ProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = external_tempdir(prefix='trending tests ')
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / 'output with spaces'
        self.snapshot = t.collect(self.out, FIX/'trending.html')
        self.data = t.load(self.snapshot)
        self.value = {'items':[dict(name=r['name'],summary_zh='来源描述摘要，尚未验证。',reason_zh='判断：值得关注。') for r in self.data['repositories'][:5]]}
        self.import_file = Path(self.temp.name)/'import.json'
        self.write_import()
    def write_import(self):
        self.import_file.write_text(json.dumps(self.value,ensure_ascii=False),encoding='utf-8')
    def test_archive_integrity_dedup_immutability(self):
        first = self.snapshot.read_bytes()
        other = t.collect(self.out,FIX/'trending.html')
        second = t.load(other)
        self.assertNotEqual(self.snapshot, other)
        self.assertNotEqual(self.data['raw_html'],second['raw_html'])
        self.assertEqual(self.data['content_sha256'],second['content_sha256'])
        self.assertEqual(len(list((self.out/'content').glob('*.json'))),1)
        self.assertEqual(first,self.snapshot.read_bytes())
        self.assertEqual(self.data['source_kind'],'fixture')
        self.assertIsNone(self.data['listing_date'])
        self.assertIsNotNone(t.dt.datetime.fromisoformat(self.data['collected_at']).tzinfo)
        self.assertEqual(t.digest((self.out/self.data['raw_html']).read_bytes()), self.data['raw_sha256'])
    def test_http_errors_timeout_and_bad_body_saved(self):
        for error,kind in [(urllib.error.HTTPError(t.SOURCE,429,'rate limit',{},None),'http'),(TimeoutError(),'timeout'),(urllib.error.URLError(TimeoutError()),'timeout')]:
            with patch.object(t.urllib.request,'urlopen',side_effect=error), self.assertRaisesRegex(t.BriefingError,kind):
                t.collect(self.out)
        response = unittest.mock.MagicMock()
        response.__enter__.return_value = response
        response.getcode.return_value = 200
        response.read.return_value = b'<html>no rows</html>'
        before = len(list((self.out/'raw').glob('*')))
        with patch.object(t.urllib.request,'urlopen',return_value=response), self.assertRaisesRegex(t.BriefingError,'parse'):
            t.collect(self.out)
        self.assertEqual(len(list((self.out/'raw').glob('*'))),before+1)
    def test_validation(self):
        self.assertEqual(t.validate_analysis(self.value,self.data),self.value)
        self.assertEqual(t.validate_analysis({'items':self.value['items'][:1]},self.data)['items'],self.value['items'][:1])
        invalid = []
        for count in (0,9):
            invalid.append({'items':(self.value['items']*2)[:count]})
        for key,val in [('name','unknown/repo'),('summary_zh','English only'),('reason_zh',''),('summary_zh',None)]:
            v=copy.deepcopy(self.value); v['items'][0][key]=val; invalid.append(v)
        v=copy.deepcopy(self.value); v['items'][1]=v['items'][0]; invalid.append(v)
        v=copy.deepcopy(self.value); v['items'][0]['extra']=1; invalid.append(v)
        invalid += [[], {'items':'bad'}, {'items':self.value['items'],'extra':True}]
        for value in invalid:
            with self.subTest(value=value),self.assertRaises(t.BriefingError):
                t.validate_analysis(value,self.data)
    def test_json_cache_provenance_and_no_snapshot_mutation(self):
        original = self.snapshot.read_bytes()
        raw = (self.out/self.data['raw_html']).read_bytes()
        report, analysis = t.analyze(self.snapshot,self.out,'json',self.import_file)
        first = report.read_bytes()
        manifest = t.load(report.parent/'manifest.json')
        self.assertEqual(manifest['identity']['backend'],'json-import')
        self.assertEqual(manifest['identity']['content'],self.data['content_sha256'])
        self.assertEqual(manifest['identity']['publication_policy'],'no-repeat-v1')
        text = report.read_text(encoding='utf-8')
        self.assertNotIn(self.snapshot.name,text)
        self.assertNotIn(self.data['content_sha256'],text)
        self.assertNotIn('仓库来源事实',text)
        self.assertNotIn(chr(42),text)
        self.assertNotIn(chr(35),text)
        self.assertTrue(text.startswith('GitHub Trending 中文日报｜'))
        self.assertIn('项目介绍：',text)
        self.assertNotIn('功能简介：',text)
        self.assertNotIn('推荐理由：',text)
        self.assertIn('Trending 排名：',text)
        self.assertIn('今日新增星标（页面值）：',text)
        with patch.object(t,'deepseek_analysis',side_effect=AssertionError('unexpected call')):
            self.assertEqual((report,analysis),t.analyze(self.snapshot,self.out,'json',self.import_file))
        self.value['items'][0]['reason_zh']='判断已经改变。'
        self.write_import()
        with self.assertRaisesRegex(t.BriefingError,'schema'):
            t.analyze(self.snapshot,self.out,'json',self.import_file)
        self.assertEqual(first,report.read_bytes())
        self.assertEqual(original,self.snapshot.read_bytes())
        self.assertEqual(raw,(self.out/self.data['raw_html']).read_bytes())
        remaining = {'items':[dict(name=r['name'],summary_zh='来源描述摘要。',reason_zh='值得关注。') for r in self.data['repositories'][5:10]]}
        with patch.object(t,'deepseek_analysis',return_value=remaining) as backend:
            real,_ = t.analyze(self.snapshot,self.out,'deepseek',model='test-model')
            self.assertEqual(backend.call_count,1)
            offered = backend.call_args.args[0]['repositories']
            self.assertFalse({r['name'] for r in offered} & {i['name'] for i in self.value['items']})
            self.assertEqual(t.load(real.parent/'manifest.json')['identity']['backend'],'deepseek')
            self.assertEqual(real,t.analyze(self.snapshot,self.out,'deepseek',model='test-model')[0])
            self.assertEqual(backend.call_count,1)

    def test_escape_analysis_and_remove_asterisks_and_hashes(self):
        value = copy.deepcopy(self.value)
        value['items'][0]['summary_zh']='摘要：</p>\n# Injected [click](javascript:alert(1)) <script>x</script> **内容**'
        value['items'][0]['reason_zh']='判断：#值得关注。'
        result = t.render(self.data,self.snapshot,value,'json-import')
        self.assertNotIn(chr(35),result)
        self.assertNotIn('<script>',result)
        self.assertIn('&lt;script&gt;',result)
        self.assertIn('\\[click\\]',result)
        self.assertNotIn(chr(42),result)
        self.assertIn(self.data['repositories'][0]['url'],result)

    def test_history_across_daily_directories(self):
        root = Path(self.temp.name)/'daily'
        previous, current = root/'2026-10-18', root/'2026-10-19'
        first_snapshot = t.collect(previous,FIX/'trending.html')
        t.analyze(first_snapshot,previous,'json',self.import_file)
        second_snapshot = t.collect(current,FIX/'trending.html')
        original = second_snapshot.read_bytes()
        with self.assertRaisesRegex(t.BriefingError,'schema'):
            t.analyze(second_snapshot,current,'json',self.import_file)
        remaining = {'items':[dict(name=r['name'],summary_zh='新项目简介。',reason_zh='值得关注。') for r in self.data['repositories'][5:]]}
        with patch.object(t,'deepseek_analysis',return_value=remaining) as backend:
            report,_ = t.analyze(second_snapshot,current,'deepseek')
        self.assertEqual([r['name'] for r in backend.call_args.args[0]['repositories']], [r['name'] for r in self.data['repositories'][5:]])
        self.assertEqual(len(t.published_names(current)),len(self.data['repositories']))
        self.assertEqual(second_snapshot.read_bytes(),original)
        self.assertTrue(report.exists())
        self.assertFalse((root/'history.lock').exists())

    def test_final_reader_history_single_candidate_and_exhaustion(self):
        root = Path(self.temp.name)/'daily'
        previous, current = root/'2026-10-18', root/'2026-10-19'
        previous.mkdir(parents=True)
        headings = [f'## {i}. [{r["name"]}](https://github.com/{r["name"].upper()})' for i,r in enumerate(self.data['repositories'][:-1],1)]
        headings[-1] = headings[-1].removeprefix('## ')
        (previous/'github-trending-2026-10-18.md').write_text('\n\n'.join(headings),encoding='utf-8')
        draft = previous/'reports'/'old-draft'
        draft.mkdir(parents=True)
        t.save(draft/'manifest.json',{'identity':{'backend':'deepseek'}})
        t.save(draft/'analysis.json',{'items':[{'name':self.data['repositories'][-1]['name']}]})
        self.assertEqual(len(t.published_names(current)),len(self.data['repositories'])-1)
        snapshot = t.collect(current,FIX/'trending.html')
        one = {'items':[dict(name=self.data['repositories'][-1]['name'],summary_zh='唯一新项目。',reason_zh='值得关注。')]}
        imported = root/'single-analysis.json'
        imported.write_text(json.dumps(one),encoding='utf-8')
        report,_ = t.analyze(snapshot,current,'json',imported)
        self.assertEqual(len(t.load(report.parent/'analysis.json')['items']),1)
        exhausted = t.collect(root/'2026-10-20',FIX/'trending.html')
        with patch.object(t,'deepseek_analysis') as backend, self.assertRaisesRegex(t.BriefingError,'no-new-projects'):
            t.analyze(exhausted,root/'2026-10-20')
        backend.assert_not_called()
        self.assertFalse((root/'history.lock').exists())

    def test_model_schema_failure_no_report_and_receipt(self):
        with patch.object(t,'deepseek_analysis',return_value={'items':[]}):
            with self.assertRaisesRegex(t.BriefingError,'schema'):
                t.analyze(self.snapshot,self.out)
        self.assertFalse(list((self.out/'reports').glob('*/report.md')) if (self.out/'reports').exists() else [])
        receipts=list((self.out/'receipts').glob('*.json'))
        self.assertEqual(len(receipts),1)
        self.assertIsNotNone(t.load(receipts[0])['finished_at'])
    def test_cli_failure_json_and_run_lock(self):
        stdout,stderr=io.StringIO(),io.StringIO()
        with patch.object(t,'collect',side_effect=t.BriefingError('http','HTTP 503')),contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
            code=t.main(['run','--output-dir',str(self.out)])
        self.assertEqual(code,1)
        self.assertEqual(stdout.getvalue(),'')
        logs=list((self.out/'logs').glob('*.json'))
        self.assertEqual(len(logs),1)
        self.assertEqual(t.load(logs[0])['kind'],'http')
        self.assertFalse((self.out/'run.lock').exists())
        with t.run_lock(self.out):
            with self.assertRaisesRegex(t.BriefingError,'lock'):
                with t.run_lock(self.out): pass
    def test_cli_arbitrary_cwd(self):
        proc=subprocess.run([sys.executable,'-B',str(t.ROOT/'trending.py'),'collect','--output-dir',str(self.out),'--html-file',str(FIX/'trending.html')],cwd=self.temp.name,capture_output=True,encoding='utf-8')
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertTrue(Path(json.loads(proc.stdout)['snapshot']).is_absolute())
    def test_deepseek_request_and_invalid_json(self):
        response = unittest.mock.MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(self.value)}}]}).encode()
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY':'test-key'}), patch.object(t.urllib.request,'urlopen',return_value=response) as send:
            receipt = {}
            self.assertEqual(t.deepseek_analysis(self.data,'deepseek-chat',7,receipt),self.value)
        request = send.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url,'https://api.deepseek.com/chat/completions')
        self.assertEqual(payload['response_format'],{'type':'json_object'})
        self.assertNotIn(str(self.snapshot),json.dumps(payload))
        self.assertNotIn('<article',json.dumps(payload))
        self.assertEqual(send.call_args.kwargs['timeout'],7)
        response.read.return_value = b'{invalid'
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY':'test-key'}), patch.object(t.urllib.request,'urlopen',return_value=response):
            with self.assertRaisesRegex(t.BriefingError,'model-json'):
                t.deepseek_analysis(self.data,None,7,{})
    def test_full_run_offline_network_adapter(self):
        response=unittest.mock.MagicMock()
        response.__enter__.return_value=response
        response.getcode.return_value=200
        response.read.return_value=(FIX/'trending.html').read_bytes()
        with patch.object(t.urllib.request,'urlopen',return_value=response),contextlib.redirect_stdout(io.StringIO()) as stdout,contextlib.redirect_stderr(io.StringIO()) as stderr:
            result=t.main(['run','--output-dir',str(self.out),'--backend','json','--analysis-file',str(self.import_file)])
        self.assertEqual(result,0,stderr.getvalue())
        artifacts=json.loads(stdout.getvalue())
        self.assertEqual(set(artifacts),{'snapshot','analysis','report'})
        for path in artifacts.values():
            self.assertTrue(Path(path).is_absolute())
            self.assertTrue(Path(path).is_file())
        self.assertEqual(t.load(artifacts['snapshot'])['source_kind'],'network')
        self.assertFalse((self.out/'run.lock').exists())
    def test_snapshot_content_corruption_rejected(self):
        data=copy.deepcopy(self.data)
        data['repositories'][0]['description']='modified'
        with self.assertRaisesRegex(t.BriefingError,'content_sha256'):
            t.validate_snapshot(data)
    def test_cache_tamper_rejected(self):
        report, _ = t.analyze(self.snapshot,self.out,'json',self.import_file)
        report.write_text('tampered',encoding='utf-8')
        with self.assertRaisesRegex(t.BriefingError,'archive'):
            t.analyze(self.snapshot,self.out,'json',self.import_file)
    def test_network_success_has_network_provenance(self):
        response=unittest.mock.MagicMock()
        response.__enter__.return_value=response
        response.getcode.return_value=200
        response.read.return_value=(FIX/'trending.html').read_bytes()
        with patch.object(t.urllib.request,'urlopen',return_value=response) as fetch:
            result=t.load(t.collect(self.out,timeout=7))
        self.assertEqual(fetch.call_args.kwargs['timeout'],7)
        self.assertEqual(result['source_kind'],'network')
        self.assertEqual(result['content_sha256'],self.data['content_sha256'])
    def test_cli_analyze_schema_failure_logs_no_report(self):
        self.import_file.write_text('{bad json',encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()) as output,contextlib.redirect_stderr(io.StringIO()):
            code=t.main(['analyze','--snapshot',str(self.snapshot),'--output-dir',str(self.out),'--backend','json','--analysis-file',str(self.import_file)])
        self.assertEqual(code,1)
        self.assertEqual(output.getvalue(),'')
        self.assertEqual(t.load(next((self.out/'logs').glob('*.json')))['kind'],'json')
        self.assertFalse((self.out/'reports').exists())

if __name__=='__main__':
    unittest.main()
