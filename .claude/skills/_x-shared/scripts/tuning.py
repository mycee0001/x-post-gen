"""プロジェクトローカルなスキル調整ロジック (tuning) 管理。

`.x-history/tuning.jsonl` にスキップ理由を記録し、次回実行時に
Claude が読み込んで以下のいずれかを調整する:

  - source:  検索クエリ・対象アカウント・著者フィルタ
  - content: 生成原稿のトーン・切り口・自己言及度
  - flame:   炎上チェックの解釈 (誤判定の上書き / 見逃し補強)

このファイルはプロジェクトディレクトリ配下なので、別プロジェクトでは
完全に独立したチューニングが効く。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path

try:
    from .utils import JST, ensure_history_dir, now_jst, now_jst_iso, generate_id
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from utils import JST, ensure_history_dir, now_jst, now_jst_iso, generate_id  # type: ignore

STATE_FILE = "tuning.jsonl"

VALID_KINDS = {"reply", "quote", "post"}
VALID_CATEGORIES = {"source", "content", "flame", "other"}


def _state_path(history_dir: str = "./.x-history") -> Path:
    return ensure_history_dir(history_dir) / STATE_FILE


def save(
    kind: str,
    feedback: list[dict],
    history_dir: str = "./.x-history",
) -> int:
    """スキップ理由を保存する。

    Args:
        kind: "reply" | "quote" | "post"
        feedback: 各要素は {category, reason, item: {...}} の dict
        history_dir: 履歴ディレクトリ

    Returns:
        保存した件数
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"Invalid kind: {kind}")
    if not feedback:
        return 0
    path = _state_path(history_dir)
    ts = now_jst_iso()
    count = 0
    with path.open("a", encoding="utf-8") as f:
        for fb in feedback:
            cat = fb.get("category", "other")
            if cat not in VALID_CATEGORIES:
                cat = "other"
            entry = {
                "id": generate_id(f"tune_{kind}"),
                "created_at": ts,
                "kind": kind,
                "category": cat,
                "reason": fb.get("reason", ""),
                "item": fb.get("item", {}),
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            count += 1
    return count


def load(
    kind: str | None = None,
    category: str | None = None,
    since_days: int = 30,
    limit: int = 50,
    history_dir: str = "./.x-history",
) -> list[dict]:
    """調整エントリを取得する。

    Args:
        kind: フィルタする種類。None なら全種類
        category: フィルタするカテゴリ。None なら全カテゴリ
        since_days: 何日前まで遡るか
        limit: 最大件数 (新しい順から)
        history_dir: 履歴ディレクトリ

    Returns:
        エントリのリスト (新しい順)
    """
    path = _state_path(history_dir)
    if not path.exists():
        return []
    from datetime import datetime

    cutoff = now_jst() - timedelta(days=since_days)
    entries: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if kind and obj.get("kind") != kind:
                continue
            if category and obj.get("category") != category:
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
            entries.append(obj)
    entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    return entries[:limit]


def stats(
    kind: str | None = None,
    since_days: int = 30,
    history_dir: str = "./.x-history",
) -> dict:
    """カテゴリ別件数と最近の傾向を返す。"""
    entries = load(kind=kind, since_days=since_days, limit=10_000, history_dir=history_dir)
    by_cat: Counter[str] = Counter()
    by_kind: Counter[str] = Counter()
    for e in entries:
        by_cat[e.get("category", "other")] += 1
        by_kind[e.get("kind", "?")] += 1
    return {
        "total": len(entries),
        "since_days": since_days,
        "by_category": dict(by_cat),
        "by_kind": dict(by_kind),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="スキル調整ロジック (tuning) 管理")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_save = sub.add_parser("save", help="フィードバックを保存")
    p_save.add_argument("--kind", required=True, choices=sorted(VALID_KINDS))
    p_save.add_argument("--feedback-json", required=True, help='[{"category":"source","reason":"...","item":{...}}] 形式')
    p_save.add_argument("--history-dir", default="./.x-history")

    p_load = sub.add_parser("load", help="調整エントリを取得")
    p_load.add_argument("--kind", choices=sorted(VALID_KINDS))
    p_load.add_argument("--category", choices=sorted(VALID_CATEGORIES))
    p_load.add_argument("--since-days", type=int, default=30)
    p_load.add_argument("--limit", type=int, default=50)
    p_load.add_argument("--history-dir", default="./.x-history")

    p_stat = sub.add_parser("stats", help="件数集計")
    p_stat.add_argument("--kind", choices=sorted(VALID_KINDS))
    p_stat.add_argument("--since-days", type=int, default=30)
    p_stat.add_argument("--history-dir", default="./.x-history")

    args = parser.parse_args()

    if args.cmd == "save":
        try:
            feedback = json.loads(args.feedback_json)
        except json.JSONDecodeError as e:
            print(f"ERROR: --feedback-json が JSON ではない: {e}", file=sys.stderr)
            return 2
        if not isinstance(feedback, list):
            print("ERROR: --feedback-json は配列である必要がある", file=sys.stderr)
            return 2
        count = save(args.kind, feedback, args.history_dir)
        print(json.dumps({"ok": True, "saved": count}, ensure_ascii=False))
        return 0

    if args.cmd == "load":
        entries = load(
            kind=args.kind,
            category=args.category,
            since_days=args.since_days,
            limit=args.limit,
            history_dir=args.history_dir,
        )
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "stats":
        s = stats(args.kind, args.since_days, args.history_dir)
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
