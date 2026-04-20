"""Perplexity Sonar Pro でニュース・論文を調査する。

OpenAI 互換 SDK を使い、sonar-pro モデルを呼び出す。
citation は `search_results` / `citations` フィールドから抽出する。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from openai import OpenAI
except ImportError as e:  # pragma: no cover
    print("ERROR: openai SDK が必要です。pip install openai", file=sys.stderr)
    raise

try:
    from .utils import load_env, mask_secret
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from utils import load_env, mask_secret  # type: ignore

PERPLEXITY_BASE_URL = "https://api.perplexity.ai"
DEFAULT_MODEL = "sonar-pro"

DEFAULT_DOMAIN_FILTER_MFG = [
    "meti.go.jp",
    "monoist.itmedia.co.jp",
    "nikkei.com",
    "prtimes.jp",
    "nikkeibp.co.jp",
    "xtech.nikkei.com",
]

SYSTEM_PROMPT_JA = (
    "あなたは日本の製造業・SaaS 業界に精通したリサーチアシスタントです。"
    "ユーザーのクエリに対して、信頼できる一次情報(政府統計・大手メディア・企業発表)を優先し、"
    "事実に基づいた簡潔な要約と複数の出典を示してください。推測や断定は避け、"
    "日付と出典を明記してください。"
)


def _get_client() -> OpenAI:
    load_env()
    api_key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "PERPLEXITY_API_KEY が設定されていません。.env に記入してください。"
        )
    return OpenAI(api_key=api_key, base_url=PERPLEXITY_BASE_URL)


def research(
    query: str,
    domain_filter: list[str] | None = None,
    recency: str = "month",
    model: str = DEFAULT_MODEL,
    max_tokens: int = 800,
) -> dict[str, Any]:
    """Perplexity で調査して結果を返す。"""
    client = _get_client()

    extra_body: dict[str, Any] = {}
    if domain_filter:
        extra_body["search_domain_filter"] = domain_filter
    if recency:
        extra_body["search_recency_filter"] = recency

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_JA},
                {"role": "user", "content": query},
            ],
            max_tokens=max_tokens,
            extra_body=extra_body,
        )
    except Exception as e:
        raise RuntimeError(f"Perplexity API 呼び出しに失敗: {e}") from e

    answer = ""
    if resp.choices and resp.choices[0].message.content:
        answer = resp.choices[0].message.content

    citations = _extract_citations(resp)
    usage = {}
    if getattr(resp, "usage", None):
        try:
            usage = {
                "total_tokens": resp.usage.total_tokens,
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
            }
        except AttributeError:
            usage = {}

    return {
        "answer": answer,
        "citations": citations,
        "usage": usage,
        "query": query,
    }


def _extract_citations(resp: Any) -> list[dict[str, Any]]:
    """レスポンスから citation を抽出(Perplexity の仕様は変化するため防衛的に)。"""
    citations: list[dict[str, Any]] = []

    # 1) search_results (新しい仕様)
    search_results = getattr(resp, "search_results", None)
    if search_results:
        for sr in search_results:
            citations.append(
                {
                    "url": _get(sr, "url"),
                    "title": _get(sr, "title") or "",
                    "snippet": _get(sr, "snippet") or "",
                    "date": _get(sr, "date") or "",
                }
            )
    if citations:
        return citations

    # 2) citations (旧仕様、URL のみ)
    raw_citations = getattr(resp, "citations", None)
    if raw_citations:
        for c in raw_citations:
            if isinstance(c, str):
                citations.append({"url": c, "title": "", "snippet": "", "date": ""})
            elif isinstance(c, dict):
                citations.append(
                    {
                        "url": c.get("url", ""),
                        "title": c.get("title", ""),
                        "snippet": c.get("snippet", ""),
                        "date": c.get("date", ""),
                    }
                )

    # 3) model_dump から潜り込んで探す
    if not citations:
        try:
            dumped = resp.model_dump()
        except AttributeError:
            dumped = {}
        for key in ("citations", "search_results"):
            val = dumped.get(key)
            if isinstance(val, list):
                for c in val:
                    if isinstance(c, str):
                        citations.append(
                            {"url": c, "title": "", "snippet": "", "date": ""}
                        )
                    elif isinstance(c, dict):
                        citations.append(
                            {
                                "url": c.get("url", ""),
                                "title": c.get("title", ""),
                                "snippet": c.get("snippet", ""),
                                "date": c.get("date", ""),
                            }
                        )
                if citations:
                    break
    return citations


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def research_multi(
    queries: list[str],
    domain_filter: list[str] | None = None,
    recency: str = "month",
    model: str = DEFAULT_MODEL,
) -> list[dict[str, Any]]:
    """複数クエリを順次実行。"""
    results: list[dict[str, Any]] = []
    for q in queries:
        try:
            results.append(research(q, domain_filter, recency, model))
        except Exception as e:
            results.append(
                {"answer": "", "citations": [], "usage": {}, "query": q, "error": str(e)}
            )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Perplexity Sonar Pro で調査")
    parser.add_argument("--query", required=True)
    parser.add_argument(
        "--domain-filter",
        nargs="*",
        default=None,
        help="ドメインフィルタのリスト(空白区切り)",
    )
    parser.add_argument(
        "--recency",
        default="month",
        choices=["day", "week", "month", "year"],
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--mfg-preset",
        action="store_true",
        help="製造業向けの推奨ドメインフィルタを使う",
    )
    parser.add_argument("--max-tokens", type=int, default=800)
    args = parser.parse_args()

    domain_filter = args.domain_filter
    if args.mfg_preset and not domain_filter:
        domain_filter = DEFAULT_DOMAIN_FILTER_MFG

    try:
        result = research(
            args.query,
            domain_filter=domain_filter,
            recency=args.recency,
            model=args.model,
            max_tokens=args.max_tokens,
        )
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
