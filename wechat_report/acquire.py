"""Capture a 32-byte PBKDF input through LLDB, only in memory.

No hard-coded WeChat addresses. Requires a user-authorized debug-capable
WeChat signature. Never changes signing/SIP, launches an app, or logs keys.
"""
import os
import plistlib
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from .crypto import derive_keys, decrypt_page, AuthenticationError

DEFAULT_BASE=Path.home()/'Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files'

def roots(): return sorted(DEFAULT_BASE.glob('*/db_storage'))

def select_root(account=None):
    found=roots()
    if account: found=[p for p in found if p.parent.name==account]
    if len(found)!=1: raise ValueError('需要 --account 精确选择账号：'+', '.join(p.parent.name for p in found))
    return found[0]

def preflight(app=Path('/Applications/WeChat.app')):
    app=Path(app).resolve()
    with (app/'Contents/Info.plist').open('rb') as f: info=plistlib.load(f)
    if info.get('CFBundleIdentifier')!='com.tencent.xinWeChat':raise ValueError('应用不是微信 bundle')
    signature=subprocess.run(['codesign','-dv','--verbose=4',str(app)],capture_output=True,text=True).stderr
    pid=subprocess.run(['pgrep','-x','WeChat'],capture_output=True,text=True)
    return {'macos':subprocess.check_output(['sw_vers','-productVersion'],text=True).strip(),
        'architecture':os.uname().machine,'wechat_version':info.get('CFBundleShortVersionString'),
        'wechat_build':info.get('CFBundleVersion'),'hardened_runtime':'runtime)' in signature,'app_path':str(app),
        'process_ids':[int(x) for x in pid.stdout.split() if x.isdigit()],
        'accounts':[p.parent.name for p in roots()],
        'capture_requires':'debug-capable app signature + debugger authorization + login event',
        'real_read_verified':False}

CALLBACK='''import os, socket
def status(value):
    s=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
    s.sendto(value,os.environ["WXREPORT_CAPTURE_SOCKET"])
    s.close()
def ready(debugger):
    import lldb
    target=debugger.GetSelectedTarget()
    process=target.GetProcess()
    if not process.IsValid() or process.GetState()!=lldb.eStateStopped:
        status(b"WXREPORT_ATTACH_FAILED")
    elif target.FindBreakpointByID(1).GetNumLocations()==0:
        status(b"WXREPORT_SYMBOL_MISSING")
    else:
        status(b"WXREPORT_READY")
def capture(frame, bp_loc, internal_dict):
    length=frame.FindRegister("x2").GetValueAsUnsigned()
    if length != 32: return False
    address=frame.FindRegister("x1").GetValueAsUnsigned()
    import lldb
    err=lldb.SBError()
    data=frame.GetThread().GetProcess().ReadMemory(address,32,err)
    if err.Success() and len(data)==32:
        try:
            s=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
            s.sendto(data,os.environ["WXREPORT_CAPTURE_SOCKET"])
            s.close()
        except OSError: pass
    return False
'''

def capture_status(data):
    if data==b'WXREPORT_READY':return 'ready'
    if data==b'WXREPORT_ATTACH_FAILED':raise RuntimeError('LLDB 无法附加微信；请确认系统开发者工具授权和重签状态。')
    if data==b'WXREPORT_SYMBOL_MISSING':raise RuntimeError('CCKeyDerivationPBKDF 符号未解析；当前版本无法按已验证方法捕获。')
    return 'candidate' if len(data)==32 else 'ignore'

def capture_passphrase(root,timeout=300,app=Path('/Applications/WeChat.app')):
    app=Path(app).resolve()
    pf=preflight(app)
    if pf['hardened_runtime']:
        raise RuntimeError('微信仍有 Hardened Runtime；需要本人授权重签并重启，程序不会自动修改微信。')
    if pf['architecture']!='arm64': raise RuntimeError('捕获器当前仅验证 arm64 ABI；拒绝猜测寄存器。')
    with (Path(root)/'contact/contact.db').open('rb') as f: page=f.read(4096)
    process=None; target_pid=None; attached_at=None; ready=False; seen=set(); deadline=time.monotonic()+timeout
    def stop():
        nonlocal process
        if process and process.poll() is None:
            process.send_signal(signal.SIGINT)
            try: process.communicate('process detach\nquit\n',timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
        process=None
    with tempfile.TemporaryDirectory(prefix='wxreport-capture-') as directory:
        os.chmod(directory,0o700)
        module=Path(directory)/'wx_capture.py'; module.write_text(CALLBACK)
        sock=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
        path=str(Path(directory)/'capture.sock'); sock.bind(path); os.chmod(path,0o600); sock.settimeout(.5)
        env=dict(os.environ,WXREPORT_CAPTURE_SOCKET=path)
        try:
            print('正在连接微信调试接口，请先不要点击登录；密钥不会显示或写入文件。',flush=True)
            while time.monotonic()<deadline:
                current=subprocess.run(['pgrep','-x','WeChat'],capture_output=True,text=True)
                live={int(x) for x in current.stdout.split() if x.isdigit()}
                if target_pid and target_pid not in live:
                    stop(); target_pid=None; ready=False
                if process and attached_at and not ready and time.monotonic()-attached_at>25:
                    raise RuntimeError('25 秒内未确认调试断点就绪；LLDB 附加可能被系统阻止。请检查开发者工具授权。')
                if process is None or process.poll() is not None:
                    stop()
                    result=subprocess.run(['pgrep','-x','WeChat'],capture_output=True,text=True)
                    pids=[int(x) for x in result.stdout.split() if x.isdigit() and int(x) not in seen]
                    if len(pids)>1: raise RuntimeError('多个微信进程，拒绝猜测捕获对象。')
                    if pids:
                        pid=pids[0]
                        executable=subprocess.check_output(['ps','-p',str(pid),'-o','comm='],text=True).strip()
                        if executable!=str(app/'Contents/MacOS/WeChat'): raise RuntimeError('微信进程路径不匹配；请关闭其他微信实例并启动选定应用。')
                        seen.add(pid)
                        target_pid=pid
                        commands=Path(directory)/'capture.lldb'
                        commands.write_text(f'settings set target.preload-symbols false\ncommand script import "{module}"\nprocess attach -p {pid}\nbreakpoint set -n CCKeyDerivationPBKDF -c "$x2 == 32"\nbreakpoint command add -F wx_capture.capture 1\nscript wx_capture.ready(lldb.debugger)\nprocess continue\n')
                        process=subprocess.Popen(['xcrun','lldb','--no-lldbinit','--source',str(commands)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True,env=env)
                        attached_at=time.monotonic(); ready=False
                try: candidate=bytearray(sock.recv(64))
                except socket.timeout: continue
                status=capture_status(candidate)
                if status=='ready':
                    ready=True
                    print('调试断点已就绪：现在请在微信中登录原账号。',flush=True)
                    continue
                if status!='candidate': continue
                try:
                    key,mac=derive_keys(candidate,page[:16]); decrypt_page(page,1,key,mac)
                except AuthenticationError:
                    candidate[:]=b'\0'*len(candidate); continue
                return candidate
            raise RuntimeError('未捕获到能认证本账号数据库的密钥；可能未登录、调试权限不足或版本不兼容。')
        finally:
            stop(); sock.close()
