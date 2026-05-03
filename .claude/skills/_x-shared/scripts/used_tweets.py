"""スキル間(x-quote / x-reply)で使用済みツイート ID を共有するステート管理。

`.x-history/used_tweet_ids.jsonl` に記録し、
検索時に除外リストとして渡すことで候補の重複を防ぐ。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

try:
    from .utils import JST, ensure_history_dir, now_jst, now_jst_iso
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from utils import JST, ensure_history_dir, now_jst, now_jst_iso  # type: ignore

STATE_FILE = "used_tweet_ids.jsonl"


def _state_path(history_dir: str = "./.x-history") -> Path:
    return ensure_history_dir(history_dir) / STATE_FILE


def record(
    skill: str,
    tweet_ids: list[str],
    history_dir: str = "./.x-history",
) -> int:
    """使用済みツイート ID を記録する。

    Args:
        skill: "quote" or "reply"
        tweet_ids: 記録する tweet_id のリスト
        history_dir: 履歴ディレクトリ

    Returns:
        追記した件数
    """
    if not tweet_ids:
        return 0
    path = _state_path(history_dir)
    ts = now_jst_iso()
    count = 0
    with path.open("a", encoding="utf-8") as f:
        for tid in tweet_ids:
            entry = {"tweet_id": str(tid), "skill": skill, "used_at": ts}
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            count += 1
    return count


def load(
    hours_back: int | None = None,
    history_dir: str = "./.x-history",
) -> list[str]:
    """使用済みツイート ID のリストを返す。

    リプライ/引用は同じポストに対して二度行わない方針のため、
    デフォルトでは **全期間** の使用済み ID を返す(厳格な重複防止)。

    Args:
        hours_back: 指定した場合のみ、その時間以内に使用された ID に絞る。
            None (デフォルト) なら全期間の ID を返す。
        history_dir: 履歴ディレクトリ

    Returns:
        tweet_id の重複なしリスト
    """
    path = _state_path(history_dir)
    if not path.exists():
        return []
    from datetime import datetime

    cutoff = (
        now_jst() - timedelta(hours=hours_back) if hours_back is not None else None
    )
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            used_at = obj.get("used_at")
            if cutoff is not None and used_at:
                try:
                    dt = datetime.fromisoformat(used_at)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=JST)
                    if dt < cutoff:
                        continue
                except ValueError:
                    pass
            seen.add(str(obj.get("tweet_id", "")))
    seen.discard("")
    return sorted(seen)


def cleanup(
    keep_hours: int = 8760,
    history_dir: str = "./.x-history",
) -> int:
    """古いエントリを削除してファイルを縮小する(任意操作)。

    重複防止は `load()` の全期間モードで成立するため、通常はこの関数を呼ぶ必要はない。
    ファイルサイズが過大になった場合のみ手動で実行する。

    Args:
        keep_hours: この時間以内のエントリだけ残す(デフォルト 1 年 = 8760h)
        history_dir: 履歴ディレクトリ

    Returns:
        削除した件数
    """
    path = _state_path(history_dir)
    if not path.exists():
        return 0
    from datetime import datetime

    cutoff = now_jst() - timedelta(hours=keep_hours)
    kept: list[str] = []
    removed = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                removed += 1
                continue
            used_at = obj.get("used_at")
            if used_at:
                try:
                    dt = datetime.fromisoformat(used_at)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=JST)
                    if dt < cutoff:
                        removed += 1
                        continue
                except ValueError:
                    pass
            kept.append(json.dumps(obj, ensure_ascii=False))
    with path.open("w", encoding="utf-8") as f:
        for entry_line in kept:
            f.write(entry_line + "\n")
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="スキル間 使用済みツイートID 管理")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("record", help="使用済み ID を記録")
    p_rec.add_argument("--skill", required=True, choices=["quote", "reply"])
    p_rec.add_argument("--tweet-ids-json", required=True, help='["id1","id2"] 形式')
    p_rec.add_argument("--history-dir", default="./.x-history")

    p_load = sub.add_parser(
        "load",
        help="使用済み ID を取得(デフォルトは全期間。重複防止のため通常はこれを使う)",
    )
    p_load.add_argument(
        "--hours-back",
        type=int,
        default=None,
        help="この時間以内の ID に絞る。未指定なら全期間",
    )
    p_load.add_argument("--history-dir", default="./.x-history")

    p_clean = sub.add_parser(
        "cleanup",
        help="古いエントリを削除(任意)。通常は実行不要",
    )
    p_clean.add_argument("--keep-hours", type=int, default=8760)
    p_clean.add_argument("--history-dir", default="./.x-history")

    args = parser.parse_args()

    if args.cmd == "record":
        try:
            ids = json.loads(args.tweet_ids_json)
        except json.JSONDecodeError as e:
            print(f"ERROR: --tweet-ids-json が JSON ではない: {e}", file=sys.stderr)
            return 2
        count = record(args.skill, ids, args.history_dir)
        print(json.dumps({"ok": True, "recorded": count}, ensure_ascii=False))
        return 0

    if args.cmd == "load":
        ids = load(args.hours_back, args.history_dir)
        print(json.dumps(ids, ensure_ascii=False))
        return 0

    if args.cmd == "cleanup":
        removed = cleanup(args.keep_hours, args.history_dir)
        print(json.dumps({"ok": True, "removed": removed}, ensure_ascii=False))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
