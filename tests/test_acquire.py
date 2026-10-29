import unittest
from wechat_report.acquire import capture_status

class AcquireTests(unittest.TestCase):
    def test_ready_is_distinct_from_secret(self):
        self.assertEqual(capture_status(b'WXREPORT_READY'),'ready')
        with self.assertRaises(RuntimeError):capture_status(b'WXREPORT_ATTACH_FAILED')
        with self.assertRaises(RuntimeError):capture_status(b'WXREPORT_SYMBOL_MISSING')
        self.assertEqual(capture_status(b'x'*32),'candidate')
        self.assertEqual(capture_status(b'junk'),'ignore')
