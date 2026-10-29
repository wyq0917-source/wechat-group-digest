import argparse
import json
import os
import pwd
import resource
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from .acquire import preflight, select_root, capture_passphrase
from .reader import export, Window
from .report import save_json, write_export, render_report, batch_manifest

PROJECT=Path(__file__).resolve().parents[1]

def load(path): return json.loads(Path(path).read_text(encoding='utf-8'))

def make_window(args):
    tz=ZoneInfo(args.timezone)
    def parse(text):
        d=datetime.fromisoformat(text)
        if d.tzinfo is None: raise ValueError('自定义时间必须带明确时区偏移，例如 2026-10-28T08:00:00-07:00')
        return d.timestamp()
    end=parse(args.end) if args.end else datetime.now(tz).timestamp()
    start=parse(args.start) if args.start else end-args.hours*3600
    return Window(start,end,args.timezone)

def render_png(directory):
    config=load(PROJECT/'runtime.local.json')
    subprocess.run([config['node'],str(PROJECT/'scripts/render.cjs'),str(directory)],check=True)

def output_dir():
    parent=PROJECT/'outputs'; parent.mkdir(exist_ok=True,mode=0o700)
    return Path(tempfile.mkdtemp(prefix=datetime.now().strftime('%Y%m%d-%H%M%S-'),dir=parent))

def main(argv=None):
    os.umask(0o077)
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    parser=argparse.ArgumentParser(description='本地微信记录读取；总结由当前 Codex 会话完成，无独立模型调用。')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('doctor');p.add_argument('--app',type=Path,default=Path('/Applications/WeChat.app'))
    for cmd in ['export','capture-export']:
        p=sub.add_parser(cmd)
        p.add_argument('--group',help='完整群名；缺省时交互询问')
        p.add_argument('--group-id');p.add_argument('--account');p.add_argument('--root',type=Path)
        p.add_argument('--app',type=Path,default=Path('/Applications/WeChat.app'))
        p.add_argument('--hours',type=int,choices=[24,48,72],default=24)
        p.add_argument('--start');p.add_argument('--end');p.add_argument('--timezone',default='UTC')
        if cmd=='export':p.add_argument('--passphrase-stdin',action='store_true',help='仅接受安全管道的32字节二进制，不可把密钥粘贴到聊天或命令行')
    p=sub.add_parser('render');p.add_argument('directory',type=Path)
    p=sub.add_parser('verify');p.add_argument('directory',type=Path)
    sub.add_parser('demo')
    p=sub.add_parser('batch');p.add_argument('directory',type=Path);p.add_argument('number',type=int)
    args=parser.parse_args(argv)
    if args.command=='doctor':
        print(json.dumps(preflight(args.app),ensure_ascii=False,indent=2));return
    if args.command=='demo':
        from .demo import run
        directory=run(output_dir);render_png(directory);print(directory);return
    if args.command in ('render','verify'):
        from .report import validate_report
        data=load(args.directory/'messages.json'); report=load(args.directory/'report.json')
        validate_report(data,report)
        if args.command=='render':render_report(data,report,args.directory);render_png(args.directory)
        else:print(json.dumps({'reference_ids_valid':True,'batch_coverage_valid':True,'stats_valid':True,'semantic_support':'需总结者逐条人工复核'},ensure_ascii=False))
        return
    if args.command=='batch':
        manifest=load(args.directory/'batches/manifest.json')
        if args.number<1 or args.number>len(manifest):raise ValueError('批次编号超出范围')
        print((args.directory/'batches'/manifest[args.number-1]['file']).read_text());return
    group=args.group or input('请输入完整微信群名：').strip()
    root=args.root or select_root(args.account)
    window=make_window(args)  # freeze once, before capture/login wait
    print('统计窗口：'+json.dumps(window.metadata(),ensure_ascii=False),flush=True)
    secret=None
    try:
        if args.command=='capture-export':
            secret=capture_passphrase(root,app=args.app)
            # Root is needed only for debugger attachment; export as original user.
            if os.getuid()==0:
                uid=(root/'contact/contact.db').stat().st_uid
                if uid==0:raise ValueError('拒绝将 root 数据目录视为用户账号')
                user=pwd.getpwuid(uid);os.setgroups([]);os.setgid(user.pw_gid);os.setuid(uid)
        elif args.passphrase_stdin:
            if sys.stdin.isatty():raise ValueError('拒绝从可回显终端接收密钥；只接受安全管道')
            secret=bytearray(sys.stdin.buffer.read(33))
            if len(secret)!=32:raise ValueError('管道必须恰好提供32字节二进制密钥')
        data=export(root,group,window,secret,group_id=args.group_id)
        data['client_environment']=preflight(args.app)
        data['client_environment']['real_read_verified']=True
        directory=output_dir();write_export(data,directory)
        print(json.dumps({'export_directory':str(directory),'stats':data['stats'],'status':'exported_awaiting_Codex_summary'},ensure_ascii=False,indent=2))
    finally:
        if secret is not None:secret[:]=b'\0'*len(secret)

if __name__=='__main__':
    def interrupted(_signum,_frame):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)
    try:main()
    except (ValueError,RuntimeError,OSError,subprocess.CalledProcessError) as e:
        print('错误：'+str(e),file=sys.stderr);sys.exit(1)
    except KeyboardInterrupt:
        print('已中止并清理临时捕获文件。',file=sys.stderr);sys.exit(130)
