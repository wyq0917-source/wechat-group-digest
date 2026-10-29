#!/usr/bin/env python3
"""Prepare a private Terminal launcher; no key handling or app signing here."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_PROJECT = Path(os.environ.get('WECHAT_REPORT_PROJECT', str(Path(__file__).resolve().parents[3])))

def prepare(args):
    project = args.project.expanduser().resolve()
    python = project / '.venv/bin/python'
    app = project / '.runtime/WeChat-reader.app'
    if not python.is_file() or not (project / 'wechat_report/cli.py').is_file():
        raise ValueError('找不到已验证项目或 Python 环境；请提供 --project，勿重新猜测数据库实现。')
    if not (app / 'Contents/Info.plist').is_file():
        raise ValueError('已授权的微信副本不存在；先检查项目 README，不自动重签应用。')
    if not args.group.strip() or any(ord(c) < 32 for c in args.group):
        raise ValueError('群名必须完整非空，且不能包含控制字符。')
    ZoneInfo(args.timezone)
    if bool(args.start) != bool(args.end):
        raise ValueError('自定义时间必须同时给出 --start 和 --end。')
    if args.start:
        dates = [datetime.fromisoformat(s) for s in [args.start,args.end]]
        if any(d.tzinfo is None for d in dates) or dates[0] >= dates[1]:
            raise ValueError('起止时间需带 UTC 偏移且起点早于终点。')
    base = Path.home() / 'Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files'
    accounts = sorted(p for p in base.glob('*/db_storage') if (p/'contact/contact.db').is_file())
    if args.account:
        accounts = [p for p in accounts if p.parent.name == args.account]
    if len(accounts) != 1:
        raise ValueError('请用 --account 选择唯一账号，候选：'+', '.join(p.parent.name for p in accounts))
    command = ['sudo',str(python),'-m','wechat_report.cli','capture-export',
               '--app',str(app),'--root',str(accounts[0]),'--group',args.group,
               '--timezone',args.timezone]
    if args.start: command += ['--start',args.start,'--end',args.end]
    else: command += ['--hours',str(args.hours)]
    if args.group_id: command += ['--group-id',args.group_id]
    runtime=project/'.runtime';runtime.mkdir(mode=0o700,exist_ok=True)
    run=Path(tempfile.mkdtemp(prefix='skill-capture-',dir=runtime));os.chmod(run,0o700)
    launcher=run/'capture.command';log=run/'status.log'
    q=shlex.quote
    script='''#!/bin/zsh
set -u
umask 077
cd PROJECT || exit 1
exec > >(tee -a LOG) 2>&1
osascript -e 'tell application id "com.tencent.xinWeChat" to quit'
for attempt in {1..30}; do
  if ! pgrep -x WeChat >/dev/null; then break; fi
  sleep 1
done
if pgrep -x WeChat >/dev/null; then
  echo '微信未退出，请手动完成退出；本次尚未捕获。'
  read -r '?按回车关闭。'
  exit 1
fi
open -n APP || exit 1
echo '在 Password: 后输入 Mac 管理员密码，输入不回显。不要在普通命令提示符输入密码。'
echo '先不要登录微信；等出现“调试断点已就绪”后，再登录原账号。'
COMMAND
result=$?
if [[ $result -eq 0 ]]; then
  echo '导出已完成。返回 Codex，由当前会话读取全部批次并生成 HTML 和 PNG。'
else
  echo "捕获或导出失败（退出码 $result）；不要发送密码，返回 Codex 检查状态日志。"
fi
read -r '?按回车关闭。'
exit $result
'''
    # Replace entire sentinel lines, so user values are never reinterpreted as template tokens.
    replacements={'cd PROJECT || exit 1':f'cd {q(str(project))} || exit 1',
                  'exec > >(tee -a LOG) 2>&1':f'exec > >(tee -a {q(str(log))}) 2>&1',
                  'open -n APP || exit 1':f'open -n {q(str(app))} || exit 1',
                  'COMMAND':shlex.join(command)}
    launcher.write_text('\n'.join(replacements.get(line,line) for line in script.splitlines())+'\n')
    os.chmod(launcher,0o700)
    subprocess.run(['/bin/zsh','-n',str(launcher)],check=True)
    if args.launch: subprocess.run(['open','-a','Terminal',str(launcher)],check=True)
    return {'launcher':str(launcher),'status_log':str(log),'launched':args.launch,
            'account':accounts[0].parent.name,'group':args.group,
            'next':'等待用户在本机 Terminal 输入密码，并在断点就绪后登录；不要索取密码或密钥。'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,default=DEFAULT_PROJECT)
    parser.add_argument('--group',required=True)
    parser.add_argument('--group-id')
    parser.add_argument('--account')
    parser.add_argument('--hours',type=int,choices=[24,48,72],default=24)
    parser.add_argument('--start');parser.add_argument('--end')
    parser.add_argument('--timezone',default='UTC')
    parser.add_argument('--launch',action='store_true',help='打开 Terminal 执行；不加此参数只准备并检查脚本')
    args=parser.parse_args()
    try: print(json.dumps(prepare(args),ensure_ascii=False,indent=2))
    except (ValueError,OSError,subprocess.CalledProcessError) as e: parser.exit(1,str(e)+'\n')

if __name__=='__main__':main()
