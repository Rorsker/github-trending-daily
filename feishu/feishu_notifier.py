"""Small Feishu tenant-token and application-bot text notifier."""
from __future__ import annotations

import json
import os
import ctypes
import urllib.error
import urllib.request
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

BASE_URL = os.getenv("FEISHU_BASE_URL", "https://open.feishu.cn")
STORE_PATH = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "FeishuNotifier" / "credentials.dat"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _dpapi(data: bytes, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        raise FeishuError("DPAPI requires Windows")
    source = ctypes.create_string_buffer(data)
    input_blob = _DataBlob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_byte)))
    output_blob = _DataBlob()
    crypt = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    # Both functions accept optional metadata, entropy and prompts. Only the
    # current user's DPAPI key is used; CRYPTPROTECT_LOCAL_MACHINE is absent.
    crypt.argtypes = [ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p,
                      ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                      ctypes.POINTER(_DataBlob)]
    crypt.restype = wintypes.BOOL
    flags = 0 if decrypt else 0x1  # CRYPTPROTECT_UI_FORBIDDEN
    if not crypt(ctypes.byref(input_blob), None, None, None, None, flags, ctypes.byref(output_blob)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        local_free = ctypes.windll.kernel32.LocalFree
        local_free.argtypes = [ctypes.c_void_p]
        local_free.restype = ctypes.c_void_p
        local_free(output_blob.pbData)


class FeishuError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None, http_status: int | None = None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


@dataclass(frozen=True)
class Credentials:
    app_id: str
    app_secret: str
    open_id: str

    @classmethod
    def from_store(cls) -> "Credentials":
        try:
            values = json.loads(_dpapi(STORE_PATH.read_bytes(), decrypt=True).decode("utf-8"))
            return cls(*(values[key] for key in ("app_id", "app_secret", "open_id")))
        except FileNotFoundError as exc:
            raise FeishuError("未找到当前用户的飞书凭据；运行 configure.ps1") from exc
        except (OSError, ValueError, KeyError, UnicodeError) as exc:
            raise FeishuError("当前用户无法读取飞书 DPAPI 凭据") from exc

    def save_to_store(self) -> None:
        STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps({"app_id": self.app_id, "app_secret": self.app_secret,
                           "open_id": self.open_id}, ensure_ascii=False).encode("utf-8")
        encrypted = _dpapi(data)
        temporary = STORE_PATH.with_name(STORE_PATH.name + ".tmp")
        try:
            temporary.write_bytes(encrypted)
            os.replace(temporary, STORE_PATH)
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def from_environment(cls) -> "Credentials":
        values = {name: os.getenv(name, "").strip() for name in ("FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_OPEN_ID")}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise FeishuError("缺少环境变量: " + ", ".join(missing))
        return cls(values["FEISHU_APP_ID"], values["FEISHU_APP_SECRET"], values["FEISHU_OPEN_ID"])


def _post(path: str, payload: dict, headers: dict | None = None) -> dict:
    request = urllib.request.Request(
        BASE_URL + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise FeishuError(f"飞书 HTTP 错误 {exc.code}: {detail[:300]}", http_status=exc.code) from exc
    except urllib.error.URLError as exc:
        raise FeishuError(f"飞书网络错误: {exc.reason}") from exc
    try:
        result = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeishuError(f"飞书返回了无效 JSON (HTTP {status})") from exc
    if status < 200 or status >= 300:
        raise FeishuError(f"飞书 HTTP 错误 {status}: {result}", http_status=status)
    if result.get("code", 0) != 0:
        code = result.get("code")
        msg = result.get("msg", "未知业务错误")
        raise FeishuError(f"飞书业务错误 {code}: {msg}", code=code)
    return result


def get_tenant_access_token(credentials: Credentials) -> str:
    result = _post("/open-apis/auth/v3/tenant_access_token/internal", {
        "app_id": credentials.app_id, "app_secret": credentials.app_secret,
    })
    token = result.get("tenant_access_token")
    if not token:
        raise FeishuError("飞书未返回 tenant_access_token")
    return token


def send_text(credentials: Credentials, text: str) -> dict:
    if not text.strip():
        raise ValueError("消息内容不能为空")
    token = get_tenant_access_token(credentials)
    return _post("/open-apis/im/v1/messages?receive_id_type=open_id", {
        "receive_id": credentials.open_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
    }, {"Authorization": f"Bearer {token}"})
