import tempfile, unittest
from pathlib import Path
from wechat_report.snapshot import capture

class SnapshotTests(unittest.TestCase):
    def test_original_unchanged_and_no_temporary_plaintext(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'one.db').write_bytes(b'encrypted fake fixture')
            before=set(p.iterdir());original=(p/'one.db').read_bytes()
            snap=capture(p,[Path('one.db')])
            self.assertEqual(snap['one.db']['db'],original)
            self.assertEqual(set(p.iterdir()),before)
            self.assertEqual((p/'one.db').read_bytes(),original)
            with self.assertRaises(ValueError):capture(p,[Path('../escape.db')])
            self.assertEqual(set(p.iterdir()),before)

    def test_reject_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'real').write_bytes(b'x');(p/'link.db').symlink_to(p/'real')
            with self.assertRaises(OSError):capture(p,[Path('link.db')])
