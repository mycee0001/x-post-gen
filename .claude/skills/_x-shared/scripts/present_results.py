#!/usr/bin/env python3
"""候補コンテンツをブラウザで表示し、採用/不採用を受け付けるローカルサーバー。

ブラウザ上で:
  - 各候補の Adopt / Skip ボタンで採用・不採用を選択
  - Copy ボタンでクリップボードにコピー
  - Open in X リンクで X に遷移
  - 全候補の判定後「Complete」ボタンで結果を CLI に返す
  - スキップが 1 件でもあれば理由収集フォーム (3カテゴリ + 自由記述) を表示

使い方:
  python3 present_results.py --kind post --json '<JSON>'
  python3 present_results.py --kind reply --json '<JSON>'
  python3 present_results.py --kind quote --json '<JSON>'

戻り値 (stdout JSON):
  {"adopted": [1, 3], "skipped": [2, 4, 5], "feedback": [...], "auto_adopted": false}

タイムアウト動作:
  10 分間 Complete が押されない場合、すべての候補を「強制採用」して
  {"adopted": [...全番号], "skipped": [], "feedback": [], "auto_adopted": true}
  を返す。これにより履歴管理が中断されない。
"""
from __future__ import annotations

import argparse
import json
import socket
import threading
import webbrowser
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

JST = timezone(timedelta(hours=9))
TIMEOUT_SECONDS = 600  # 10 分

# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------

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
  h1 {{ font-size: 1.3rem; margin-bottom: 8px; color: #1d9bf0; }}
  h2 {{ font-size: 1.1rem; margin-bottom: 12px; color: #1d9bf0; }}
  .subtitle {{ color: #71767b; font-size: 0.85rem; margin-bottom: 16px; }}
  .card {{
    background: #16181c; border: 1px solid #2f3336; border-radius: 12px;
    padding: 16px; margin-bottom: 16px; transition: opacity 0.3s, border-color 0.3s;
  }}
  .card.adopted {{ border-color: #00ba7c; }}
  .card.skipped {{ opacity: 0.4; border-color: #2f3336; }}
  .card-header {{
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 12px; font-size: 0.85rem; color: #71767b;
  }}
  .badge {{ padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }}
  .badge-safe {{ background: #00ba7c22; color: #00ba7c; }}
  .badge-warn {{ background: #ffd40022; color: #ffd400; }}
  .status-badge {{ padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }}
  .status-adopted {{ background: #00ba7c; color: #fff; }}
  .status-skipped {{ background: #536471; color: #fff; }}
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
    display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap;
  }}
  .btn {{
    padding: 8px 16px; border-radius: 20px; border: none;
    font-size: 0.85rem; font-weight: 600; cursor: pointer;
    transition: all 0.2s; display: inline-flex; align-items: center; gap: 4px;
  }}
  .btn:hover {{ opacity: 0.85; }}
  .btn:disabled {{ opacity: 0.3; cursor: not-allowed; }}
  .btn-adopt {{ background: #00ba7c; color: #fff; }}
  .btn-skip {{ background: #536471; color: #fff; }}
  .btn-copy {{ background: #1d9bf0; color: #fff; }}
  .btn-copy.copied {{ background: #00ba7c; }}
  .btn-open {{
    background: transparent; border: 1px solid #536471; color: #e7e9ea;
    text-decoration: none;
  }}
  .btn-open:hover {{ border-color: #1d9bf0; color: #1d9bf0; }}
  .complete-bar {{
    position: sticky; bottom: 0; background: #16181c; border-top: 1px solid #2f3336;
    padding: 16px; margin: 0 -20px; text-align: center;
  }}
  .btn-complete {{
    background: #1d9bf0; color: #fff; padding: 12px 32px;
    border-radius: 24px; border: none; font-size: 1rem; font-weight: 700;
    cursor: pointer; transition: all 0.2s;
  }}
  .btn-complete:hover {{ background: #1a8cd8; }}
  .btn-complete:disabled {{ background: #536471; cursor: not-allowed; }}
  .progress {{ color: #71767b; font-size: 0.85rem; margin-bottom: 8px; }}
  .countdown {{ color: #ffd400; font-size: 0.75rem; margin-top: 4px; }}
  .author {{ color: #1d9bf0; font-weight: 600; }}
  .angle {{ color: #71767b; font-size: 0.8rem; }}
  .done-message {{
    text-align: center; padding: 40px; color: #00ba7c; font-size: 1.1rem;
  }}
  .done-message p {{ margin-top: 8px; color: #71767b; font-size: 0.85rem; }}
  .feedback-intro {{
    background: #16181c; border: 1px solid #ffd40044; border-radius: 12px;
    padding: 16px; margin-bottom: 16px; font-size: 0.9rem; color: #ffd400;
  }}
  .feedback-card {{
    background: #16181c; border: 1px solid #2f3336; border-radius: 12px;
    padding: 16px; margin-bottom: 16px;
  }}
  .feedback-snippet {{
    background: #0a0a0a; border-radius: 6px; padding: 8px 12px;
    margin-bottom: 12px; font-size: 0.85rem; color: #8b98a5; line-height: 1.5;
    max-height: 80px; overflow: hidden; text-overflow: ellipsis;
  }}
  .feedback-row {{ margin-bottom: 10px; }}
  .feedback-row label {{ display: block; font-size: 0.85rem; color: #e7e9ea; margin-bottom: 6px; font-weight: 600; }}
  .feedback-row select, .feedback-row textarea {{
    width: 100%; background: #000; color: #e7e9ea;
    border: 1px solid #2f3336; border-radius: 8px;
    padding: 8px 12px; font-family: inherit; font-size: 0.9rem;
  }}
  .feedback-row textarea {{ min-height: 60px; resize: vertical; }}
  .feedback-help {{ color: #71767b; font-size: 0.75rem; margin-top: 4px; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="subtitle">Generated at {timestamp} — Adopt or skip each candidate, then click Complete</div>

<div id="cards">
{cards}
</div>

<div id="feedback-section" style="display:none;">
  <h2>スキップ理由を教えてください</h2>
  <div class="feedback-intro">
    調整ロジックを改善するため、スキップした候補ごとに理由カテゴリを選んでください。
    自由記述は任意ですが具体的だと精度が上がります。
  </div>
  <div id="feedback-cards"></div>
</div>

<div class="complete-bar" id="complete-bar">
  <div class="progress" id="progress">0 / {total} decided</div>
  <div class="countdown" id="countdown">⏱ 自動採用まで残り <span id="remaining">10:00</span> (応答なしで全候補を強制採用)</div>
  <button class="btn-complete" id="btn-complete" disabled onclick="handleComplete()">
    Complete
  </button>
</div>

<script>
const total = {total};
const decisions = {{}};
const itemsData = {items_json};
let phase = 'decide';  // decide | feedback

function decide(num, action) {{
  decisions[num] = action;
  const card = document.getElementById('card-' + num);
  card.className = 'card ' + (action === 'adopt' ? 'adopted' : 'skipped');

  const adoptBtn = document.getElementById('adopt-' + num);
  const skipBtn = document.getElementById('skip-' + num);
  if (action === 'adopt') {{
    adoptBtn.disabled = true;
    adoptBtn.innerHTML = 'Adopted';
    skipBtn.disabled = true;
  }} else {{
    skipBtn.disabled = true;
    skipBtn.innerHTML = 'Skipped';
    adoptBtn.disabled = true;
  }}

  const header = card.querySelector('.card-header');
  const existing = header.querySelector('.status-badge');
  if (existing) existing.remove();
  const badge = document.createElement('span');
  badge.className = 'status-badge ' + (action === 'adopt' ? 'status-adopted' : 'status-skipped');
  badge.textContent = action === 'adopt' ? 'ADOPTED' : 'SKIPPED';
  header.appendChild(badge);

  updateProgress();
}}

function updateProgress() {{
  const decided = Object.keys(decisions).length;
  document.getElementById('progress').textContent = decided + ' / ' + total + ' decided';
  document.getElementById('btn-complete').disabled = (decided < total);
}}

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

function handleComplete() {{
  if (phase === 'decide') {{
    const skipped = Object.entries(decisions)
      .filter(([_, a]) => a === 'skip')
      .map(([n, _]) => parseInt(n));
    if (skipped.length === 0) {{
      submitFinal([]);
    }} else {{
      showFeedbackForm(skipped);
    }}
  }} else if (phase === 'feedback') {{
    const feedback = collectFeedback();
    submitFinal(feedback);
  }}
}}

function showFeedbackForm(skippedNums) {{
  phase = 'feedback';
  document.getElementById('cards').style.display = 'none';
  const fbSection = document.getElementById('feedback-section');
  const fbCards = document.getElementById('feedback-cards');
  fbSection.style.display = 'block';
  fbCards.innerHTML = '';

  for (const num of skippedNums) {{
    const item = itemsData.find(i => i.number === num) || {{}};
    const snippet = item.reply_text || item.comment_text || item.text || '';
    const sourceText = item.source_text || '';
    const author = item.author || '';

    const div = document.createElement('div');
    div.className = 'feedback-card';
    div.innerHTML = `
      <div class="card-header"><span>#${{num}}${{author ? ' | <span class="author">' + escapeHtml(author) + '</span>' : ''}}</span></div>
      ${{sourceText ? '<div class="feedback-snippet">引用元: ' + escapeHtml(sourceText.slice(0,100)) + '</div>' : ''}}
      <div class="feedback-snippet">原稿: ${{escapeHtml(snippet.slice(0,100))}}</div>
      <div class="feedback-row">
        <label>カテゴリ <span style="color:#71767b;font-weight:400;">(必須)</span></label>
        <select id="fb-cat-${{num}}">
          <option value="source">① 収集された元ポストが不適切 (検索クエリ・対象アカウント)</option>
          <option value="content">② 生成原稿の内容が不適切 (トーン・切り口・自己言及)</option>
          <option value="flame">③ 炎上チェックの判定がおかしい (誤検知 or 見逃し)</option>
          <option value="other">④ その他</option>
        </select>
      </div>
      <div class="feedback-row">
        <label>具体的な理由 <span style="color:#71767b;font-weight:400;">(任意・推奨)</span></label>
        <textarea id="fb-reason-${{num}}" placeholder="例: このアカウントは政治的なポストが多いので外したい / もう少し簡潔にしたい / 数字を出さなくていい 等"></textarea>
        <div class="feedback-help">次回実行時、Claude がこの理由を読んでクエリ・原稿・炎上判定を調整します。</div>
      </div>
    `;
    fbCards.appendChild(div);
  }}

  document.getElementById('progress').textContent = 'スキップ理由を入力後、Complete を再度クリック';
  document.getElementById('btn-complete').disabled = false;
  document.getElementById('btn-complete').textContent = 'フィードバック送信して完了';
}}

function collectFeedback() {{
  const skipped = Object.entries(decisions)
    .filter(([_, a]) => a === 'skip')
    .map(([n, _]) => parseInt(n));
  const feedback = [];
  for (const num of skipped) {{
    const cat = document.getElementById('fb-cat-' + num).value;
    const reason = document.getElementById('fb-reason-' + num).value.trim();
    const item = itemsData.find(i => i.number === num) || {{}};
    feedback.push({{
      number: num,
      category: cat,
      reason: reason,
      item: {{
        url: item.url || '',
        author: item.author || '',
        source_text: item.source_text || '',
        text: item.reply_text || item.comment_text || item.text || ''
      }}
    }});
  }}
  return feedback;
}}

function escapeHtml(s) {{
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}}

function submitFinal(feedback) {{
  const adopted = [];
  const skipped = [];
  for (const [num, action] of Object.entries(decisions)) {{
    if (action === 'adopt') adopted.push(parseInt(num));
    else skipped.push(parseInt(num));
  }}
  adopted.sort();
  skipped.sort();

  fetch('/complete', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify({{ adopted, skipped, feedback }})
  }}).then(r => r.json()).then(data => {{
    document.getElementById('cards').innerHTML = '';
    document.getElementById('feedback-section').style.display = 'none';
    document.getElementById('complete-bar').innerHTML =
      '<div class="done-message">' +
      'Completed! Adopted ' + adopted.length + ' / ' + total +
      (feedback.length ? '<p>フィードバック ' + feedback.length + ' 件を保存しました</p>' : '') +
      '<p>You can close this tab now.</p></div>';
  }});
}}

// ---- Countdown timer (auto-adopt at 10 min) ----
let secondsLeft = {timeout_seconds};
function tickCountdown() {{
  const m = Math.floor(secondsLeft / 60);
  const s = secondsLeft % 60;
  const el = document.getElementById('remaining');
  if (el) el.textContent = m + ':' + (s < 10 ? '0' + s : s);
  secondsLeft -= 1;
  if (secondsLeft < 0) return;
  setTimeout(tickCountdown, 1000);
}}
tickCountdown();
</script>
</body>
</html>"""

# ---------------------------------------------------------------------------
# Card Templates
# ---------------------------------------------------------------------------

CARD_POST = """<div class="card" id="card-{number}">
  <div class="card-header">
    <span>#{number} | <span class="angle">{angle}</span></span>
    <span class="badge {badge_class}">{flame}</span>
  </div>
  <div class="content-box" id="content-{number}">{text}</div>
  <div class="actions">
    <button class="btn btn-adopt" id="adopt-{number}" onclick="decide({number},'adopt')">Adopt</button>
    <button class="btn btn-skip" id="skip-{number}" onclick="decide({number},'skip')">Skip</button>
    <button class="btn btn-copy" onclick="copyText(this, 'content-{number}')">Copy</button>
  </div>
</div>"""

CARD_REPLY = """<div class="card" id="card-{number}">
  <div class="card-header">
    <span>#{number} | <span class="author">{author}</span></span>
    <span class="badge {badge_class}">{flame}</span>
  </div>
  <div class="source-text">{source_text}</div>
  <div class="content-box" id="content-{number}">{reply_text}</div>
  <div class="actions">
    <button class="btn btn-adopt" id="adopt-{number}" onclick="decide({number},'adopt')">Adopt</button>
    <button class="btn btn-skip" id="skip-{number}" onclick="decide({number},'skip')">Skip</button>
    <button class="btn btn-copy" onclick="copyText(this, 'content-{number}')">Copy</button>
    <a class="btn btn-open" href="{url}" target="_blank" rel="noopener">Open in X</a>
  </div>
</div>"""

CARD_QUOTE = """<div class="card" id="card-{number}">
  <div class="card-header">
    <span>#{number} | <span class="author">{author}</span></span>
    <span class="badge {badge_class}">{flame}</span>
  </div>
  <div class="source-text">{source_text}</div>
  <div class="content-box" id="content-{number}">{comment_text}</div>
  <div class="actions">
    <button class="btn btn-adopt" id="adopt-{number}" onclick="decide({number},'adopt')">Adopt</button>
    <button class="btn btn-skip" id="skip-{number}" onclick="decide({number},'skip')">Skip</button>
    <button class="btn btn-copy" onclick="copyText(this, 'content-{number}')">Copy</button>
    <a class="btn btn-open" href="{url}" target="_blank" rel="noopener">Open in X</a>
  </div>
</div>"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        bc = _badge_class(item.get("flame", "SAFE"))
        n = item["number"]
        if kind == "post":
            cards_html.append(CARD_POST.format(
                number=n, angle=_escape(item.get("angle", "")),
                flame=item.get("flame", "SAFE"), badge_class=bc,
                text=_escape(item["text"]),
            ))
        elif kind == "reply":
            cards_html.append(CARD_REPLY.format(
                number=n, author=_escape(item.get("author", "")),
                flame=item.get("flame", "SAFE"), badge_class=bc,
                source_text=_escape(item.get("source_text", "")),
                reply_text=_escape(item["reply_text"]),
                url=_escape(item.get("url", "")),
            ))
        elif kind == "quote":
            cards_html.append(CARD_QUOTE.format(
                number=n, author=_escape(item.get("author", "")),
                flame=item.get("flame", "SAFE"), badge_class=bc,
                source_text=_escape(item.get("source_text", "")),
                comment_text=_escape(item["comment_text"]),
                url=_escape(item.get("url", "")),
            ))

    title = f"X {kind_label} Candidates ({len(items)})"
    items_json = json.dumps(items, ensure_ascii=False)
    return HTML_TEMPLATE.format(
        kind_label=kind_label, title=title,
        cards="\n".join(cards_html), timestamp=timestamp,
        total=len(items),
        items_json=items_json,
        timeout_seconds=TIMEOUT_SECONDS,
    )


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# HTTP Server
# ---------------------------------------------------------------------------

class RequestHandler(BaseHTTPRequestHandler):
    html_content: str = ""
    result: dict | None = None
    result_event: threading.Event

    def log_message(self, format, *args):
        pass  # suppress logs

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(self.html_content.encode("utf-8"))

    def do_POST(self):
        if self.path == "/complete":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            RequestHandler.result = data
            RequestHandler.result_event.set()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Present X skill results in browser")
    parser.add_argument("--kind", required=True, choices=["post", "reply", "quote"])
    parser.add_argument("--json", required=True, help="JSON array of candidates")
    args = parser.parse_args()

    items = json.loads(args.json)
    html = build_html(args.kind, items)

    port = find_free_port()
    RequestHandler.html_content = html
    RequestHandler.result = None
    RequestHandler.result_event = threading.Event()

    server = HTTPServer(("127.0.0.1", port), RequestHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    url = f"http://127.0.0.1:{port}"
    webbrowser.open(url)

    # Wait for user to complete
    completed = RequestHandler.result_event.wait(timeout=TIMEOUT_SECONDS)

    server.shutdown()

    if completed and RequestHandler.result is not None:
        result = RequestHandler.result
        result.setdefault("auto_adopted", False)
        result.setdefault("feedback", [])
        print(json.dumps(result, ensure_ascii=False))
    else:
        # タイムアウト → 全候補を強制採用 (履歴管理を中断させない)
        all_numbers = [i["number"] for i in items]
        print(json.dumps({
            "adopted": all_numbers,
            "skipped": [],
            "feedback": [],
            "auto_adopted": True,
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
