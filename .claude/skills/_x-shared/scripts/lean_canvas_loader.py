"""lean-canvas-{service}.md を読み込み、構造化データに変換する。

仕様:
- `## N. SECTION_NAME` の見出しでセクション分割
- 各セクション内の `####` と `-` 箇条書きを抽出
- UVP / PROBLEM / UNFAIR ADVANTAGE から主要キーワードを `topic_tags` に抽出
- ファイル名から `service` 識別子を抽出 (例: lean-canvas-stow.md → "stow")
- `--discover` モードでカレントディレクトリの全 lean-canvas を自動検出
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

SECTION_KEYS = {
    "problem": ["problem", "課題", "問題"],
    "customer_segments": ["customer segments", "customer_segments", "顧客セグメント", "customer"],
    "uvp": ["uvp", "unique value proposition", "独自価値提案", "価値提案"],
    "solution": ["solution", "ソリューション", "解決策"],
    "channels": ["channels", "チャネル"],
    "revenue_streams": ["revenue streams", "revenue", "収益", "収益モデル"],
    "cost_structure": ["cost structure", "cost", "コスト", "コスト構造"],
    "key_metrics": ["key metrics", "metrics", "主要指標", "kpi"],
    "unfair_advantage": ["unfair advantage", "unfair_advantage", "圧倒的優位性", "競争優位"],
}

HEADING_RE = re.compile(r"^##+\s+(?:\d+\.\s*)?(.+?)\s*$")
BULLET_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")
FILENAME_RE = re.compile(r"^lean-canvas(?:-(?P<service>[a-zA-Z0-9_.-]+))?\.md$")


def _normalize_heading(heading: str) -> str | None:
    h = heading.strip().lower()
    for key, aliases in SECTION_KEYS.items():
        for alias in aliases:
            if alias.lower() in h:
                return key
    return None


def _extract_keywords(texts: list[str], max_n: int = 10) -> list[str]:
    """箇条書きテキスト群から簡易キーワード抽出。

    実装方針: 「」『』で囲まれたトークン、英数字混在トークン、
    および 2〜12 文字の漢字/カタカナトークンを候補にして上位を返す。
    """
    candidates: list[str] = []
    patterns = [
        re.compile(r"[「『](.+?)[」』]"),
        re.compile(r"([A-Za-z][A-Za-z0-9\-]{2,})"),
        re.compile(r"([一-鿿]{2,6})"),
        re.compile(r"([゠-ヿ]{2,10})"),
    ]
    for t in texts:
        for p in patterns:
            candidates.extend(p.findall(t))
    # 重複除去しつつ順序保持
    seen: set[str] = set()
    result: list[str] = []
    stopwords = {"こと", "ため", "これ", "それ", "あれ", "もの", "よう", "等々", "など"}
    for c in candidates:
        c = c.strip()
        if not c or c in stopwords:
            continue
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(c)
        if len(result) >= max_n:
            break
    return result


def _service_from_filename(path: Path) -> str:
    """ファイル名から service 識別子を抽出。

    - lean-canvas-stow.md → "stow"
    - lean-canvas-synapseize.md → "synapseize"
    - lean-canvas.md → "default" (互換)
    - その他 → ファイル stem そのまま
    """
    m = FILENAME_RE.match(path.name)
    if m and m.group("service"):
        return m.group("service").lower()
    if path.name == "lean-canvas.md":
        return "default"
    return path.stem.lower()


def load_canvas(path: str = "./lean-canvas.md") -> dict[str, Any]:
    """lean-canvas-*.md を 1 ファイル読み込んで辞書を返す。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"lean-canvas が見つかりません: {path}\n"
            f"カレントディレクトリにキャンバスを置くか、--path で指定してください。"
        )
    raw = p.read_text(encoding="utf-8")

    sections: dict[str, list[str]] = {k: [] for k in SECTION_KEYS}
    current_key: str | None = None

    for line in raw.splitlines():
        m = HEADING_RE.match(line)
        if m:
            key = _normalize_heading(m.group(1))
            current_key = key
            continue
        if current_key is None:
            continue
        bm = BULLET_RE.match(line)
        if bm:
            sections[current_key].append(bm.group(1).strip())
        else:
            stripped = line.strip()
            # 見出しでも箇条書きでもない本文行: 空でなければ段落として追加
            if stripped and not stripped.startswith("#"):
                sections[current_key].append(stripped)

    # topic_tags は UVP, PROBLEM, UNFAIR ADVANTAGE から抽出
    tag_source: list[str] = []
    for k in ("uvp", "problem", "unfair_advantage", "solution"):
        tag_source.extend(sections.get(k, []))
    topic_tags = _extract_keywords(tag_source, max_n=15)

    content_hash = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    service = _service_from_filename(p)

    return {
        "service": service,
        "path": str(p),
        "raw_text": raw,
        "sections": sections,
        "topic_tags": topic_tags,
        "content_hash": content_hash,
    }


def discover_canvases(cwd: str = ".") -> list[dict[str, Any]]:
    """カレントディレクトリの lean-canvas-*.md と lean-canvas.md を全件読み込む。

    優先順位:
    - lean-canvas-{service}.md が 1 件以上ある場合 → それらを返す
    - 1 件もない場合 → lean-canvas.md を service="default" として返す
    - 両方無ければ FileNotFoundError

    返すリストは service 名のアルファベット順。
    """
    base = Path(cwd)
    suffixed = sorted(
        [p for p in base.glob("lean-canvas-*.md") if p.is_file()],
        key=lambda p: p.name,
    )
    plain = base / "lean-canvas.md"

    paths: list[Path] = []
    if suffixed:
        paths.extend(suffixed)
        # サフィックス付きファイルがある場合は plain は無視 (旧名は使わない)
    elif plain.exists():
        paths.append(plain)
    else:
        raise FileNotFoundError(
            f"lean-canvas-*.md / lean-canvas.md が {cwd} に見つかりません。\n"
            f"カレントディレクトリに最低 1 ファイル配置してください。"
        )

    return [load_canvas(str(p)) for p in paths]


def _summary(canvas: dict[str, Any]) -> str:
    lines = [f"=== lean-canvas 読み込み結果 (service={canvas['service']}) ==="]
    for key, values in canvas["sections"].items():
        if not values:
            continue
        lines.append(f"\n[{key}]")
        for v in values[:5]:
            lines.append(f"  - {v}")
        if len(values) > 5:
            lines.append(f"  ... 他 {len(values) - 5} 件")
    lines.append(f"\n[topic_tags]")
    lines.append("  " + ", ".join(canvas["topic_tags"]))
    lines.append(f"\n[content_hash] {canvas['content_hash'][:16]}...")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="lean-canvas-*.md を読み込んで構造化する")
    parser.add_argument("--path", default=None, help="単一ファイルのパス。--discover と排他")
    parser.add_argument(
        "--discover",
        action="store_true",
        help="カレントディレクトリの lean-canvas-*.md を全件読み込む",
    )
    parser.add_argument("--cwd", default=".", help="--discover の起点ディレクトリ")
    parser.add_argument("--json", action="store_true", help="JSON で出力")
    args = parser.parse_args()

    if args.discover and args.path:
        print("ERROR: --path と --discover は同時指定できません", file=sys.stderr)
        return 2

    try:
        if args.discover:
            canvases = discover_canvases(args.cwd)
            if args.json:
                print(json.dumps(canvases, ensure_ascii=False, indent=2))
            else:
                for c in canvases:
                    print(_summary(c))
                    print()
        else:
            path = args.path or "./lean-canvas.md"
            canvas = load_canvas(path)
            if args.json:
                print(json.dumps(canvas, ensure_ascii=False, indent=2))
            else:
                print(_summary(canvas))
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
