"""共通ユーティリティ。

- .env のロード
- JST タイムゾーン
- ID 生成
- 履歴ディレクトリ初期化
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore

JST = timezone(timedelta(hours=9))

_ENV_LOADED = False


def load_env(env_path: str | None = None) -> None:
    """カレントディレクトリの .env を読み込む(冪等)。"""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    if load_dotenv is None:
        _ENV_LOADED = True
        return
    if env_path is None:
        env_path = str(Path.cwd() / ".env")
    if Path(env_path).exists():
        load_dotenv(env_path)
    _ENV_LOADED = True


def now_jst() -> datetime:
    return datetime.now(JST)


def now_jst_iso() -> str:
    return now_jst().isoformat(timespec="seconds")


def generate_id(kind: str) -> str:
    """kind は "post" or "quote"。"""
    ts = now_jst().strftime("%Y%m%d_%H%M%S")
    return f"{kind}_{ts}"


def ensure_history_dir(history_dir: str = "./.x-history") -> Path:
    """履歴ディレクトリを作成して Path を返す。ユーザー許可不要。"""
    p = Path(history_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def getenv_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


def count_chars_for_x(text: str) -> int:
    """X の字数カウント(URL は 23 文字換算、日本語 1 文字 = 1 文字)。

    X 公式の字数計算は weighted だが、ここでは簡易実装:
      - 空白区切りで URL らしきトークンを 23 文字換算
      - それ以外は文字数(コードポイント数)
    """
    if not text:
        return 0
    # URL 置換(23 文字のダミーに)
    url_pattern = re.compile(r"https?://\S+")
    replaced = url_pattern.sub("X" * 23, text)
    return len(replaced)


def safe_print_json(obj, **kwargs) -> None:
    """標準出力へ UTF-8 JSON を出す。"""
    import json
    import sys
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, **kwargs))
    sys.stdout.write("\n")
    sys.stdout.flush()


def mask_secret(value: str | None, keep: int = 4) -> str:
    """ログ用にシークレットをマスクする。"""
    if not value:
        return "<empty>"
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "*" * (len(value) - keep)
