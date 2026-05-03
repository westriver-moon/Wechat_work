import json
import os
import time
from pathlib import Path
from typing import Dict

import requests

BASE_DIR = Path(__file__).resolve().parent
CACHE_FILE = BASE_DIR / "wechat_token_cache.json"

WECHAT_APPID = os.getenv("WECHAT_APPID", "")
WECHAT_APPSECRET = os.getenv("WECHAT_APPSECRET", "")


def _load_cache() -> Dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(token: str, expires_at: int) -> None:
    payload = {"access_token": token, "expires_at": int(expires_at)}
    CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def get_access_token(force_refresh: bool = False) -> str:
    if not WECHAT_APPID or not WECHAT_APPSECRET:
        raise RuntimeError("WECHAT_APPID/WECHAT_APPSECRET not configured")

    now = int(time.time())
    if not force_refresh:
        cache = _load_cache()
        token = str(cache.get("access_token", ""))
        expires_at = int(cache.get("expires_at", 0))
        if token and expires_at > now + 60:
            return token

    resp = requests.get(
        "https://api.weixin.qq.com/cgi-bin/token",
        params={
            "grant_type": "client_credential",
            "appid": WECHAT_APPID,
            "secret": WECHAT_APPSECRET,
        },
        timeout=8,
    )
    data = resp.json()
    token = str(data.get("access_token", ""))
    if not token:
        raise RuntimeError(f"get_access_token_failed: {data}")

    expires_in = int(data.get("expires_in", 7200))
    _save_cache(token, now + expires_in)
    return token


def send_customer_message(openid: str, text: str) -> Dict:
    try:
        token = get_access_token(force_refresh=False)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    payload = {
        "touser": openid,
        "msgtype": "text",
        "text": {"content": text},
    }

    url = f"https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={token}"
    try:
        resp = requests.post(url, json=payload, timeout=8)
        data = resp.json()
        # Token expired or invalid, try one forced refresh.
        if int(data.get("errcode", 0)) in {40001, 42001, 40014}:
            token = get_access_token(force_refresh=True)
            url = f"https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token={token}"
            resp = requests.post(url, json=payload, timeout=8)
            data = resp.json()

        return {
            "ok": int(data.get("errcode", -1)) == 0,
            "errcode": int(data.get("errcode", -1)),
            "errmsg": str(data.get("errmsg", "")),
            "raw": data,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
