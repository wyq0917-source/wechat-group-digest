import copy, tempfile, unittest
from pathlib import Path
from wechat_report.report import write_export, validate_report, render_report, batch_manifest

def document():
    return {'data_kind':'fictional','group':{'name':'测试<script>bad()</script>','id':'g@chatroom'},'account':'fictional',
    'window':{'start':'2026-10-27T00:00:00-07:00','end':'2026-10-28T00:00:00-07:00','timezone':'America/Los_Angeles','interval':'[start, end)'},
    'scope':'本地已同步记录','stats':{'message_count':1,'speaker_count':1},'warnings':[],
    'coverage':{'all_available_rows_read':True},'messages':[{'id':'m1','sender_id':'u','sender_name':'<小明>','time':'2026-10-27T12:00:00-07:00','type':'text','text':'建议明天上线 <img src=x onerror=alert(1)>','sources':[]} ]}

def summary(d):
    return {'format_version':1,'summarizer':'当前 Codex 会话','reviewed_batches':[x['sha256'] for x in batch_manifest(d)],
    'overview':{'text':'群内出现上线建议，尚无决定或完成证据。','refs':['m1']},
    'topics':[{'text':'小明建议明天上线；只是建议。','refs':['m1']}],
    'todos':[{'text':'讨论是否上线','owner':'未明确','due':'未明确','status':'建议，未确认','refs':['m1']}],
    'confirmed':[],'unresolved':[{'text':'上线方案尚未确认。','refs':['m1']}],'other':[]}

class ReportTests(unittest.TestCase):
    def test_refs_and_read_coverage(self):
        d=document(); r=summary(d); validate_report(d,r)
        bad=copy.deepcopy(r); bad['overview']['refs']=['absent']
        with self.assertRaises(ValueError):validate_report(d,bad)
        bad=copy.deepcopy(r); bad['reviewed_batches']=[]
        with self.assertRaises(ValueError):validate_report(d,bad)

    def test_offline_html_escaped_and_outputs(self):
        d=document(); r=summary(d)
        with tempfile.TemporaryDirectory() as p:
            write_export(d,Path(p)); render_report(d,r,Path(p))
            html=(Path(p)/'index.html').read_text()
            self.assertNotIn('<script>bad()',html)
            self.assertNotIn('<img src=x',html)
            self.assertIn('&lt;小明&gt;',html)
            self.assertIn('<details',html)
            for f in ['messages.json','messages.txt','summary.md','report.json','index.html','batches/manifest.json']:
                self.assertTrue((Path(p)/f).exists())

    def test_stats_must_match(self):
        d=document(); d['stats']['message_count']=99
        with self.assertRaises(ValueError): validate_report(d,summary(d))

if __name__=='__main__':unittest.main()
