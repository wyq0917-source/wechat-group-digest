"""Explicitly fictional database fixture and its hand-reviewed report."""
import hashlib
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from .reader import Window,export
from .report import render_report,batch_manifest

def run(make_output):
    end=datetime.fromisoformat('2026-10-28T09:00:00-07:00').timestamp()
    start=end-86400
    with tempfile.TemporaryDirectory(prefix='wxreport-fixture-') as tmp:
        root=Path(tmp);(root/'contact').mkdir();(root/'message').mkdir()
        c=sqlite3.connect(root/'contact/contact.db')
        c.execute('CREATE TABLE contact(username TEXT,nick_name TEXT)')
        c.executemany('INSERT INTO contact VALUES (?,?)',[('fictional@chatroom','虚构演示群 · 本地报告验收'),('u1','小林'),('u2','小周'),('u3','小陈')]);c.commit();c.close()
        c=sqlite3.connect(root/'message/message_0.db')
        c.execute('CREATE TABLE Name2Id(user_name TEXT)');c.executemany('INSERT INTO Name2Id VALUES (?)',[('u1',),('u2',),('u3',)])
        table='Msg_'+hashlib.md5(b'fictional@chatroom').hexdigest()
        c.execute(f'CREATE TABLE {table}(local_id INTEGER,server_id INTEGER,local_type INTEGER,sort_seq INTEGER,real_sender_id INTEGER,create_time INTEGER,message_content TEXT)')
        entries=[(1,1,'建议周五发布课程材料，大家先评估。'),(2,1,'收到，我先看看。'),(3,1,'确认先内部试讲，公开发布时间未定。'),(1,1,'我负责整理讲义，明天18点前发初稿。'),(2,1,'测试链接修复完成，已验证可打开。'),(3,49,'<msg><appmsg><title>试讲安排</title><type>5</type><url>https://example.com/course</url><des>这是虚构测试链接，未访问链接核实内容。</des></appmsg></msg>'),(1,3,'<msg><img/></msg>'),(2,34,'<msg><voicemsg/></msg>'),(3,1,'报名表由谁维护？还需要确认负责人。'),(1,1,'HTML转义测试：<script>alert("虚构")</script> & <b>原样显示</b>')]
        for i,(sender,kind,text) in enumerate(entries,1):c.execute(f'INSERT INTO {table} VALUES(?,?,?,?,?,?,?)',(i,100+i,kind,i,sender,int(start+i*600),text))
        # The endpoint row must never appear.
        c.execute(f'INSERT INTO {table} VALUES(99,999,1,99,1,?,?)',(int(end),'终点排除测试'))
        c.commit();c.close()
        data=export(root,'虚构演示群 · 本地报告验收',Window(start,end,'America/Los_Angeles'),fixture=True)
        data['account']='fictional-test-account'
    ident=lambda i:f'fictional@chatroom:server:{100+i}'
    item=lambda text,*n:{'text':text,'refs':[ident(i) for i in n]}
    report={'format_version':1,'summarizer':'当前 Codex 会话；虚构验收内容人工复核','reviewed_batches':[x['sha256'] for x in batch_manifest(data)],
      'overview':item('讨论集中在试讲安排、材料整理和报名分工。群内确认先内部试讲，公开发布时间尚未确定；链接修复为成员自述完成，未独立核实。',1,2,3,4,5,9),
      'topics':[item('发布建议与决定：周五公开发布只是建议；小周回复“收到”不等于同意。随后小陈确认先内部试讲，公开时间未定。',1,2,3),item('材料准备：小林承诺整理讲义并在“明天18点前”提交初稿；当前没有执行完成的证据。',4)],
      'todos':[{**item('整理讲义并提交初稿',4),'owner':'小林','due':'明天18点前（保留原话）','status':'已承诺，未确认完成'}],
      'confirmed':[item('小陈明确提出已确认先内部试讲。',3),item('小周报告测试链接已修复且可打开；这是群内自述，未独立访问验证。',5)],
      'unresolved':[item('公开发布的具体时间尚未确定。',3),item('报名表维护负责人尚未明确。',9)],
      'other':[item('有一条图片和一条语音消息，仅记录类型，没有识别其内容。',7,8),item('分享了一张“试讲安排”链接卡片；只提取本地标题、描述与 URL。',6)]}
    directory=make_output();render_report(data,report,directory);return directory
