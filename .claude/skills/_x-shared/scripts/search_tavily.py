"""Tavily Search API でニュース・論文・Web 情報を調査する。

Tavily は AI エージェント向けに最適化された検索 API。
- Basic search: 1 credit / Advanced search: 2 credits
- include_answer=True で AI 生成の answer を取得できる
- include_domains / exclude_domains でドメインフィルタ可能
- topic="news" でニュース寄り、"general" で汎用

ドキュメント: https://docs.tavily.com
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from tavily import TavilyClient
except ImportError as e:  # pragma: no cover
    print(
        "ERROR: tavily-python が必要です。pip install tavily-python",
        file=sys.stderr,
    )
    raise

try:
    from .utils import load_env
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from utils import load_env  # type: ignore


DEFAULT_DOMAIN_FILTER_MFG = [
    "meti.go.jp",
    "monoist.itmedia.co.jp",
    "nikkei.com",
    "prtimes.jp",
    "nikkeibp.co.jp",
    "xtech.nikkei.com",
    "jst.go.jp",
    "nedo.go.jp",
]


def _get_client() -> TavilyClient:
    load_env()
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "TAVILY_API_KEY が設定されていません。.env に記入してください。"
        )
    return TavilyClient(api_key=api_key)


def _normalize_time_range(recency: str | None) -> str | None:
    """Perplexity 互換の recency 指定を Tavily の time_range に変換。"""
    if not recency:
        return None
    m = {
        "day": "day",
        "week": "week",
        "month": "month",
        "year": "year",
    }
    return m.get(recency.lower())


def research(
    query: str,
    domain_filter: list[str] | None = None,
    recency: str = "month",
    search_depth: str = "advanced",
    max_results: int = 8,
    include_answer: bool = True,
    topic: str = "general",
) -> dict[str, Any]:
    """Tavily で調査して Perplexity 互換形式で返す。

    Returns:
        {
            "answer": str,
            "citations": [{"url", "title", "snippet", "date"}],
            "usage": {...},
            "query": str,
        }
    """
    client = _get_client()

    params: dict[str, Any] = {
        "query": query,
        "search_depth": search_depth,   # "basic" or "advanced"
        "max_results": max_results,
        "include_answer": include_answer,
        "topic": topic,
    }
    if domain_filter:
        params["include_domains"] = domain_filter
    tr = _normalize_time_range(recency)
    if tr:
        params["time_range"] = tr

    try:
        resp = client.search(**params)
    except Exception as e:
        raise RuntimeError(f"Tavily API 呼び出しに失敗: {e}") from e

    # Tavily のレスポンス:
    # { "answer": "...", "query": "...", "results": [{"title","url","content","score","published_date"}], ... }
    answer = resp.get("answer") or ""
    results = resp.get("results") or []
    citations: list[dict[str, Any]] = []
    for r in results:
        citations.append(
            {
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "snippet": (r.get("content") or "")[:500],
                "date": r.get("published_date") or "",
                "score": r.get("score"),
            }
        )

    # usage は Tavily のプランによっては含まれない。プレースホルダとして件数を入れる
    usage = {
        "results_count": len(results),
        "search_depth": search_depth,
    }

    return {
        "answer": answer,
        "citations": citations,
        "usage": usage,
        "query": query,
    }


def research_multi(
    queries: list[str],
    domain_filter: list[str] | None = None,
    recency: str = "month",
    search_depth: str = "advanced",
    max_results: int = 8,
) -> list[dict[str, Any]]:
    """複数クエリを順次実行。"""
    results: list[dict[str, Any]] = []
    for q in queries:
        try:
            results.append(
                research(
                    q,
                    domain_filter=domain_filter,
                    recency=recency,
                    search_depth=search_depth,
                    max_results=max_results,
                )
            )
        except Exception as e:
            results.append(
                {"answer": "", "citations": [], "usage": {}, "query": q, "error": str(e)}
            )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Tavily Search API で調査")
    parser.add_argument("--query", required=True)
    parser.add_argument(
        "--domain-filter",
        nargs="*",
        default=None,
        help="include_domains のリスト",
    )
    parser.add_argument(
        "--recency",
        default="month",
        choices=["day", "week", "month", "year"],
    )
    parser.add_argument(
        "--search-depth",
        default="advanced",
        choices=["basic", "advanced"],
    )
    parser.add_argument("--max-results", type=int, default=8)
    parser.add_argument(
        "--topic",
        default="general",
        choices=["general", "news"],
    )
    parser.add_argument(
        "--no-answer",
        action="store_true",
        help="AI answer を取得しない(クレジット節約)",
    )
    parser.add_argument(
        "--mfg-preset",
        action="store_true",
        help="製造業向けの推奨ドメインフィルタを使う",
    )
    args = parser.parse_args()

    domain_filter = args.domain_filter
    if args.mfg_preset and not domain_filter:
        domain_filter = DEFAULT_DOMAIN_FILTER_MFG

    try:
        result = research(
            args.query,
            domain_filter=domain_filter,
            recency=args.recency,
            search_depth=args.search_depth,
            max_results=args.max_results,
            include_answer=not args.no_answer,
            topic=args.topic,
        )
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
