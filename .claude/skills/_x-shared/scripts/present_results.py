#!/usr/bin/env python3
"""候補コンテンツを一時 HTML ファイルとしてブラウザで表示する。

使い方:
  python3 present_results.py --kind post --json '<JSON>'
  python3 present_results.py --kind reply --json '<JSON>'
  python3 present_results.py --kind quote --json '<JSON>'

JSON スキーマ (配列):
  post:  [{"number": 1, "text": "...", "angle": "...", "flame": "SAFE"}]
  reply: [{"number": 1, "url": "...", "author": "@...", "source_text": "...", "reply_text": "...", "flame": "SAFE"}]
  quote: [{"number": 1, "url": "...", "author": "@...", "source_text": "...", "comment_text": "...", "flame": "SAFE"}]

ブラウザで開いた後、ユーザーがコピー・URL 遷移を行い、タブを閉じる。
一時ファイルは /tmp に作成される。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>X {kind_label} - {timestamp}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0f0f0f; color: #e7e9ea; padding: 20px;
    max-width: 680px; margin: 0 auto;
  }}
  h1 {{ font-size: 1.3rem; margin-bottom: 16px; color: #1d9bf0; }}
  .card {{
    background: #16181c; border: 1px solid #2f3336; border-radius: 12px;
    padding: 16px; margin-bottom: 16px;
  }}
  .card-header {{
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 12px; font-size: 0.85rem; color: #71767b;
  }}
  .badge {{ padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }}
  .badge-safe {{ background: #00ba7c22; color: #00ba7c; }}
  .badge-warn {{ background: #ffd40022; color: #ffd400; }}
  .source-text {{
    background: #1e1e1e; border-left: 3px solid #2f3336;
    padding: 8px 12px; margin-bottom: 12px; font-size: 0.9rem;
    color: #8b98a5; line-height: 1.5;
  }}
  .content-box {{
    background: #000; border: 1px solid #2f3336; border-radius: 8px;
    padding: 12px; font-size: 1rem; line-height: 1.6;
    white-space: pre-wrap; word-break: break-word;
  }}
  .actions {{
    display: flex; gap: 8px; margin-top: 12px;
  }}
  .btn {{
    padding: 8px 16px; border-radius: 20px; border: none;
    font-size: 0.85rem; font-weight: 600; cursor: pointer;
    transition: opacity 0.2s;
  }}
  .btn:hover {{ opacity: 0.85; }}
  .btn-copy {{
    background: #1d9bf0; color: #fff;
  }}
  .btn-copy.copied {{
    background: #00ba7c;
  }}
  .btn-open {{
    background: transparent; border: 1px solid #536471; color: #e7e9ea;
  }}
  .btn-open:hover {{ border-color: #1d9bf0; color: #1d9bf0; }}
  .author {{ color: #1d9bf0; font-weight: 600; }}
  .angle {{ color: #71767b; font-size: 0.8rem; }}
  .footer {{
    text-align: center; color: #536471; font-size: 0.75rem;
    margin-top: 24px; padding-top: 16px; border-top: 1px solid #2f3336;
  }}
</style>
</head>
<body>
<h1>{title}</h1>
{cards}
<div class="footer">
  Generated at {timestamp} | Close this tab when done
</div>
<script>
function copyText(btn, id) {{
  const el = document.getElementById(id);
  navigator.clipboard.writeText(el.textContent).then(() => {{
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => {{
      btn.textContent = 'Copy';
      btn.classList.remove('copied');
    }}, 2000);
  }});
}}
</script>
</body>
</html>"""

CARD_POST = """<div class="card">
  <div class="card-header">
    <span>#{number} | <span class="angle">{angle}</span></span>
    <span class="badge {badge_class}">{flame}</span>
  </div>
  <div class="content-box" id="content-{number}">{text}</div>
  <div class="actions">
    <button class="btn btn-copy" onclick="copyText(this, 'content-{number}')">Copy</button>
  </div>
</div>"""

CARD_REPLY = """<div class="card">
  <div class="card-header">
    <span>#{number} | <span class="author">{author}</span></span>
    <span class="badge {badge_class}">{flame}</span>
  </div>
  <div class="source-text">{source_text}</div>
  <div class="content-box" id="content-{number}">{reply_text}</div>
  <div class="actions">
    <button class="btn btn-copy" onclick="copyText(this, 'content-{number}')">Copy</button>
    <a class="btn btn-open" href="{url}" target="_blank" rel="noopener">Open in X</a>
  </div>
</div>"""

CARD_QUOTE = """<div class="card">
  <div class="card-header">
    <span>#{number} | <span class="author">{author}</span></span>
    <span class="badge {badge_class}">{flame}</span>
  </div>
  <div class="source-text">{source_text}</div>
  <div class="content-box" id="content-{number}">{comment_text}</div>
  <div class="actions">
    <button class="btn btn-copy" onclick="copyText(this, 'content-{number}')">Copy</button>
    <a class="btn btn-open" href="{url}" target="_blank" rel="noopener">Open in X</a>
  </div>
</div>"""


def _badge_class(flame: str) -> str:
    return "badge-warn" if flame == "WARN" else "badge-safe"


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_html(kind: str, items: list[dict]) -> str:
    kind_labels = {"post": "Post", "reply": "Reply", "quote": "Quote"}
    kind_label = kind_labels.get(kind, kind)
    timestamp = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")

    cards_html = []
    for item in items:
        badge_class = _badge_class(item.get("flame", "SAFE"))
        if kind == "post":
            cards_html.append(
                CARD_POST.format(
                    number=item["number"],
                    angle=_escape(item.get("angle", "")),
                    flame=item.get("flame", "SAFE"),
                    badge_class=badge_class,
                    text=_escape(item["text"]),
                )
            )
        elif kind == "reply":
            cards_html.append(
                CARD_REPLY.format(
                    number=item["number"],
                    author=_escape(item.get("author", "")),
                    flame=item.get("flame", "SAFE"),
                    badge_class=badge_class,
                    source_text=_escape(item.get("source_text", "")),
                    reply_text=_escape(item["reply_text"]),
                    url=_escape(item.get("url", "")),
                )
            )
        elif kind == "quote":
            cards_html.append(
                CARD_QUOTE.format(
                    number=item["number"],
                    author=_escape(item.get("author", "")),
                    flame=item.get("flame", "SAFE"),
                    badge_class=badge_class,
                    source_text=_escape(item.get("source_text", "")),
                    comment_text=_escape(item["comment_text"]),
                    url=_escape(item.get("url", "")),
                )
            )

    title = f"X {kind_label} Candidates ({len(items)})"
    return HTML_TEMPLATE.format(
        kind_label=kind_label,
        title=title,
        cards="\n".join(cards_html),
        timestamp=timestamp,
    )


def main():
    parser = argparse.ArgumentParser(description="Present X skill results in browser")
    parser.add_argument("--kind", required=True, choices=["post", "reply", "quote"])
    parser.add_argument("--json", required=True, help="JSON array of candidates")
    args = parser.parse_args()

    items = json.loads(args.json)
    html = build_html(args.kind, items)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", prefix=f"x-{args.kind}-", delete=False, dir="/tmp"
    ) as f:
        f.write(html)
        tmp_path = f.name

    subprocess.run(["open", tmp_path])
    print(json.dumps({"ok": True, "path": tmp_path}))


if __name__ == "__main__":
    main()
