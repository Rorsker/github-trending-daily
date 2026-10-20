"""Offline tests for AstrBot delivery and the unattended entry point."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import astrbot_delivery as delivery
import daily
import trending


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = self.root / 'report.md'
        self.report.write_text('中文日报\n' * 800, encoding='utf-8')
        self.config = {'ASTRBOT_API_URL': 'https://astrbot.example',
                       'ASTRBOT_API_KEY': 'fake-key', 'ASTRBOT_TARGET_UMO': 'platform:GroupMessage:123'}

    def test_unconfigured_and_partial_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(delivery.deliver(self.report, self.root / 'delivery')['status'], 'not_configured')
        with patch.dict(os.environ, {'ASTRBOT_API_KEY': 'fake-key'}, clear=True):
            with self.assertRaises(delivery.DeliveryError):
                delivery.deliver(self.report, self.root / 'delivery')

    def test_send_chunks_and_idempotency(self):
        sent = []
        response = unittest.mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"status":"ok","data":{}}'
        def receive(request, timeout):
            self.assertEqual(request.full_url, 'https://astrbot.example/api/v1/im/messages')
            self.assertEqual(request.get_header('X-api-key'), 'fake-key')
            sent.append(json.loads(request.data)['message'])
            self.assertEqual(json.loads(request.data)['umo'], self.config['ASTRBOT_TARGET_UMO'])
            return response
        with patch.dict(os.environ, self.config, clear=True), patch.object(delivery.urllib.request, 'urlopen', side_effect=receive):
            result = delivery.deliver(self.report, self.root / 'delivery')
            self.assertEqual(result['status'], 'sent')
            self.assertEqual(delivery.deliver(self.report, self.root / 'delivery')['status'], 'already_sent')
        self.assertGreater(len(sent), 1)
        self.assertEqual(''.join(sent), self.report.read_bytes().decode('utf-8'))
        self.assertNotIn('fake-key', Path(result['receipt']).read_text(encoding='utf-8'))

    def test_timeout_retry_and_uncertain_receipt(self):
        with patch.dict(os.environ, self.config, clear=True), patch.object(delivery.urllib.request, 'urlopen', side_effect=TimeoutError()), patch.object(delivery.time, 'sleep') as pause:
            with self.assertRaisesRegex(delivery.DeliveryError, 'uncertain'):
                delivery.deliver(self.report, self.root / 'delivery')
            self.assertEqual(pause.call_count, 2)
            with self.assertRaisesRegex(delivery.DeliveryError, 'Previous'):
                delivery.deliver(self.report, self.root / 'delivery')

    def test_http_rejection_does_not_expose_key(self):
        error = urllib.error.HTTPError('https://astrbot.example', 401, 'unauthorized', {}, None)
        with patch.dict(os.environ, self.config, clear=True), patch.object(delivery.urllib.request, 'urlopen', side_effect=error):
            with self.assertRaises(delivery.DeliveryError) as raised:
                delivery.deliver(self.report, self.root / 'delivery')
        self.assertNotIn('fake-key', str(raised.exception))

    def test_daily_fixture_generates_without_astrbot(self):
        fixture = Path(trending.ROOT) / 'fixtures' / 'trending.html'
        repos = trending.parse_trending(fixture.read_text(encoding='utf-8'))
        analysis = {'items': [{'name': r['name'], 'summary_zh': '项目用途来自公开描述。',
                               'reason_zh': '值得关注。'} for r in repos[:5]]}
        analysis_file = self.root / 'analysis.json'
        analysis_file.write_text(json.dumps(analysis, ensure_ascii=False), encoding='utf-8')
        args = ['--output-root', str(self.root / 'data'), '--backend', 'json',
                '--analysis-file', str(analysis_file), '--html-file', str(fixture)]
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(daily.main(args), 0)
            first = json.loads(output.getvalue())
        self.assertEqual(first['delivery']['status'], 'not_configured')
        report = Path(first['report'])
        self.assertTrue(report.read_text(encoding='utf-8').startswith('GitHub Trending 中文日报｜'))
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(daily.main(args), 0)
        self.assertEqual(json.loads(output.getvalue())['report'], str(report))


if __name__ == '__main__':
    unittest.main()
