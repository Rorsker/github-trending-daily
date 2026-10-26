import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from feishu_notifier import Credentials, FeishuError
from send_report import deliver


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = self.root / "report.md"
        self.state = self.root / "delivery"
        self.credentials = Credentials("cli_app", "secret", "ou_person")

    @patch("send_report.send_text")
    @patch("send_report.Credentials.from_store")
    def test_chunks_are_complete_ordered_and_deduplicated(self, stored, send):
        stored.return_value = self.credentials
        text = "甲" * 3001 + "乙" * 3000 + "终"
        self.report.write_bytes(text.encode("utf-8"))
        send.side_effect = [
            {"code": 0, "data": {"message_id": f"m{i}"}} for i in range(3)
        ]
        self.assertEqual(deliver(self.report, self.state)["status"], "sent")
        self.assertEqual("".join(call.args[1] for call in send.call_args_list), text)
        self.assertEqual(deliver(self.report, self.state)["status"], "already_sent")
        self.assertEqual(send.call_count, 3)
        receipt = json.loads(next(self.state.glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(receipt["report_status"], "success")
        self.assertEqual(receipt["message_ids"], ["m0", "m1", "m2"])

    @patch("send_report.send_text")
    @patch("send_report.Credentials.from_store")
    def test_legacy_success_receipt_skips_send(self, stored, send):
        stored.return_value = self.credentials
        self.report.write_text("日报", encoding="utf-8")
        report_hash = hashlib.sha256(self.report.read_bytes()).hexdigest()
        recipient_hash = hashlib.sha256(self.credentials.open_id.encode()).hexdigest()
        self.state.mkdir()
        (self.state / f"feishu-{report_hash}.json").write_text(json.dumps({
            "report_sha256": report_hash, "recipient_sha256": recipient_hash,
            "report_status": "success", "report_message_id": "old-id",
        }), encoding="utf-8")
        self.assertEqual(deliver(self.report, self.state)["status"], "already_sent")
        send.assert_not_called()

    @patch("send_report.send_text", side_effect=FeishuError("network unknown"))
    @patch("send_report.Credentials.from_store")
    def test_ambiguous_failure_cannot_auto_retry(self, stored, send):
        stored.return_value = self.credentials
        self.report.write_text("日报", encoding="utf-8")
        with self.assertRaises(FeishuError):
            deliver(self.report, self.state)
        with self.assertRaisesRegex(RuntimeError, "状态不确定"):
            deliver(self.report, self.state)
        self.assertEqual(send.call_count, 1)


if __name__ == "__main__":
    unittest.main()
