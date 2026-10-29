import argparse
import importlib.util
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('skill_launcher',Path(__file__).resolve().parents[1]/'skills/wechat-group-digest/scripts/start_capture.py')
launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)

class SkillLauncherTests(unittest.TestCase):
    def fixture(self, root):
        project=root/'Project with spaces'
        for name in ['.venv/bin/python','wechat_report/cli.py','.runtime/WeChat-reader.app/Contents/Info.plist']:
            p=project/name;p.parent.mkdir(parents=True,exist_ok=True);p.touch()
        db=root/'Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/account_a/db_storage/contact/contact.db'
        db.parent.mkdir(parents=True);db.touch()
        return argparse.Namespace(project=project,group='测试群',group_id=None,account=None,hours=24,start=None,end=None,timezone='America/Los_Angeles',launch=False)

    def test_prepare_quotes_group_and_does_not_launch(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);args=self.fixture(root)
            args.group="群 ' $(touch /tmp/never-run) `echo nope`"
            with patch.object(launcher.Path,'home',return_value=root):result=launcher.prepare(args)
            script=Path(result['launcher']).read_text()
            command=next(line for line in script.splitlines() if line.startswith('sudo '))
            parsed=shlex.split(command)
            self.assertEqual(parsed[parsed.index('--group')+1],args.group)
            self.assertFalse(result['launched'])
            self.assertFalse(Path(result['status_log']).exists())
            self.assertEqual(Path(result['launcher']).stat().st_mode & 0o777,0o700)

    def test_ambiguous_accounts_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);args=self.fixture(root)
            db=root/'Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/account_b/db_storage/contact/contact.db'
            db.parent.mkdir(parents=True);db.touch()
            with patch.object(launcher.Path,'home',return_value=root):
                with self.assertRaisesRegex(ValueError,'唯一账号'):launcher.prepare(args)
                args.account='account_b'
                self.assertEqual(launcher.prepare(args)['account'],'account_b')

    def test_invalid_window_rejected_before_launcher(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);args=self.fixture(root);args.start='2026-10-28T09:00:00'
            with self.assertRaisesRegex(ValueError,'同时'):launcher.prepare(args)
            args.end='2026-10-29T09:00:00'
            with self.assertRaisesRegex(ValueError,'偏移'):launcher.prepare(args)
            self.assertFalse(list((args.project/'.runtime').glob('skill-capture-*')))

    def test_custom_window_is_forwarded_exactly(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);args=self.fixture(root)
            args.start='2026-10-27T09:00:00+08:00';args.end='2026-10-28T09:00:00+08:00';args.timezone='Asia/Shanghai';args.group_id='123@chatroom'
            with patch.object(launcher.Path,'home',return_value=root):result=launcher.prepare(args)
            parsed=shlex.split(next(line for line in Path(result['launcher']).read_text().splitlines() if line.startswith('sudo ')))
            self.assertEqual(parsed[parsed.index('--start')+1],args.start)
            self.assertNotIn('--hours',parsed)
            self.assertEqual(parsed[parsed.index('--group-id')+1],args.group_id)
