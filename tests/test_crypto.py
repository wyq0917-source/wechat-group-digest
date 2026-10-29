import hashlib, hmac, os, struct, unittest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from wechat_report.crypto import decrypt_page, derive_keys, wal_frames, AuthenticationError

KEY = b'k'*32
SALT = b's'*16

def encrypted_page(n=1, text=None):
    key, mac = derive_keys(KEY, SALT)
    start = 16 if n == 1 else 0
    plain = text or b'A'*(4016-start)
    iv = b'i'*16
    enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    body = enc.update(plain)+enc.finalize()+iv
    digest = hmac.digest(mac,body+struct.pack('<I',n),'sha512')
    return (SALT if n==1 else b'')+body+digest, plain

def checksum(data, state=(0,0), endian='<'):
    a,b=state
    words=struct.unpack(endian+str(len(data)//4)+'I',data)
    for x,y in zip(words[::2],words[1::2]):
        a=(a+x+b)&0xffffffff; b=(b+y+a)&0xffffffff
    return a,b

def make_wal(frames):
    hdr=struct.pack('>6I',0x377f0682,3007000,4096,0,123,456)
    state=checksum(hdr); data=hdr+struct.pack('>2I',*state)
    for n,commit,page in frames:
        h=struct.pack('>4I',n,commit,123,456)
        state=checksum(h[:8]+page,state)
        data+=h+struct.pack('>2I',*state)+page
    return data

class CryptoTests(unittest.TestCase):
    def test_authenticated_page_and_wrong_key(self):
        page,plain=encrypted_page()
        key,mac=derive_keys(KEY,SALT)
        self.assertEqual(decrypt_page(page,1,key,mac),b'SQLite format 3\0'+plain+b'\0'*80)
        with self.assertRaises(AuthenticationError): decrypt_page(page,1,b'x'*32,b'y'*32)
        bad=bytearray(page); bad[100]^=1
        with self.assertRaises(AuthenticationError): decrypt_page(bytes(bad),1,key,mac)

    def test_wal_commit_and_checksum(self):
        page,_=encrypted_page(2)
        data=make_wal([(2,2,page),(2,0,page)])
        frames,audit=wal_frames(data)
        self.assertEqual(len(frames),1)
        self.assertEqual(audit['committed_pages'],2)
        bad=bytearray(data); bad[80]^=1
        frames,audit=wal_frames(bytes(bad))
        self.assertEqual(frames,[])
        self.assertTrue(audit['invalid_tail'])

    def test_short_wal_and_invalid_header(self):
        self.assertEqual(wal_frames(b'')[0],[])
        with self.assertRaises(ValueError): wal_frames(b'x'*32)
        page,_=encrypted_page(2)
        frames,audit=wal_frames(make_wal([(2,2,page)])+b'partial')
        self.assertEqual(len(frames),1)
        self.assertEqual(audit['trailing_bytes'],7)

if __name__=='__main__': unittest.main()
