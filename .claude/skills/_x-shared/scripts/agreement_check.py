"""agreement_rules.yaml のルールでテキストを BLOCK/WARN/SAFE 判定する。

x-reply / x-quote 専用の「同意スタンス」検査。元ポストに対する
否定・反論・相対化・上から目線の指摘・敵視メタファー等を検出する。

使い方:
    python3 agreement_check.py --text "<本文>"
    python3 agreement_check.py --text-file path/to/text.txt

戻り値:
    {"score": "SAFE"|"WARN"|"BLOCK", "warnings": [...]}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    print(
        "ERROR: pyyaml が見つかりません。pip install pyyaml を実行してください。",
        file=sys.stderr,
    )
    raise

DEFAULT_RULES_PATH = (
    Path(__file__).resolve().parent.parent / "rules" / "agreement_rules.yaml"
)

SEVERITY_ORDER = {"SAFE": 0, "WARN": 1, "BLOCK": 2}


def _load_rules(rules_path: str | Path | None = None) -> list[dict[str, Any]]:
    path = Path(rules_path) if rules_path else DEFAULT_RULES_PATH
    if not path.exists():
        raise FileNotFoundError(f"agreement_rules.yaml が見つかりません: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("rules", [])


def _rule_hits(rule: dict[str, Any], text: str) -> tuple[bool, str | None]:
    """ルールがマッチするか判定し、マッチした文字列を返す。"""
    for p in rule.get("patterns", []) or []:
        ptype = p.get("type")
        if ptype == "regex":
            try:
                m = re.search(p.get("pattern", ""), text)
                if m:
                    return True, m.group(0)
            except re.error:
                continue
        elif ptype == "keyword":
            for kw in p.get("keywords", []) or []:
                if kw and kw in text:
                    return True, kw
    return False, None


def check(
    text: str,
    rules_path: str | Path | None = None,
) -> dict[str, Any]:
    """text を判定して結果を返す。"""
    rules = _load_rules(rules_path)
    warnings: list[dict[str, Any]] = []
    max_severity = "SAFE"
    for rule in rules:
        sev = rule.get("severity", "WARN")
        hit, matched = _rule_hits(rule, text)
        if hit:
            warnings.append(
                {
                    "rule_id": rule.get("id", "?"),
                    "message": rule.get("description", ""),
                    "severity": sev,
                    "matched": matched,
                }
            )
            if SEVERITY_ORDER.get(sev, 0) > SEVERITY_ORDER.get(max_severity, 0):
                max_severity = sev
    return {"score": max_severity, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="同意スタンス検査 (x-reply / x-quote 用)"
    )
    parser.add_argument("--text", help="判定するテキスト")
    parser.add_argument("--text-file", help="判定するテキストが入ったファイル")
    parser.add_argument("--rules", help="agreement_rules.yaml のパス")
    args = parser.parse_args()

    if args.text is None and args.text_file is None:
        print(
            "ERROR: --text か --text-file のいずれかを指定してください",
            file=sys.stderr,
        )
        return 2

    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8")
    else:
        text = args.text or ""

    result = check(text, args.rules)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
