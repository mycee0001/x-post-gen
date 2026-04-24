"""新規生成物が過去の履歴と重複していないかを判定する。

- simhash による本文類似度
- トピックタグの完全一致
- 引用ツイートの場合: 同一 tweet_id / 同一アカウント直近2回以上
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from simhash import Simhash
except ImportError as e:  # pragma: no cover
    print(
        "ERROR: simhash ライブラリが見つかりません。\n"
        "pip install -r requirements.txt を実行してください。",
        file=sys.stderr,
    )
    raise

try:
    from .utils import getenv_int
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from utils import getenv_int  # type: ignore


def _tokenize(text: str) -> list[str]:
    """簡易トークナイザ(日本語は 2-gram、英数字は単語)。"""
    import re
    tokens: list[str] = []
    # 英数字連続を単語として抽出
    for m in re.finditer(r"[A-Za-z0-9_]+", text):
        tokens.append(m.group(0).lower())
    # 日本語部分を 2-gram 化
    ja = re.sub(r"[A-Za-z0-9_\s]+", "", text)
    for i in range(len(ja) - 1):
        tokens.append(ja[i : i + 2])
    return tokens


def compute_simhash(text: str) -> int:
    """Simhash 値(int)を返す。"""
    if not text:
        return 0
    return Simhash(_tokenize(text)).value


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _entry_simhash(entry: dict[str, Any]) -> int | None:
    val = entry.get("simhash")
    if val is None:
        return None
    if isinstance(val, int):
        return val
    try:
        return int(val, 16) if isinstance(val, str) else int(val)
    except (ValueError, TypeError):
        return None


def is_duplicate_post(
    new_entry: dict[str, Any],
    history: list[dict[str, Any]],
    threshold: int | None = None,
) -> tuple[bool, str]:
    """本文 simhash のハミング距離が threshold 以下なら重複。
    トピックタグの完全一致(セット一致)も重複扱い。
    """
    if threshold is None:
        threshold = getenv_int("X_HISTORY_SIMHASH_THRESHOLD", 4)

    new_hash = new_entry.get("simhash")
    if isinstance(new_hash, str):
        try:
            new_hash = int(new_hash, 16)
        except ValueError:
            new_hash = None
    if new_hash is None:
        new_hash = compute_simhash(new_entry.get("text", ""))

    new_tags = frozenset(new_entry.get("topic_tags", []) or [])

    for past in history:
        past_hash = _entry_simhash(past)
        if past_hash is not None:
            dist = hamming_distance(new_hash, past_hash)
            if dist <= threshold:
                return (
                    True,
                    f"本文が過去ポスト {past.get('id', '?')} と類似(ハミング距離 {dist} ≤ {threshold})",
                )
        if new_tags and frozenset(past.get("topic_tags", []) or []) == new_tags:
            return (
                True,
                f"トピックタグが過去ポスト {past.get('id', '?')} と完全一致: {sorted(new_tags)}",
            )
    return (False, "")


def is_duplicate_quote(
    new_entry: dict[str, Any],
    history: list[dict[str, Any]],
    threshold: int | None = None,
) -> tuple[bool, str]:
    """引用ツイート特有のチェック。"""
    if threshold is None:
        threshold = getenv_int("X_HISTORY_SIMHASH_THRESHOLD", 4)

    new_tweet = new_entry.get("quoted_tweet") or {}
    new_tweet_id = new_tweet.get("tweet_id")
    new_handle = new_tweet.get("author_handle")

    new_hash = new_entry.get("simhash")
    if isinstance(new_hash, str):
        try:
            new_hash = int(new_hash, 16)
        except ValueError:
            new_hash = None
    if new_hash is None:
        new_hash = compute_simhash(new_entry.get("comment_text", ""))

    # 同一ハンドルの引用回数を数える
    handle_counter: Counter[str] = Counter()
    for past in history:
        past_tweet = past.get("quoted_tweet") or {}
        if new_tweet_id and past_tweet.get("tweet_id") == new_tweet_id:
            return (True, f"同一ツイート(tweet_id={new_tweet_id})は過去に引用済み")
        h = past_tweet.get("author_handle")
        if h:
            handle_counter[h] += 1

        past_hash = _entry_simhash(past)
        if past_hash is not None and new_hash:
            dist = hamming_distance(new_hash, past_hash)
            if dist <= threshold:
                return (
                    True,
                    f"コメント本文が過去引用 {past.get('id', '?')} と類似(ハミング距離 {dist})",
                )

    if new_handle and handle_counter.get(new_handle, 0) >= 2:
        return (
            True,
            f"@{new_handle} は直近30日で既に {handle_counter[new_handle]} 回引用済み(多用回避)",
        )

    return (False, "")


def suggest_underused_topics(
    canvas_topics: list[str],
    history: list[dict[str, Any]],
    top_n: int = 5,
) -> list[str]:
    """履歴で使用頻度が低いトピックを優先して返す。"""
    counter: Counter[str] = Counter()
    for entry in history:
        for t in entry.get("topic_tags", []) or []:
            counter[t] += 1

    scored: list[tuple[int, int, str]] = []
    for i, t in enumerate(canvas_topics):
        scored.append((counter.get(t, 0), i, t))
    scored.sort()  # 使用頻度昇順、同率は元の順序維持
    return [t for _, _, t in scored[:top_n]]


def main() -> int:
    parser = argparse.ArgumentParser(description="重複判定ユーティリティ")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_hash = sub.add_parser("simhash", help="simhash を計算")
    p_hash.add_argument("--text", required=True)

    p_post = sub.add_parser("check-post", help="ポスト重複チェック")
    p_post.add_argument("--entry-json", required=True)
    p_post.add_argument("--history-json", required=True)

    p_quote = sub.add_parser("check-quote", help="引用重複チェック")
    p_quote.add_argument("--entry-json", required=True)
    p_quote.add_argument("--history-json", required=True)

    p_suggest = sub.add_parser("suggest-topics", help="低頻度トピックを提案")
    p_suggest.add_argument("--canvas-topics-json", required=True)
    p_suggest.add_argument("--history-json", required=True)
    p_suggest.add_argument("--top-n", type=int, default=5)

    args = parser.parse_args()

    if args.cmd == "simhash":
        h = compute_simhash(args.text)
        print(json.dumps({"simhash": format(h, "x")}, ensure_ascii=False))
        return 0

    if args.cmd == "check-post":
        entry = json.loads(args.entry_json)
        history = json.loads(args.history_json)
        dup, reason = is_duplicate_post(entry, history)
        print(json.dumps({"is_duplicate": dup, "reason": reason}, ensure_ascii=False))
        return 0

    if args.cmd == "check-quote":
        entry = json.loads(args.entry_json)
        history = json.loads(args.history_json)
        dup, reason = is_duplicate_quote(entry, history)
        print(json.dumps({"is_duplicate": dup, "reason": reason}, ensure_ascii=False))
        return 0

    if args.cmd == "suggest-topics":
        topics = json.loads(args.canvas_topics_json)
        history = json.loads(args.history_json)
        out = suggest_underused_topics(topics, history, args.top_n)
        print(json.dumps(out, ensure_ascii=False))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
