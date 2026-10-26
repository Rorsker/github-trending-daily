"""Send an existing Markdown report once, with task-local delivery receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from feishu_notifier import Credentials, FeishuError, send_text

CHUNK_SIZE = 3000


def load_credentials() -> Credentials:
    return Credentials.from_store() if os.name == "nt" else Credentials.from_environment()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def deliver(report: Path, state_dir: Path) -> dict:
    report = report.resolve(strict=True)
    raw = report.read_bytes()
    text = raw.decode("utf-8-sig")
    if not text.strip():
        raise ValueError("日报为空")
    credentials = load_credentials()
    report_hash = hashlib.sha256(raw).hexdigest()
    recipient_hash = hashlib.sha256(credentials.open_id.encode("utf-8")).hexdigest()
    state_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = state_dir / f"feishu-{report_hash}.json"
    lock = state_dir / f"feishu-{report_hash}.lock"
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise RuntimeError("此日报已有发送进程或遗留锁，请检查状态") from exc
    try:
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
            if receipt.get("report_sha256") != report_hash or receipt.get("recipient_sha256") != recipient_hash:
                raise RuntimeError("回执与日报或收件人不匹配")
            if receipt.get("report_status") == "success":
                return {"status": "already_sent", "receipt": str(receipt_path),
                        "message_ids": receipt.get("message_ids") or [receipt.get("report_message_id")]}
            if receipt.get("report_status") not in (None, "pending", "sending"):
                raise RuntimeError("先前发送状态不确定，已停止自动重试以防重复")
        else:
            receipt = {"schema_version": 2, "report_sha256": report_hash,
                       "recipient_sha256": recipient_hash, "report_path": str(report),
                       "report_status": "pending", "parts": []}
        chunks = [text[i:i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
        if "parts" not in receipt:
            receipt["parts"] = []
        if any(part.get("status") != "success" for part in receipt["parts"]):
            raise RuntimeError("先前分段发送状态不确定，已停止自动重试以防重复")
        if len(receipt["parts"]) > len(chunks):
            raise RuntimeError("回执分段数超出日报内容")
        for part, chunk in zip(receipt["parts"], chunks):
            if part.get("sha256") != hashlib.sha256(chunk.encode("utf-8")).hexdigest():
                raise RuntimeError("回执分段哈希与日报内容不匹配")
        for index, chunk in enumerate(chunks[len(receipt["parts"]):], len(receipt["parts"])):
            part = {"index": index + 1, "sha256": hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
                    "status": "sending"}
            receipt["parts"].append(part)
            receipt["report_status"] = "sending"
            write_json(receipt_path, receipt)
            try:
                response = send_text(credentials, chunk)
                message_id = response.get("data", {}).get("message_id")
                if response.get("code") != 0 or not isinstance(message_id, str) or not message_id:
                    raise RuntimeError("飞书未确认 message_id，发送状态不确定")
            except FeishuError as exc:
                if exc.code is not None:
                    receipt["parts"].pop()
                    receipt["report_status"] = "pending"
                    receipt["last_rejection"] = {"code": exc.code, "at": datetime.now(timezone.utc).isoformat()}
                    write_json(receipt_path, receipt)
                raise
            part["status"] = "success"
            part["message_id"] = message_id
            part["confirmed_at"] = datetime.now(timezone.utc).isoformat()
            write_json(receipt_path, receipt)
        receipt["report_status"] = "success"
        receipt["report_bytes"] = len(raw)
        receipt["confirmed_at"] = datetime.now(timezone.utc).isoformat()
        receipt["message_ids"] = [part["message_id"] for part in receipt["parts"]]
        write_json(receipt_path, receipt)
        return {"status": "sent", "receipt": str(receipt_path), "message_ids": receipt["message_ids"]}
    finally:
        lock.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--state-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(deliver(args.report, args.state_dir), ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, FeishuError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
