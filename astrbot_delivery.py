"""Optional AstrBot OpenAPI delivery with durable per-report receipts."""
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request


class DeliveryError(Exception):
    pass


def settings_from_env():
    values = [os.environ.get(key, '').strip() for key in ('ASTRBOT_API_URL', 'ASTRBOT_API_KEY', 'ASTRBOT_TARGET_UMO')]
    if not any(values):
        return None
    if not all(values):
        raise DeliveryError('ASTRBOT_API_URL, ASTRBOT_API_KEY, and ASTRBOT_TARGET_UMO must be set together')
    base_url, api_key, umo = values
    if not base_url.startswith(('https://', 'http://localhost:', 'http://127.0.0.1:')):
        raise DeliveryError('AstrBot URL must use HTTPS or local HTTP')
    path = os.environ.get('ASTRBOT_MESSAGE_PATH', '/api/v1/im/messages')
    if not path.startswith('/') or path.startswith('//'):
        raise DeliveryError('ASTRBOT_MESSAGE_PATH must be an absolute API path')
    return base_url.rstrip('/') + path, api_key, umo


def chunks(text, max_chars=1800):
    if max_chars < 1:
        raise ValueError('max_chars must be positive')
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]


def write_receipt(path, value):
    temp = path.with_suffix('.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def send_chunk(endpoint, api_key, umo, message, timeout, attempts=3):
    payload = json.dumps({'umo': umo, 'message': message}, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(endpoint, data=payload, method='POST', headers={
        'X-API-Key': api_key, 'Content-Type': 'application/json'})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise DeliveryError('AstrBot response too large; delivery status uncertain')
                try:
                    result = json.loads(raw)
                except (UnicodeError, ValueError) as exc:
                    raise DeliveryError('AstrBot returned invalid JSON; delivery status uncertain') from exc
                if not isinstance(result, dict) or result.get('status') != 'ok' or 'data' not in result:
                    raise DeliveryError('AstrBot did not confirm success; delivery status uncertain')
                return
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 502, 503, 504) or attempt == attempts - 1:
                raise DeliveryError(f'AstrBot HTTP {exc.code}; delivery status uncertain') from exc
        except (TimeoutError, urllib.error.URLError) as exc:
            if attempt == attempts - 1:
                raise DeliveryError('AstrBot network timeout; delivery status uncertain') from exc
        if attempt < attempts - 1:
            time.sleep(2 ** attempt)


def deliver(report, state_dir, timeout=15):
    config = settings_from_env()
    if config is None:
        return {'status': 'not_configured'}
    endpoint, api_key, umo = config
    raw = Path(report).read_bytes()
    text = raw.decode('utf-8-sig')
    if not text.strip():
        raise DeliveryError('Report is empty')
    destination = Path(state_dir)
    destination.mkdir(parents=True, exist_ok=True)
    target_hash = hashlib.sha256((endpoint + '\0' + umo).encode('utf-8')).hexdigest()
    identity = hashlib.sha256(raw + b'\0' + target_hash.encode('ascii')).hexdigest()
    receipt_path = destination / f'astrbot-{identity}.json'
    lock = destination / f'astrbot-{identity}.lock'
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise DeliveryError('AstrBot delivery is already running; inspect its lock') from exc
    try:
        parts = chunks(text)
        if receipt_path.exists():
            receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
            if receipt.get('report_sha256') != hashlib.sha256(raw).hexdigest() or receipt.get('target_sha256') != target_hash:
                raise DeliveryError('AstrBot receipt does not match report or destination')
            if receipt.get('status') == 'success':
                return {'status': 'already_sent', 'receipt': str(receipt_path)}
            if receipt.get('status') == 'uncertain':
                raise DeliveryError('Previous AstrBot delivery is uncertain; inspect before retrying')
        else:
            receipt = {'report_sha256': hashlib.sha256(raw).hexdigest(),
                       'target_sha256': target_hash,
                       'status': 'pending', 'completed_parts': 0, 'parts': len(parts)}
        for part in parts[receipt['completed_parts']:]:
            receipt['status'] = 'uncertain'
            write_receipt(receipt_path, receipt)
            send_chunk(endpoint, api_key, umo, part, timeout)
            receipt['completed_parts'] += 1
            receipt['status'] = 'pending'
            write_receipt(receipt_path, receipt)
        receipt['status'] = 'success'
        write_receipt(receipt_path, receipt)
        return {'status': 'sent', 'receipt': str(receipt_path)}
    finally:
        lock.rmdir()
