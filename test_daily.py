import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import daily


class DailyEntryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.day = daily.dt.datetime.now(daily.ZONE).date().isoformat()
        bundle = self.root / self.day / 'reports' / 'existing'
        bundle.mkdir(parents=True)
        self.report = bundle / 'report.md'
        self.report.write_text('GitHub Trending 中文日报', encoding='utf-8')
        manifest = {
            'identity': {'day': self.day, 'publication_policy': 'no-repeat-v1'},
            'report_sha256': hashlib.sha256(self.report.read_bytes()).hexdigest(),
        }
        (bundle / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

    def invoke(self, *args):
        with patch.object(sys, 'argv', ['daily.py', '--output-root', str(self.root), *args]):
            with contextlib.redirect_stdout(io.StringIO()):
                return daily.main()

    @patch('daily.run_child')
    def test_existing_report_does_not_generate_or_send_by_default(self, child):
        self.assertEqual(self.invoke(), 0)
        child.assert_not_called()
        status = json.loads((self.root / self.day / 'automation' / 'run-status.json').read_text())
        self.assertEqual(status['status'], 'generated')

    @patch('daily.run_child', return_value={'status': 'sent'})
    def test_delivery_requires_explicit_flag(self, child):
        self.assertEqual(self.invoke('--send'), 0)
        self.assertIn('send_report.py', ' '.join(child.call_args.args[0]))
        status = json.loads((self.root / self.day / 'automation' / 'run-status.json').read_text())
        self.assertEqual(status['push_status'], 'sent')

    def test_existing_report_hash_is_checked(self):
        self.report.write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'hash mismatch'):
            daily.existing_report(self.root / self.day, self.day)


if __name__ == '__main__':
    unittest.main()
