"""`.x-history/*.jsonl` を管理する。

append / load / stats を提供する。
履歴ディレクトリが無い場合は自動生成(ユーザー許可不要)。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from .utils import JST, ensure_history_dir, now_jst
except ImportError:  # スクリプトとして直接実行された場合
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from utils import JST, ensure_history_dir, now_jst  # type: ignore

VALID_KINDS = ("post", "quote")


def _file_for(kind: str, history_dir: str) -> Path:
    if kind not in VALID_KINDS:
        raise ValueError(f"kind は {VALID_KINDS} のいずれか。got: {kind!r}")
    return ensure_history_dir(history_dir) / f"{kind}s.jsonl"


def _entry_matches_service(entry: dict[str, Any], service: str | None) -> bool:
    """エントリが指定 service にマッチするかを判定する。

    - service=None なら常に True (全件)
    - エントリに service フィールドが無い場合は **常に True** (旧データを無駄にしない)
    - エントリに service フィールドがあれば一致時のみ True
    """
    if service is None:
        return True
    entry_svc = entry.get("service")
    if not entry_svc:
        return True  # 後方互換: service タグが付いていない過去データは全 service に hit させる
    return entry_svc == service


def append(kind: str, entry: dict[str, Any], history_dir: str = "./.x-history") -> None:
    """1 エントリを追記する。entry に service フィールドを含めることを推奨。"""
    path = _file_for(kind, history_dir)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load(
    kind: str,
    since_days: int = 30,
    history_dir: str = "./.x-history",
    service: str | None = None,
) -> list[dict[str, Any]]:
    """直近 since_days 日のエントリを返す(ファイルが無ければ空リスト)。

    Args:
        service: 指定すると同じ service のエントリ + service タグ無しの旧データを返す。
    """
    path = _file_for(kind, history_dir)
    if not path.exists():
        return []
    cutoff = now_jst() - timedelta(days=since_days)
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not _entry_matches_service(obj, service):
                continue
            created_at = obj.get("created_at")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=JST)
                    if dt < cutoff:
                        continue
                except ValueError:
                    pass
            out.append(obj)
    return out


def stats(
    kind: str,
    history_dir: str = "./.x-history",
    service: str | None = None,
) -> dict[str, Any]:
    """集計統計を返す。service 指定時は同 service + 旧データのみ集計。"""
    path = _file_for(kind, history_dir)
    total = 0
    last_30d = 0
    topic_counter: Counter[str] = Counter()
    accounts: list[str] = []
    cutoff = now_jst() - timedelta(days=30)

    if not path.exists():
        return {
            "total": 0,
            "last_30d": 0,
            "topic_coverage": {},
            "accounts_quoted_last_30d": [],
        }

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not _entry_matches_service(obj, service):
                continue
            total += 1
            in_window = False
            created_at = obj.get("created_at")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=JST)
                    if dt >= cutoff:
                        in_window = True
                        last_30d += 1
                except ValueError:
                    pass
            if in_window:
                for t in obj.get("topic_tags", []) or []:
                    topic_counter[t] += 1
                if kind == "quote":
                    handle = (obj.get("quoted_tweet") or {}).get("author_handle")
                    if handle:
                        accounts.append(handle)

    result: dict[str, Any] = {
        "total": total,
        "last_30d": last_30d,
        "topic_coverage": dict(topic_counter),
    }
    if kind == "quote":
        result["accounts_quoted_last_30d"] = sorted(set(accounts))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=".x-history/*.jsonl の管理")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_app = sub.add_parser("append", help="エントリを追記")
    p_app.add_argument("--kind", required=True, choices=VALID_KINDS)
    p_app.add_argument("--data-json", required=True, help="JSON 文字列")
    p_app.add_argument("--history-dir", default="./.x-history")

    p_load = sub.add_parser("load", help="履歴を読み込む")
    p_load.add_argument("--kind", required=True, choices=VALID_KINDS)
    p_load.add_argument("--since-days", type=int, default=30)
    p_load.add_argument("--history-dir", default="./.x-history")
    p_load.add_argument(
        "--service",
        default=None,
        help="service 識別子 (lean-canvas-{service}.md)。指定時は同 service + service 無し旧データを返す",
    )

    p_stats = sub.add_parser("stats", help="集計を表示")
    p_stats.add_argument("--kind", required=True, choices=VALID_KINDS)
    p_stats.add_argument("--history-dir", default="./.x-history")
    p_stats.add_argument(
        "--service",
        default=None,
        help="service 識別子。指定時は同 service + service 無し旧データを集計",
    )

    args = parser.parse_args()

    if args.cmd == "append":
        try:
            entry = json.loads(args.data_json)
        except json.JSONDecodeError as e:
            print(f"ERROR: --data-json が JSON ではない: {e}", file=sys.stderr)
            return 2
        append(args.kind, entry, args.history_dir)
        print(json.dumps({"ok": True}, ensure_ascii=False))
        return 0

    if args.cmd == "load":
        out = load(args.kind, args.since_days, args.history_dir, service=args.service)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "stats":
        out = stats(args.kind, args.history_dir, service=args.service)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
