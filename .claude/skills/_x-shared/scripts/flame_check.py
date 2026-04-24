"""flame_rules.yaml のルールでテキストを BLOCK/WARN/SAFE 判定する。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as e:  # pragma: no cover
    print(
        "ERROR: pyyaml が見つかりません。pip install pyyaml を実行してください。",
        file=sys.stderr,
    )
    raise

DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "flame_rules.yaml"

SEVERITY_ORDER = {"SAFE": 0, "WARN": 1, "BLOCK": 2}


# ---- カスタム関数 ---------------------------------------------------------


def check_stats_have_source(text: str, context: dict[str, Any] | None = None) -> bool:
    """数字が含まれるが URL らしき文字列が本文に無い場合 True(違反あり)。"""
    # 「3倍」「40%」「1,200社」「約500万円」のようなパターン
    number_pattern = re.compile(
        r"(\d{1,3}(,\d{3})+|\d{2,})\s*(倍|％|%|社|人|万|億|兆|円|ドル|時間|分|秒|日|年)"
    )
    has_number = bool(number_pattern.search(text))
    if not has_number:
        return False
    has_url = bool(re.search(r"https?://\S+", text))
    # context.sources がある場合は OK とする
    if context and context.get("sources"):
        return False
    return not has_url


def check_emoji_count(text: str, context: dict[str, Any] | None = None) -> bool:
    """絵文字が 3 個超なら True(違反あり)。"""
    emoji_re = re.compile(
        "["
        "\U0001F300-\U0001F5FF"
        "\U0001F600-\U0001F64F"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\u2600-\u27BF"
        "]"
    )
    return len(emoji_re.findall(text)) > 3


CUSTOM_FUNCTIONS = {
    "check_stats_have_source": check_stats_have_source,
    "check_emoji_count": check_emoji_count,
}


# ---- ルール適用 -----------------------------------------------------------


def _load_rules(rules_path: str | Path | None = None) -> list[dict[str, Any]]:
    path = Path(rules_path) if rules_path else DEFAULT_RULES_PATH
    if not path.exists():
        raise FileNotFoundError(f"flame_rules.yaml が見つかりません: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("rules", [])


def _rule_hits(rule: dict[str, Any], text: str, context: dict[str, Any] | None) -> bool:
    if rule.get("check") == "custom_function":
        fn_name = rule.get("custom_function")
        fn = CUSTOM_FUNCTIONS.get(fn_name)
        if fn is None:
            return False
        try:
            return bool(fn(text, context))
        except Exception:
            return False

    for p in rule.get("patterns", []) or []:
        ptype = p.get("type")
        if ptype == "regex":
            try:
                if re.search(p.get("pattern", ""), text):
                    return True
            except re.error:
                continue
        elif ptype == "keyword":
            for kw in p.get("keywords", []) or []:
                if kw and kw in text:
                    return True
    return False


def check(
    text: str,
    context: dict[str, Any] | None = None,
    rules_path: str | Path | None = None,
) -> dict[str, Any]:
    """text を判定して結果を返す。"""
    rules = _load_rules(rules_path)
    warnings: list[dict[str, Any]] = []
    max_severity = "SAFE"
    for rule in rules:
        sev = rule.get("severity", "WARN")
        if _rule_hits(rule, text, context):
            warnings.append(
                {
                    "rule_id": rule.get("id", "?"),
                    "message": rule.get("description", ""),
                    "severity": sev,
                }
            )
            if SEVERITY_ORDER.get(sev, 0) > SEVERITY_ORDER.get(max_severity, 0):
                max_severity = sev
    return {"score": max_severity, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser(description="炎上チェック")
    parser.add_argument("--text", help="判定するテキスト")
    parser.add_argument("--text-file", help="判定するテキストが入ったファイル")
    parser.add_argument(
        "--context-json",
        default="{}",
        help="コンテキスト JSON(例: '{\"sources\": [...]}'",
    )
    parser.add_argument("--rules", help="flame_rules.yaml のパス")
    args = parser.parse_args()

    if args.text is None and args.text_file is None:
        print("ERROR: --text か --text-file のいずれかを指定してください", file=sys.stderr)
        return 2

    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8")
    else:
        text = args.text or ""

    try:
        ctx = json.loads(args.context_json) if args.context_json else None
    except json.JSONDecodeError as e:
        print(f"ERROR: --context-json 不正: {e}", file=sys.stderr)
        return 2

    result = check(text, ctx, args.rules)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
