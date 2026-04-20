"""TwitterAPI.io の Advanced Search エンドポイントで X 内ツイートを検索する。

- エンドポイント: GET /twitter/tweet/advanced_search
- 認証: X-API-Key ヘッダー
- ドキュメント: https://docs.twitterapi.io

将来 X 社規約変更等で TwitterAPI.io が使えなくなる可能性があるため、
クライアントは抽象化しやすい形で実装。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError as e:  # pragma: no cover
    print("ERROR: requests が必要です。pip install requests", file=sys.stderr)
    raise

try:
    from .utils import load_env
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from utils import load_env  # type: ignore

BASE_URL = "https://api.twitterapi.io"
ADVANCED_SEARCH_PATH = "/twitter/tweet/advanced_search"


class TwitterAPIError(Exception):
    pass


def _get_api_key() -> str:
    load_env()
    key = os.environ.get("TWITTERAPI_IO_KEY", "").strip()
    if not key:
        raise TwitterAPIError(
            "TWITTERAPI_IO_KEY が設定されていません。.env に記入してください。"
        )
    return key


def _build_query(
    terms: str,
    language: str = "ja",
    hours_back: int = 72,
    min_likes: int = 5,
) -> str:
    """Advanced Search のクエリ文字列を組み立てる(X の検索構文)。"""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).strftime("%Y-%m-%d")
    parts: list[str] = [terms.strip()]
    if language:
        parts.append(f"lang:{language}")
    if min_likes > 0:
        parts.append(f"min_faves:{min_likes}")
    parts.append(f"since:{since}")
    parts.append("-is:retweet")
    return " ".join(p for p in parts if p)


def _request(
    query: str,
    cursor: str | None = None,
    query_type: str = "Latest",
    timeout: int = 30,
) -> dict[str, Any]:
    key = _get_api_key()
    params = {"query": query, "queryType": query_type}
    if cursor:
        params["cursor"] = cursor
    headers = {"X-API-Key": key}
    url = BASE_URL + ADVANCED_SEARCH_PATH

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
        except requests.exceptions.RequestException as e:
            last_exc = e
            time.sleep(1 + attempt)
            continue

        if r.status_code in (401, 403):
            raise TwitterAPIError(
                f"TwitterAPI.io 認証失敗 (status={r.status_code})。"
                f".env の TWITTERAPI_IO_KEY を確認してください。"
            )
        if r.status_code == 429:
            time.sleep(3)
            continue
        if r.status_code >= 500:
            time.sleep(1 + attempt)
            continue
        if not r.ok:
            raise TwitterAPIError(
                f"TwitterAPI.io エラー status={r.status_code}: {r.text[:200]}"
            )
        try:
            return r.json()
        except ValueError as e:
            raise TwitterAPIError(f"TwitterAPI.io のレスポンスが JSON ではない: {e}")

    if last_exc:
        raise TwitterAPIError(f"TwitterAPI.io ネットワークエラー: {last_exc}")
    raise TwitterAPIError("TwitterAPI.io にリトライ後も失敗しました")


def _normalize_tweet(t: dict[str, Any]) -> dict[str, Any] | None:
    """API レスポンスの1件を共通スキーマに正規化。"""
    if not isinstance(t, dict):
        return None
    tweet_id = t.get("id") or t.get("tweet_id") or t.get("rest_id")
    if not tweet_id:
        return None
    tweet_id = str(tweet_id)

    author = t.get("author") or t.get("user") or {}
    if isinstance(author, dict):
        author_handle = (
            author.get("userName")
            or author.get("username")
            or author.get("screen_name")
            or ""
        )
        author_id = str(author.get("id") or author.get("rest_id") or "")
        author_name = author.get("name") or ""
    else:
        author_handle = ""
        author_id = ""
        author_name = ""

    text = t.get("text") or t.get("full_text") or ""
    posted_at = (
        t.get("createdAt")
        or t.get("created_at")
        or t.get("creation_date")
        or ""
    )

    like_count = _to_int(
        t.get("likeCount")
        or t.get("favorite_count")
        or t.get("favoriteCount")
        or 0
    )
    repost_count = _to_int(
        t.get("retweetCount") or t.get("retweet_count") or 0
    )
    reply_count = _to_int(t.get("replyCount") or t.get("reply_count") or 0)

    url = f"https://x.com/{author_handle}/status/{tweet_id}" if author_handle else ""

    return {
        "tweet_id": tweet_id,
        "url": url,
        "author_handle": author_handle,
        "author_id": author_id,
        "author_name": author_name,
        "text": text,
        "posted_at": posted_at,
        "like_count": like_count,
        "repost_count": repost_count,
        "reply_count": reply_count,
    }


def _to_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _extract_tweets(resp: dict[str, Any]) -> list[dict[str, Any]]:
    """API レスポンスから tweets のリストを取り出す(仕様差吸収)。"""
    for key in ("tweets", "data", "results", "statuses"):
        val = resp.get(key)
        if isinstance(val, list):
            return val
    # data の中に入っているパターン
    data = resp.get("data")
    if isinstance(data, dict):
        for key in ("tweets", "results"):
            val = data.get(key)
            if isinstance(val, list):
                return val
    return []


def search_tweets(
    query: str,
    max_results: int = 30,
    language: str = "ja",
    hours_back: int = 72,
    min_likes: int = 5,
) -> list[dict[str, Any]]:
    """X 内ツイートを検索して共通スキーマに正規化して返す。"""
    q = _build_query(query, language=language, hours_back=hours_back, min_likes=min_likes)
    results: list[dict[str, Any]] = []
    cursor: str | None = None

    while len(results) < max_results:
        resp = _request(q, cursor=cursor)
        tweets = _extract_tweets(resp)
        if not tweets:
            break
        for t in tweets:
            norm = _normalize_tweet(t)
            if norm:
                results.append(norm)
            if len(results) >= max_results:
                break
        cursor = (
            resp.get("next_cursor")
            or resp.get("nextCursor")
            or (resp.get("data") or {}).get("next_cursor")
            if isinstance(resp.get("data"), dict)
            else resp.get("next_cursor")
        )
        has_more = resp.get("has_next_page") or resp.get("hasNextPage")
        if not cursor or has_more is False:
            break
        time.sleep(0.5)

    return results[:max_results]


def multi_search(
    queries: list[str],
    max_results_per_query: int = 30,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """複数クエリで検索して重複排除。"""
    seen: set[str] = set()
    combined: list[dict[str, Any]] = []
    for q in queries:
        try:
            items = search_tweets(q, max_results=max_results_per_query, **kwargs)
        except TwitterAPIError as e:
            print(f"WARN: query={q!r} でエラー: {e}", file=sys.stderr)
            continue
        for it in items:
            if it["tweet_id"] in seen:
                continue
            seen.add(it["tweet_id"])
            combined.append(it)
    return combined


def main() -> int:
    parser = argparse.ArgumentParser(description="TwitterAPI.io Advanced Search")
    parser.add_argument("--query", required=True, help="検索キーワード(X 検索構文も可)")
    parser.add_argument("--max-results", type=int, default=30)
    parser.add_argument("--language", default="ja")
    parser.add_argument("--hours-back", type=int, default=72)
    parser.add_argument("--min-likes", type=int, default=5)
    args = parser.parse_args()

    try:
        results = search_tweets(
            args.query,
            max_results=args.max_results,
            language=args.language,
            hours_back=args.hours_back,
            min_likes=args.min_likes,
        )
    except TwitterAPIError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
