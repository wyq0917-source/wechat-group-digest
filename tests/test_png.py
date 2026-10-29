import json,struct,unittest
from pathlib import Path

class PNGTests(unittest.TestCase):
    def test_rendered_dimensions_match_manifest(self):
        manifests=list((Path(__file__).resolve().parents[1]/'outputs').glob('*/render-manifest.json'))
        if not manifests:self.skipTest('Run ./wxreport demo first')
        for path in manifests:
            manifest=json.loads(path.read_text())
            last=0
            for entry in manifest['images']:
                data=(path.parent/entry['file']).read_bytes()
                self.assertEqual(data[:8],b'\x89PNG\r\n\x1a\n')
                self.assertEqual(struct.unpack('>II',data[16:24]),(entry['width'],entry['height']))
                self.assertEqual(entry['css_start'],last)
                last=entry['css_end']
                if len(manifest['images'])>1:self.assertGreater(entry['height'],200,'避免仅剩空白/页脚的极短尾图')
