"""Stable, read-only whole-set capture. Ciphertext stays in RAM."""
import hashlib
import os
import stat
import time
from pathlib import Path

def _read(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode): raise ValueError('Not a regular database file')
        chunks=[]
        while chunk:=os.read(fd,1024*1024): chunks.append(chunk)
        after=os.fstat(fd)
        signature=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if signature(before)!=signature(after): raise RuntimeError('Database changed during snapshot')
        return b''.join(chunks),signature(after)
    finally: os.close(fd)

def capture(root, relatives, retries=4):
    root=Path(root)
    if root.is_symlink(): raise ValueError('Symlink database root refused')
    root=root.resolve(strict=True)
    paths=[]
    for relative in relatives:
        p=root/relative
        if '..' in Path(relative).parts or not p.resolve().is_relative_to(root):
            raise ValueError('Unsafe database path')
        paths.extend([p,Path(str(p)+'-wal')])
    def read_set():
        result={}
        for p in paths:
            if p.name.endswith('-wal') and not p.exists():
                result[p]=(b'',None)
            else: result[p]=_read(p)
        return result
    for attempt in range(retries):
        try:
            first=read_set(); second=read_set()
            if first==second:
                return {str(r):{'db':first[root/r][0],
                    'wal':first[Path(str(root/r)+'-wal')][0],
                    'sha256':hashlib.sha256(first[root/r][0]+first[Path(str(root/r)+'-wal')][0]).hexdigest()}
                    for r in relatives}
        except (RuntimeError,FileNotFoundError): pass
        time.sleep(.15*(attempt+1))
    raise RuntimeError('数据库持续变化，未生成一致快照；请暂时停止操作微信后重试。')
