import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from .crypto import open_database
from .snapshot import capture
from .parsing import parse_content

class AmbiguousGroup(ValueError):
    def __init__(self,candidates):
        self.candidates=candidates
        super().__init__('同名群需要 --group-id 选择：'+json.dumps(candidates,ensure_ascii=False))

@dataclass(frozen=True)
class Window:
    start: float
    end: float
    timezone: str
    def __post_init__(self):
        ZoneInfo(self.timezone)
        if not 0<=self.start<self.end: raise ValueError('时间范围必须满足 start < end')
    def iso(self,ts): return datetime.fromtimestamp(ts,ZoneInfo(self.timezone)).isoformat()
    def metadata(self): return {'start':self.iso(self.start),'end':self.iso(self.end),'start_epoch':self.start,'end_epoch':self.end,'timezone':self.timezone,'interval':'[start, end)'}

def columns(conn,table):
    if not re.fullmatch(r'[A-Za-z0-9_]+',table): raise ValueError('Unsafe table identifier')
    return {r['name'] for r in conn.execute(f'PRAGMA table_info("{table}")')}

def required(conn,table,names):
    actual=columns(conn,table)
    if not set(names)<=actual: raise ValueError(f'未支持的数据库结构 {table}: missing {sorted(set(names)-actual)}')
    return actual

def groups(conn,name,group_id=None):
    required(conn,'contact',['username','nick_name'])
    candidates=[dict(r) for r in conn.execute("SELECT username AS id,nick_name AS name FROM contact WHERE nick_name=? AND username LIKE '%@chatroom'",(name,))]
    if group_id: candidates=[g for g in candidates if g['id']==group_id]
    if not candidates: raise ValueError('未找到完整群名；请检查微信中显示的名称及本地同步状态。')
    if len(candidates)>1: raise AmbiguousGroup(candidates)
    return candidates[0]

def export(root,name,window,passphrase=None,group_id=None,fixture=False):
    root=Path(root)
    shards=sorted(p.relative_to(root) for p in (root/'message').glob('*.db') if re.fullmatch(r'(?:biz_)?message_\d+\.db',p.name))
    if not shards: raise ValueError('未找到消息数据库分片')
    paths=[Path('contact/contact.db'),*shards]
    shots=capture(root,paths)
    after=sorted(p.relative_to(root) for p in (root/'message').glob('*.db') if re.fullmatch(r'(?:biz_)?message_\d+\.db',p.name))
    if shards!=after:
        shots.clear()
        raise RuntimeError('捕获期间消息分片集合发生变化，拒绝不完整导出；请重试。')
    conns=[]; audit={}; warnings=[]
    try:
        contact,a=open_database(shots['contact/contact.db'],passphrase); conns.append(contact); audit['contact/contact.db']=a
        group=groups(contact,name,group_id)
        table='Msg_'+hashlib.md5(group['id'].encode()).hexdigest()
        all_rows=[]; limits=[]; source_count=0; present=0
        names={}
        def sender_name(sender):
            if sender not in names:
                r=contact.execute('SELECT nick_name FROM contact WHERE username=?',(sender,)).fetchone()
                names[sender]=r[0] if r and r[0] else sender
            return names[sender]
        for shard in shards:
            db,a=open_database(shots[str(shard)],passphrase); conns.append(db); audit[str(shard)]=a
            if not columns(db,table):
                a['target_table_present']=False; continue
            present+=1; a['target_table_present']=True
            cols=required(db,table,['local_id','server_id','local_type','sort_seq','real_sender_id','create_time','message_content'])
            a['message_columns']=sorted(cols)
            required(db,'Name2Id',['user_name'])
            lo,hi=db.execute(f'SELECT MIN(create_time),MAX(create_time) FROM "{table}"').fetchone()
            if lo is None: continue
            # Select by observed magnitude; reject mixed/unsupported timestamp units.
            def unit(v):
                if 946684800<=v<4102444800: return 1
                if 946684800000<=v<4102444800000: return 1000
                raise ValueError('时间戳单位/年代不在已验证范围内')
            factor=unit(lo)
            if unit(hi)!=factor: raise ValueError('同一表中出现混合时间戳单位')
            a['timestamp_unit']='seconds' if factor==1 else 'milliseconds'
            limits.append((lo/factor,hi/factor))
            query=f'SELECT m.*, n.user_name AS mapped_sender FROM "{table}" m LEFT JOIN Name2Id n ON m.real_sender_id=n.rowid WHERE m.create_time>=? AND m.create_time<? ORDER BY m.create_time,m.sort_seq,m.local_id'
            cursor=db.execute(query,(window.start*factor,window.end*factor))
            for batch in iter(lambda:cursor.fetchmany(500),[]):
                for r in batch:
                    source_count+=1
                    body=r['message_content']
                    if (body is None or body==b'' or body=='') and 'compress_content' in cols: body=r['compress_content']
                    parsed=parse_content(body,r['local_type'],r['mapped_sender'])
                    sender=r['mapped_sender'] or parsed.get('sender_prefix') or f"unresolved:{r['real_sender_id']}"
                    if not r['mapped_sender'] and parsed['type']!='system': warnings.append('部分发送人无法通过 Name2Id 映射，已保留标识。')
                    stamp=r['create_time']/factor
                    server=str(r['server_id']); local=str(r['local_id'])
                    identity=f"{group['id']}:server:{server}" if server not in ('0','None','') else f"{group['id']}:{shard}:{local}"
                    msg={'id':identity,'server_id':server,'local_id':local,'timestamp':stamp,'time':window.iso(stamp),
                        'timestamp_raw':r['create_time'],'timestamp_unit':a['timestamp_unit'],'sort_seq':r['sort_seq'],
                        'sender_id':sender,'sender_name':sender_name(sender),'sources':[{'database':str(shard),'table':table,'local_id':local}],**parsed}
                    all_rows.append(msg)
            db.close(); conns.remove(db)
        if not present: raise ValueError('联系人中找到群，但所有消息分片均无该群的消息表；本地同步不足。')
        dedup={}; duplicates=0
        for m in all_rows:
            old=dedup.get(m['id'])
            if old:
                fields=['timestamp','sender_id','type_code','text','source_content_sha256']
                if all(old.get(k)==m.get(k) for k in fields):
                    old['sources'].extend(m['sources']); duplicates+=1; continue
                raise ValueError('相同服务端消息 ID 内容冲突，拒绝静默去重；需要检查数据库。')
            dedup[m['id']]=m
        messages=sorted(dedup.values(),key=lambda m:(m['timestamp'],m['sort_seq'],m['id']))
        if not messages: warnings.append('该窗口没有本地可用消息；不能据此断言群内没有讨论。')
        if limits and min(x[0] for x in limits)>window.start:
            warnings.append('本地该群最早消息晚于窗口起点，可能同步不足或群在此后才有消息。')
        for m in messages: warnings.extend(m['warnings'])
        return {'format_version':1,'data_kind':'fictional' if fixture else 'real_local',
            'account':root.parent.name,'group':group,'window':window.metadata(),
            'scope':'仅本机该账号已同步记录；不等于该群完整历史。未读取或识别图片、视频、音频内容。',
            'stats':{'message_count':len(messages),'speaker_count':len({m['sender_id'] for m in messages if m['type']!='system'}),
                'system_message_count':sum(m['type']=='system' for m in messages),
                'source_rows':source_count,'duplicates_removed':duplicates,'shards_scanned':len(shards)},
            'coverage':{'all_available_rows_read':True,'synchronization_completeness':'无法从本地数据库证明云端历史完整',
                'local_earliest':window.iso(min(x[0] for x in limits)) if limits else None,
                'local_latest':window.iso(max(x[1] for x in limits)) if limits else None,
                'snapshot_method':'整组 DB/WAL 两次只读捕获字节及文件元数据一致；无跨库事务保证',
                'databases':audit,'snapshot_sha256':{k:v['sha256'] for k,v in shots.items()}},
            'warnings':list(dict.fromkeys(warnings)),'messages':messages}
    finally:
        for c in conns: c.close()
        shots.clear()
