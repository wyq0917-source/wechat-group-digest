"""Independent synthetic SQLCipher encoder using system SQLite's reserve bytes.
Does not use the production decryption routine to construct its oracle.
"""
import ctypes,ctypes.util,hashlib,hmac,sqlite3,struct,tempfile,unittest
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from wechat_report.crypto import open_database,AuthenticationError
from test_crypto import make_wal

def sqlite_fixture(path,text):
    lib=ctypes.CDLL(ctypes.util.find_library('sqlite3'))
    lib.sqlite3_open.argtypes=[ctypes.c_char_p,ctypes.POINTER(ctypes.c_void_p)]
    lib.sqlite3_file_control.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_int,ctypes.c_void_p]
    lib.sqlite3_exec.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p]
    lib.sqlite3_close.argtypes=[ctypes.c_void_p]
    db=ctypes.c_void_p();assert lib.sqlite3_open(str(path).encode(),ctypes.byref(db))==0
    try:
        reserve=ctypes.c_int(80)
        assert lib.sqlite3_file_control(db,b'main',38,ctypes.byref(reserve))==0
        sql="PRAGMA page_size=4096; CREATE TABLE messages(body TEXT); INSERT INTO messages VALUES ('"+text+"');"
        assert lib.sqlite3_exec(db,sql.encode(),None,None,None)==0
    finally:lib.sqlite3_close(db)
    data=path.read_bytes();assert data[20]==80
    return data

def encrypt(raw,password,salt):
    key=hashlib.pbkdf2_hmac('sha512',password,salt,256000,32)
    mac=hashlib.pbkdf2_hmac('sha512',key,bytes(x^58 for x in salt),2,32)
    result=b''
    for offset in range(0,len(raw),4096):
        n=offset//4096+1;page=raw[offset:offset+4096];start=16 if n==1 else 0
        iv=bytes([n])*16
        cipher=Cipher(algorithms.AES(key),modes.CBC(iv)).encryptor()
        body=cipher.update(page[start:4016])+cipher.finalize()+iv
        result+=(salt if n==1 else b'')+body+hmac.digest(mac,body+struct.pack('<I',n),'sha512')
    return result

class EncryptedTests(unittest.TestCase):
    def test_full_database_and_encrypted_committed_wal(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);password=b'p'*32;salt=b's'*16
            before=encrypt(sqlite_fixture(p/'before.db','旧值'),password,salt)
            after=encrypt(sqlite_fixture(p/'after.db','虚构已提交消息'),password,salt)
            pages=[(i//4096+1,0,after[i:i+4096]) for i in range(0,len(after),4096)]
            pages[-1]=(pages[-1][0],len(after)//4096,pages[-1][2])
            wal=make_wal(pages+[(2,0,before[4096:8192])])
            conn,audit=open_database({'db':before,'wal':wal},password)
            try:self.assertEqual(conn.execute('select body from messages').fetchone()[0],'虚构已提交消息')
            finally:conn.close()
            self.assertEqual(audit['uncommitted_frames'],1)
            with self.assertRaises(AuthenticationError):open_database({'db':before},b'wrong'.ljust(32,b'x'))
            self.assertEqual(set(x.name for x in p.iterdir()),{'before.db','after.db'})

if __name__=='__main__':unittest.main()
