import json
from pathlib import Path
from typing import Dict
from http.cookiejar import CookieJar
import requests


def load_cookies_from_json(cookie_file: str) -> Dict[str, str]:
    """從 JSON 檔案載入 cookies (支援多種格式)"""
    cookie_path = Path(cookie_file)
    if not cookie_path.exists():
        raise FileNotFoundError(f"Cookie 檔案不存在: {cookie_file}")

    with open(cookie_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    cookies = {}

    # 格式1: EditThisCookie 匯出格式 (list of dicts)
    if isinstance(data, list):
        for cookie in data:
            if isinstance(cookie, dict) and 'name' in cookie and 'value' in cookie:
                cookies[cookie['name']] = cookie['value']

    # 格式2: 簡單的 {name: value} 格式
    elif isinstance(data, dict):
        # 檢查是否為巢狀格式
        if all(isinstance(v, str) for v in data.values()):
            cookies = data
        else:
            # 可能是其他格式，嘗試提取
            for key, value in data.items():
                if isinstance(value, str):
                    cookies[key] = value
                elif isinstance(value, dict) and 'value' in value:
                    cookies[key] = value['value']

    return cookies


def apply_cookies_to_session(session: requests.Session, cookies: Dict[str, str],
                             domain: str = ".fastzone.org"):
    """將 cookies 套用到 requests Session"""
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=domain)


def get_important_cookies(cookies: Dict[str, str]) -> Dict[str, str]:
    """提取重要的認證 cookies"""
    important_prefixes = ['95ck_2132_auth', '95ck_2132_saltkey', '95ck_2132_sid']
    return {k: v for k, v in cookies.items()
            if any(k.startswith(prefix) for prefix in important_prefixes)}
