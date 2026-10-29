"""SQLCipher 4 profile: authenticated pages; SQLite WAL checksums and commits.

Profile verified against GreenBubbles 69f19c7 SQLCipherKeyVerifier and Zetetic
design. WAL parsing follows sqlite.org/fileformat2.html, not upstream's
salt-only WAL loop. Never writes a plaintext database to disk.
"""
import hashlib
import hmac
import sqlite3
import struct
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

PAGE = 4096

class AuthenticationError(ValueError):
    pass

def derive_keys(passphrase, salt):
    if len(passphrase) != 32 or len(salt) != 16:
        raise ValueError('Expected 32-byte passphrase and 16-byte salt')
    key = hashlib.pbkdf2_hmac('sha512', passphrase, salt, 256000, 32)
    mac = hashlib.pbkdf2_hmac('sha512', key, bytes(x ^ 0x3a for x in salt), 2, 32)
    return key, mac

def decrypt_page(page, number, key, mac):
    if len(page) != PAGE or number < 1:
        raise ValueError('Invalid page length or number')
    offset = 16 if number == 1 else 0
    expected = hmac.digest(mac, page[offset:4032] + struct.pack('<I',number), 'sha512')
    if not hmac.compare_digest(expected,page[4032:]):
        raise AuthenticationError(f'Page {number} authentication failed; no output accepted')
    decryptor=Cipher(algorithms.AES(key),modes.CBC(page[4016:4032])).decryptor()
    body=decryptor.update(page[offset:4016])+decryptor.finalize()
    return (b'SQLite format 3\0' if number==1 else b'')+body+b'\0'*80

def _checksum(data, state, endian):
    a,b=state
    words=struct.unpack(endian+str(len(data)//4)+'I',data)
    for x,y in zip(words[::2],words[1::2]):
        a=(a+x+b)&0xffffffff
        b=(b+y+a)&0xffffffff
    return a,b

def wal_frames(data):
    audit={'valid_frames':0,'applied_frames':0,'committed_pages':None,
           'invalid_tail':False,'trailing_bytes':0,'uncommitted_frames':0}
    if not data:
        return [],audit
    if len(data)<32:
        raise ValueError('Nonempty WAL has incomplete header')
    magic,version,size,_,s1,s2,c1,c2=struct.unpack('>8I',data[:32])
    if magic not in (0x377f0682,0x377f0683) or size!=PAGE or version!=3007000:
        raise ValueError('Unsupported WAL header/page size')
    endian='<' if magic==0x377f0682 else '>'
    state=_checksum(data[:24],(0,0),endian)
    if state!=(c1,c2):
        raise ValueError('WAL header checksum mismatch')
    frames=[]; last_commit=0
    audit['trailing_bytes']=(len(data)-32)%(PAGE+24)
    for offset in range(32,len(data)-PAGE-23,PAGE+24):
        h=data[offset:offset+24]; page=data[offset+24:offset+24+PAGE]
        n,commit,a,b,c,d=struct.unpack('>6I',h)
        next_state=_checksum(h[:8]+page,state,endian)
        if n==0 or n>1_000_000 or commit>1_000_000 or (a,b)!=(s1,s2) or next_state!=(c,d):
            audit['invalid_tail']=True
            break  # SQLite uses only the contiguous valid prefix, never skips a frame.
        state=next_state
        frames.append((n,page))
        if commit:
            last_commit=len(frames); audit['committed_pages']=commit
    audit['valid_frames']=len(frames)
    audit['uncommitted_frames']=len(frames)-last_commit
    audit['applied_frames']=last_commit
    return frames[:last_commit],audit

def open_database(snapshot, passphrase=None):
    raw=snapshot['db']; wal=snapshot.get('wal',b'')
    if len(raw)<PAGE or len(raw)%PAGE:
        raise ValueError('Database does not match the pinned 4096-byte profile')
    plain=raw.startswith(b'SQLite format 3\0')
    if not plain and passphrase is None:
        raise AuthenticationError('Encrypted database needs an in-memory passphrase')
    key=mac=None
    if not plain: key,mac=derive_keys(passphrase,raw[:16])
    output=bytearray(len(raw)); conn=None
    try:
        zero_pages=0
        for offset in range(0,len(raw),PAGE):
            page=raw[offset:offset+PAGE]; n=offset//PAGE+1
            if not plain and n>1 and not any(page):
                zero_pages+=1; continue
            output[offset:offset+PAGE]=page if plain else decrypt_page(page,n,key,mac)
        frames,audit=wal_frames(wal)
        for n,page in frames:
            p=page if plain else decrypt_page(page,n,key,mac)
            if n*PAGE>len(output): output.extend(b'\0'*(n*PAGE-len(output)))
            output[(n-1)*PAGE:n*PAGE]=p
        if audit['committed_pages']:
            target=audit['committed_pages']*PAGE
            if target>len(output): raise ValueError('Committed WAL references missing pages')
            del output[target:]
        if output[16:18]!=b'\x10\0': raise ValueError('Unexpected decrypted page size')
        if not plain and output[20]!=80: raise ValueError('Unexpected SQLCipher reserve size')
        # deserialize has no WAL sidecar; commit overlay is already materialized.
        output[18:20]=b'\x01\x01'
        conn=sqlite3.connect(':memory:')
        conn.deserialize(bytes(output))
        conn.execute('PRAGMA query_only=ON')
        conn.execute('PRAGMA temp_store=MEMORY')
        check=conn.execute('PRAGMA integrity_check').fetchall()
        if check!=[('ok',)]: raise ValueError('SQLite integrity_check failed')
        conn.row_factory=sqlite3.Row
        audit.update({'encrypted':not plain,'integrity_check':'ok','zero_pages':zero_pages})
        return conn,audit
    except BaseException:
        if conn: conn.close()
        raise
    finally:
        output[:]=b'\0'*len(output)
        key=mac=None  # Python cannot guarantee zeroing immutable internal copies.
