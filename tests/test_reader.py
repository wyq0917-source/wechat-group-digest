import hashlib, sqlite3, tempfile, unittest
from unittest.mock import patch
from pathlib import Path
from wechat_report.reader import export, Window, AmbiguousGroup
from wechat_report.parsing import parse_content

def fixture(root, duplicate_group=False, millis=False):
    root=Path(root); (root/'contact').mkdir(); (root/'message').mkdir()
    c=sqlite3.connect(root/'contact/contact.db')
    c.execute('create table contact(username text,nick_name text,remark text)')
    c.executemany('insert into contact values(?,?,?)', [('g@chatroom','测试群',''),('u1','小明',''),('u2','小李','')]+([('g2@chatroom','测试群','')] if duplicate_group else []))
    c.commit(); c.close()
    table='Msg_'+hashlib.md5(b'g@chatroom').hexdigest()
    for shard in range(2):
        c=sqlite3.connect(root/f'message/message_{shard}.db')
        c.execute('create table Name2Id(user_name text)'); c.executemany('insert into Name2Id values(?)',[('u1',),('u2',)])
        c.execute(f'create table {table}(local_id integer,server_id integer,local_type integer,sort_seq integer,real_sender_id integer,create_time integer,message_content text)')
        factor=1000 if millis else 1
        rows=[(1,11,1,1,1,1800000000*factor,'建议周五发布'),(2,12,1,2,2,1800000001*factor,'收到'),(3,13,3,3,1,1800000002*factor,'<msg><img/></msg>')]
        c.executemany(f'insert into {table} values(?,?,?,?,?,?,?)',rows if shard==0 else [rows[1]])
        c.commit(); c.close()

class ReaderTests(unittest.TestCase):
    def test_window_all_shards_dedup_and_sender(self):
        with tempfile.TemporaryDirectory() as p:
            fixture(p)
            d=export(Path(p),'测试群',Window(1800000000,1800000002,'Asia/Shanghai'))
            self.assertEqual(d['stats']['message_count'],2)
            self.assertEqual(d['stats']['speaker_count'],2)
            self.assertEqual(d['stats']['duplicates_removed'],1)
            self.assertEqual(d['messages'][0]['sender_name'],'小明')
            self.assertEqual(len(d['messages'][1]['sources']),2)

    def test_ambiguous_groups_require_id(self):
        with tempfile.TemporaryDirectory() as p:
            fixture(p,True)
            with self.assertRaises(AmbiguousGroup): export(Path(p),'测试群',Window(1800000000,1800000002,'UTC'))
            d=export(Path(p),'测试群',Window(1800000000,1800000002,'UTC'),group_id='g@chatroom')
            self.assertEqual(d['group']['id'],'g@chatroom')

    def test_milliseconds_boundaries(self):
        with tempfile.TemporaryDirectory() as p:
            fixture(p,millis=True)
            d=export(Path(p),'测试群',Window(1800000000,1800000002,'UTC'))
            self.assertEqual(d['stats']['message_count'],2)
            self.assertEqual(d['messages'][0]['timestamp_unit'],'milliseconds')

    def test_media_and_reference(self):
        self.assertEqual(parse_content('<msg><img/></msg>',3)['text'],'[图片：未解析内容]')
        d=parse_content('<msg><appmsg><title>建议改到周六</title><type>57</type><refermsg><svrid>12</svrid><content>收到</content></refermsg></appmsg></msg>',49)
        self.assertEqual(d['quote']['server_id'],'12')
        self.assertEqual(d['text'],'建议改到周六')

    def test_normal_colon_heading_is_not_removed(self):
        self.assertEqual(parse_content('注意:\n不要上线',1)['text'],'注意:\n不要上线')

    def test_xml_sender_prefix_requires_matching_embedded_sender(self):
        xml='<msg><fromusername>u1</fromusername><appmsg><title>引用标题</title><type>5</type></appmsg></msg>'
        self.assertEqual(parse_content('u1:\n'+xml,49)['text'],'引用标题')
        self.assertTrue(parse_content('other:\n'+xml,1)['text'].startswith('other:\n'))

    def test_media_transport_secrets_not_exported_and_nested_quote_readable(self):
        import json
        image='<msg><img aeskey="secret-media-key" cdnthumburl="secret-url"/></msg>'
        self.assertNotIn('secret-media-key',json.dumps(parse_content(image,3)))
        card='<msg><appmsg><type>51</type><title>升级提示</title><finderFeed><nickname>演示作者</nickname><desc>演示标题</desc></finderFeed></appmsg></msg>'
        self.assertEqual(parse_content(card,49)['text'],'演示标题')
        quote='<msg><appmsg><type>57</type><title>好</title><refermsg><type>49</type><content>&lt;msg&gt;&lt;appmsg&gt;&lt;title&gt;被引标题&lt;/title&gt;&lt;type&gt;5&lt;/type&gt;&lt;/appmsg&gt;&lt;/msg&gt;</content></refermsg></appmsg></msg>'
        self.assertEqual(parse_content(quote,49)['quote']['text'],'被引标题')

    def test_new_shard_during_snapshot_is_not_silently_omitted(self):
        from wechat_report.snapshot import capture as real_capture
        with tempfile.TemporaryDirectory() as p:
            fixture(p)
            def concurrent_capture(root,paths):
                result=real_capture(root,paths)
                (Path(root)/'message/message_2.db').write_bytes((Path(root)/'message/message_0.db').read_bytes())
                return result
            with patch('wechat_report.reader.capture',side_effect=concurrent_capture):
                with self.assertRaisesRegex(RuntimeError,'分片'):
                    export(Path(p),'测试群',Window(1800000000,1800000002,'UTC'))

    def test_reads_more_than_one_fetch_batch(self):
        with tempfile.TemporaryDirectory() as p:
            fixture(p)
            table='Msg_'+hashlib.md5(b'g@chatroom').hexdigest()
            c=sqlite3.connect(Path(p)/'message/message_0.db')
            c.executemany(f'INSERT INTO {table} VALUES(?,?,?,?,?,?,?)',[(i,10000+i,1,i,1,1800000001,'虚构批量 '+str(i)) for i in range(10,1510)])
            c.commit();c.close()
            d=export(Path(p),'测试群',Window(1800000000,1800000002,'UTC'))
            self.assertEqual(d['stats']['message_count'],1502)

if __name__=='__main__': unittest.main()
