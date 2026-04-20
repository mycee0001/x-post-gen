# x-post-gen 実装指示書(原本)

> 作成日: 2026-04-20
> 対象: Claude Code でこのリポジトリを実装する際の完全仕様
> プロジェクト名: x-post-gen (原本では unkrypt-x-ops として記載)
> 目的: X (旧Twitter) のビジネスアカウント運用を支援する Claude Code スキル群

> ⚠️ **注意**: このファイルは初期仕様書です。以下の点は実装時に変更されました:
> - Web 調査 API: **Perplexity Sonar Pro → Tavily Search API** に置換(コスト削減と無料枠活用のため)
> - プロジェクト名: unkrypt-x-ops → **x-post-gen**(GitHub リポジトリ名に合わせた)
> - ポスト/引用ツイート生成数: 1 件 → **5 件(ユーザー選択式)**
>
> 現行のアーキテクチャは `docs/architecture.md` を参照してください。

---

## 0. このドキュメントの使い方

このファイルは Claude Code に渡して実装を進めるための**完全な仕様書**です。Claude Code はこのファイルを読み込み、記載された構造・仕様に従って順番に実装してください。

実装の進め方:

1. セクション 1〜3 を読んで全体像を把握する
2. セクション 4 のディレクトリ構造を先に作成する
3. セクション 5 以降の各ファイル仕様に従って実装していく
4. セクション 12 の受け入れ基準を満たしていることを確認する

---

## 1. プロジェクト概要

### 1.1 目的

SaaS「STOW.」を運営する個人事業主 unkrypt の X ビジネスアカウント運用を支援する Claude Code スキル群を構築する。lean-canvas.md を唯一の真実の源 (SoT) とし、キャンバスに沿った一貫性のあるポスト・引用ツイートを継続的に生成する。

### 1.2 実現するもの

- `.claude/skills/` 配下に配置する 2 つのスラッシュコマンド
  - `/x-post` — 新規ポスト生成
  - `/x-quote` — 引用ツイート生成
- GitHub リポジトリで管理し、`curl | bash` でワンコマンドインストール可能にする
- lean-canvas.md を参照し、世界中のニュース・論文を調査した上で原稿を生成する
- 炎上チェックを必ず通す
- 履歴を JSONL で自動管理し、過去の生成物との重複を避ける
- 投稿は行わない。生成物を表示のみ(ユーザーが手動でコピペ投稿)

### 1.3 コスト目標

月 30 ポスト + 30 引用ツイートの運用で**月額 $1 前後**を目指す。

| API | 用途 | 想定コスト/月 |
|---|---|---|
| TwitterAPI.io | X 内引用候補の探索 | 約 $0.13 |
| Perplexity Sonar (Pro) | Web 全般のニュース・論文調査 | 約 $0.90 |
| **合計** | | **約 $1.03** |

---

## 2. 技術選定

### 2.1 X 内探索: TwitterAPI.io

- 公式 X API ではない第三者サービス。$0.15/1,000ツイート の従量課金
- X 認証不要の REST エンドポイント
- ただし X 社規約変更で突然使えなくなるリスクがあるため、クライアントを抽象化して将来差し替え可能にする

### 2.2 Web 調査: Perplexity Sonar Pro

- OpenAI 互換 SDK でリアルタイム Web 検索 + citation 取得
- `search_domain_filter` で信頼できるドメインに絞れる
- モデル名: `sonar-pro`

### 2.3 原稿生成・炎上判定

- Claude Code を実行しているセッションの Claude 自身が生成と判定を担う
- 外部 LLM API は呼ばない (コストとレイテンシの観点)
- 生成プロンプトとルールは `rules/` と `prompts/` に markdown/yaml で置く

### 2.4 履歴管理

- JSONL (追記専用ログ)
- 重複判定は `simhash` ライブラリ (Python) を使用
- ユーザー許可不要で書き込む

### 2.5 投稿

- **実装しない**。生成物を表示するのみ

---

## 3. 動作フロー

### 3.1 /x-post (新規ポスト生成)

```
1. カレントディレクトリの lean-canvas.md を読み込む
   - なければエラーメッセージを出して終了
2. キャンバスからキートピックを抽出
   - PROBLEM、UVP、UNFAIR ADVANTAGE、SOLUTION の各セクションから
   - 各セクションをトピックタグとして正規化
3. .x-history/posts.jsonl を読み込み、直近30日のトピックカバレッジを集計
   - 使われていないトピック or 最も古いトピックを優先
4. Perplexity Sonar で関連ニュース・論文を調査
   - 選択されたトピックに関連するキーワードで検索
   - 日本語と英語の両方で検索
5. ポスト原稿を生成
   - 日本語、280字以内 (絵文字・ハッシュタグ含む)
   - 出典URLを含める
6. 炎上チェック (BLOCK/WARN/SAFE)
   - BLOCK ⇒ ユーザーに再生成を促して停止
   - WARN ⇒ 警告表示しつつ続行
   - SAFE ⇒ そのまま続行
7. 履歴追記 (.x-history/posts.jsonl)
   - ユーザー許可不要
8. 最終出力: コピー可能なコードブロックで表示
```

### 3.2 /x-quote (引用ツイート生成)

```
1. lean-canvas.md を読み込み、キートピック抽出
2. .x-history/quotes.jsonl を読み込み、重複チェック用データをロード
3. TwitterAPI.io で X 内のツイートを検索
   - キャンバスのキーワード + 「製造業 DX」「ものづくり白書」等
   - 直近72時間、日本語優先
   - 最大30件取得
4. Perplexity Sonar で背景情報を補強
5. 候補ツイートをスコアリング
   - 関連性(キャンバスとの一致度)
   - エンゲージメント(いいね/リポスト数)
   - 炎上リスク(投稿アカウントの属性、内容の論争度)
   - 重複ペナルティ(過去30日に同じアカウントを引用済みか等)
6. Top 1〜3 を提示しユーザー選択を待つ
   - ここのみユーザー対話あり
7. 選ばれた候補に対してコメント原稿を生成
   - 日本語、200字以内
8. 炎上チェック
9. 履歴追記 (.x-history/quotes.jsonl)
10. 最終出力: 引用元ツイートURL + コメント原稿
```

---

## 4. ディレクトリ構造

リポジトリ (GitHub) 側:

```
unkrypt-x-ops/
├── README.md
├── LICENSE
├── install.sh
├── .env.example
├── .gitignore
├── IMPLEMENTATION.md               # このファイル (実装完了後に削除 or docs/ へ移動)
├── docs/
│   ├── architecture.md
│   ├── api-costs.md
│   └── troubleshooting.md
├── skills/
│   ├── x-post/
│   │   └── SKILL.md
│   ├── x-quote/
│   │   └── SKILL.md
│   └── _x-shared/
│       ├── requirements.txt
│       ├── scripts/
│       │   ├── __init__.py
│       │   ├── lean_canvas_loader.py
│       │   ├── history.py
│       │   ├── deduplicator.py
│       │   ├── flame_check.py
│       │   ├── search_twitterapi.py
│       │   ├── search_perplexity.py
│       │   └── utils.py
│       ├── prompts/
│       │   ├── post_generation.md
│       │   └── quote_generation.md
│       └── rules/
│           └── flame_rules.yaml
└── examples/
    └── lean-canvas-sample.md
```

インストール後のユーザープロジェクト側:

```
<user-project>/
├── lean-canvas.md                  # 必須 (ユーザー作成)
├── .env                            # install.sh で作成
├── .gitignore                      # .x-history/ と .env を追加
├── .claude/
│   └── skills/
│       ├── x-post/
│       │   └── SKILL.md
│       ├── x-quote/
│       │   └── SKILL.md
│       └── _x-shared/              # skills/_x-shared 配下をそのまま配置
│           ├── requirements.txt
│           ├── scripts/
│           ├── prompts/
│           └── rules/
└── .x-history/                     # 初回実行時に自動生成
    ├── posts.jsonl
    ├── quotes.jsonl
    └── topics.json
```

---

## 5. ファイル仕様: ルート

### 5.1 README.md

以下のセクションを含めること:

- プロジェクト名と概要 (1段落)
- 前提条件
  - Claude Code がインストール済み
  - Python 3.10+
  - TwitterAPI.io と Perplexity のアカウント
- ワンコマンドインストール
  ```bash
  cd /path/to/your-project
  curl -fsSL https://raw.githubusercontent.com/unkrypt/unkrypt-x-ops/main/install.sh | bash
  ```
- 手動インストール手順
- セットアップ後にやること
  - `.env` に API キーを入力
  - `lean-canvas.md` をプロジェクトルートに配置
- 使い方
  - `/x-post` の実行例
  - `/x-quote` の実行例
- コスト目安
- トラブルシューティングへのリンク
- ライセンス (MIT)

### 5.2 LICENSE

MIT ライセンス。著作権者は `unkrypt`。

### 5.3 .env.example

```bash
# TwitterAPI.io (https://twitterapi.io/dashboard)
TWITTERAPI_IO_KEY=

# Perplexity Sonar API (https://www.perplexity.ai/settings/api)
PERPLEXITY_API_KEY=

# オプション: 履歴管理の設定
X_HISTORY_RETENTION_DAYS=30          # 重複チェックの期間
X_HISTORY_SIMHASH_THRESHOLD=4        # 本文類似度(ハミング距離)の閾値
```

### 5.4 .gitignore

```
.env
.x-history/
__pycache__/
*.pyc
.venv/
```

### 5.5 install.sh

**要件:**

- bash スクリプトとして実行可能 (`#!/usr/bin/env bash`)
- 冒頭で `set -euo pipefail`
- 以下を順に行う:

1. カレントディレクトリが Git リポジトリかどうかを確認 (警告のみ、停止はしない)
2. `.claude/skills/` ディレクトリを作成
3. リポジトリ内容を `.claude/skills/` 配下にコピー
   - `skills/x-post/` → `.claude/skills/x-post/`
   - `skills/x-quote/` → `.claude/skills/x-quote/`
   - `skills/_x-shared/` → `.claude/skills/_x-shared/`
4. `.env.example` を `.env` にコピー (既存の `.env` がある場合は上書きしない)
5. `.gitignore` に以下を追記 (既存の行は重複しない)
   - `.env`
   - `.x-history/`
6. Python 依存関係をインストール
   - `pip install -r .claude/skills/_x-shared/requirements.txt --user`
   - 失敗した場合は `python3 -m pip` を試す
7. `lean-canvas.md` の存在確認
   - なければ `.claude/skills/_x-shared/examples/lean-canvas-sample.md` をコピーする旨を案内 (実コピーはしない)
8. 完了メッセージで次のステップを案内
   - `.env` の編集
   - `lean-canvas.md` の作成
   - Claude Code で `/x-post` または `/x-quote` を実行

**インストール方法の選択肢:**

- デフォルトはプロジェクトローカル (`.claude/skills/`)
- `--global` オプションで `~/.claude/skills/` に配置
- `--uninstall` オプションでアンインストール

**リモート実行対応:**

`curl | bash` で実行されることを想定するため、スクリプト内で以下の方法でファイルを取得:

- `git clone --depth=1 https://github.com/unkrypt/unkrypt-x-ops.git /tmp/unkrypt-x-ops-$$`
- インストール完了後にクローンディレクトリを削除

### 5.6 .gitignore (リポジトリ側)

```
.env
__pycache__/
*.pyc
.venv/
.x-history/
node_modules/
.DS_Store
```

---

## 6. ファイル仕様: skills/x-post/SKILL.md

### 6.1 フロントマター

```yaml
---
name: x-post
description: X (旧Twitter) ビジネスアカウント用の新規ポスト原稿を生成する。カレントディレクトリの lean-canvas.md を参照し、Perplexity Sonar で関連ニュース・論文を調査した上で、日本語280字以内のポスト原稿を作成する。過去の投稿履歴 (.x-history/posts.jsonl) と重複しないトピック・切り口を自動選択し、炎上チェックを通してから出力する。ユーザーが「ポスト」「ツイート」「X投稿」「Twitter投稿」「x-post」「/x-post」「SaaSのPR」「unkryptのX運用」と言ったら必ずこのスキルをトリガーすること。投稿自体は行わず、コピー可能な形で原稿を表示するだけ。
---
```

### 6.2 本文

SKILL.md の本文には以下を含めること:

- スキルの目的(1段落)
- 前提条件
  - カレントディレクトリに `lean-canvas.md` が存在すること
  - `.env` に `PERPLEXITY_API_KEY` が設定されていること
  - `.claude/skills/_x-shared/` が存在すること
- 実行フロー (セクション 3.1 の内容)
- 使用するスクリプト
  - `bash` ツールで `python .claude/skills/_x-shared/scripts/lean_canvas_loader.py --path ./lean-canvas.md` 等を実行
- 各ステップの詳細指示 (Claude Code が誤解しないよう具体的に書く)
- 出力フォーマット
  - 生成した原稿を ```` ``` ```` で囲んで表示
  - トピック・参考URL・炎上判定結果をメタ情報として添える
- エラーハンドリング
  - lean-canvas.md がない場合のメッセージ
  - API キーがない場合のメッセージ
  - API 障害時のフォールバック

### 6.3 重要な指示

SKILL.md 本文の最初の方に以下を明示:

- このスキルは**ポストを投稿しない**。生成のみ
- 履歴書き込みは**ユーザー許可なし**で自動実行する
- 炎上チェックが **BLOCK** の場合は原稿を破棄して再生成
- 炎上チェックが **WARN** の場合は警告を表示しつつユーザーに最終判断を委ねる

---

## 7. ファイル仕様: skills/x-quote/SKILL.md

### 7.1 フロントマター

```yaml
---
name: x-quote
description: X (旧Twitter) で他人のツイートを引用する引用ツイート (QT) の原稿を生成する。カレントディレクトリの lean-canvas.md のキートピックで TwitterAPI.io から直近のX投稿を検索し、関連性・エンゲージメント・炎上リスクで候補をスコアリング、ユーザーが選んだ1件に対して日本語200字以内のコメント原稿を作成する。過去の引用履歴 (.x-history/quotes.jsonl) と重複しないよう自動チェックする。ユーザーが「引用ツイート」「QT」「x-quote」「/x-quote」「引用RT」「他人のツイートに乗っかる」と言ったら必ずこのスキルをトリガーすること。投稿自体は行わず、引用元URLとコメント原稿を表示するだけ。
---
```

### 7.2 本文

SKILL.md 本文には以下を含めること:

- スキル目的
- 前提条件
  - `.env` に `TWITTERAPI_IO_KEY` と `PERPLEXITY_API_KEY`
- 実行フロー (セクション 3.2 の内容)
- 候補選択時のユーザー対話フォーマット
  - 「以下の3候補から選んでください: 1. ... 2. ... 3. ...」
- スコアリング基準の明示 (セクション 9.4 のスコアリングロジック参照)
- 出力フォーマット
- エラーハンドリング

---

## 8. ファイル仕様: skills/_x-shared/requirements.txt

```
simhash>=2.1.2
pyyaml>=6.0
requests>=2.31.0
python-dotenv>=1.0.0
openai>=1.40.0
```

注:

- `openai` は Perplexity Sonar の OpenAI 互換 SDK 利用のため
- TwitterAPI.io は `requests` で直接叩く (専用 SDK なし)
- 軽量に保つため重い ML ライブラリは使わない (simhash のみ)

---

## 9. ファイル仕様: skills/_x-shared/scripts/

### 9.1 lean_canvas_loader.py

**責務:** lean-canvas.md を読み込み、構造化データに変換する。

**関数:**

```python
def load_canvas(path: str = "./lean-canvas.md") -> dict:
    """
    Returns:
        {
            "raw_text": str,
            "sections": {
                "problem": [str, ...],
                "customer_segments": [str, ...],
                "uvp": [str, ...],
                "solution": [str, ...],
                "channels": [str, ...],
                "revenue_streams": [str, ...],
                "cost_structure": [str, ...],
                "key_metrics": [str, ...],
                "unfair_advantage": [str, ...],
            },
            "topic_tags": [str, ...],     # 正規化されたトピック一覧
            "content_hash": str,          # キャンバス内容のSHA1
        }
    """
```

**パース仕様:**

- `## N. SECTION_NAME` の見出しでセクション分割
- 各セクション内の `####` と `-` 箇条書きを抽出
- `topic_tags` は UVP、PROBLEM、UNFAIR ADVANTAGE から主要キーワードを抽出

**CLI:**

```bash
python lean_canvas_loader.py --path ./lean-canvas.md [--json]
```

`--json` を付けると JSON 出力、付けない場合は人間向けサマリ。

### 9.2 history.py

**責務:** `.x-history/*.jsonl` を管理する。

**関数:**

```python
def append(kind: str, entry: dict, history_dir: str = "./.x-history") -> None:
    """
    kind: "post" or "quote"
    entry: エントリの辞書 (スキーマは下記)
    """

def load(kind: str, since_days: int = 30, history_dir: str = "./.x-history") -> list[dict]:
    """
    直近 since_days 日のエントリを返す。
    ファイルが存在しなければ空リストを返す。
    """

def stats(kind: str, history_dir: str = "./.x-history") -> dict:
    """
    {
        "total": int,
        "last_30d": int,
        "topic_coverage": { topic: count },
        "accounts_quoted_last_30d": [str, ...],  # quote のみ
    }
    """
```

**posts.jsonl スキーマ:**

```json
{
  "id": "post_20260420_100000",
  "created_at": "2026-04-20T10:00:00+09:00",
  "topic_tags": ["手書きOCR", "2025年問題"],
  "angle": "ベテラン退職による技術継承課題",
  "sources": [
    {"url": "https://...", "title": "ものづくり白書2025"}
  ],
  "text": "投稿本文...",
  "char_count": 245,
  "simhash": "a7b3c9d2...",
  "flame_score": "SAFE",
  "flame_warnings": [],
  "canvas_hash": "キャンバスのハッシュ"
}
```

**quotes.jsonl スキーマ:**

```json
{
  "id": "quote_20260420_100000",
  "created_at": "2026-04-20T10:00:00+09:00",
  "topic_tags": ["製造業DX"],
  "quoted_tweet": {
    "url": "https://x.com/user/status/123",
    "tweet_id": "123",
    "author_handle": "user",
    "author_id": "u_abc",
    "text": "引用元の本文",
    "posted_at": "2026-04-19T15:00:00+09:00",
    "like_count": 150,
    "repost_count": 20
  },
  "comment_text": "コメント本文",
  "comment_char_count": 180,
  "simhash": "...",
  "flame_score": "SAFE",
  "flame_warnings": [],
  "canvas_hash": "..."
}
```

**CLI:**

```bash
python history.py append --kind post --data-json '{...}'
python history.py load --kind post --since-days 30
python history.py stats --kind quote
```

### 9.3 deduplicator.py

**責務:** 新規生成物が過去の履歴と重複していないか判定する。

**関数:**

```python
def compute_simhash(text: str) -> int:
    """Simhash 値を返す"""

def hamming_distance(a: int, b: int) -> int:
    """Simhash 間のハミング距離"""

def is_duplicate_post(new_entry: dict, history: list[dict], threshold: int = 4) -> tuple[bool, str]:
    """
    本文の simhash ハミング距離が threshold 以下なら重複判定。
    トピックタグの完全一致も重複扱い。
    Returns: (is_duplicate, reason)
    """

def is_duplicate_quote(new_entry: dict, history: list[dict]) -> tuple[bool, str]:
    """
    引用ツイート特有のチェック:
      - 同一 tweet_id は必ず重複
      - 同一 author_handle を直近30日で2回以上は重複扱い
      - コメント本文の simhash 類似も重複扱い
    Returns: (is_duplicate, reason)
    """

def suggest_underused_topics(canvas_topics: list[str], history: list[dict]) -> list[str]:
    """
    履歴で使用頻度が低いトピックを優先して返す。
    """
```

### 9.4 flame_check.py

**責務:** 生成した原稿を `rules/flame_rules.yaml` のルールで判定する。

**関数:**

```python
def check(text: str, context: dict = None) -> dict:
    """
    Returns:
        {
            "score": "BLOCK" | "WARN" | "SAFE",
            "warnings": [
                {"rule_id": str, "message": str, "severity": "BLOCK"|"WARN"}
            ]
        }
    """
```

**判定ロジック:**

1. `flame_rules.yaml` を読み込み、各ルールを正規表現または部分文字列マッチで検査
2. BLOCK に該当するルールが1つでもあれば `score="BLOCK"`
3. BLOCK はないが WARN に該当するルールがあれば `score="WARN"`
4. どれにも該当しなければ `score="SAFE"`

**CLI:**

```bash
python flame_check.py --text "判定したい本文"
```

### 9.5 search_twitterapi.py

**責務:** TwitterAPI.io の Advanced Search エンドポイントを叩いて、キャンバスに関連するX投稿を取得する。

**関数:**

```python
def search_tweets(
    query: str,
    max_results: int = 30,
    language: str = "ja",
    hours_back: int = 72,
    min_likes: int = 5
) -> list[dict]:
    """
    TwitterAPI.io 経由で検索。
    Returns: [
        {
            "tweet_id": "...",
            "url": "https://x.com/user/status/...",
            "author_handle": "...",
            "author_id": "...",
            "text": "...",
            "posted_at": "...",
            "like_count": 123,
            "repost_count": 45,
            "reply_count": 12
        }, ...
    ]
    """

def multi_search(queries: list[str], **kwargs) -> list[dict]:
    """
    複数クエリで検索し、重複を除いて返す。
    """
```

**エンドポイント:**

- TwitterAPI.io の公式ドキュメント https://docs.twitterapi.io を参照すること
- 推奨: Advanced Search エンドポイント (`GET /twitter/tweet/advanced_search`)
- 認証: `X-API-Key` ヘッダー
- レート制限に注意 (1000+ req/sec と言われているが念のため間隔を空ける)

**エラーハンドリング:**

- 401/403 ⇒ API キー不正。ユーザーに `.env` 確認を促す
- 429 ⇒ レート制限。3秒待って1回リトライ
- 500+ ⇒ 1回リトライして失敗したらエラー
- ネットワークエラー ⇒ `requests.exceptions` を捕捉して分かりやすいメッセージを出す

### 9.6 search_perplexity.py

**責務:** Perplexity Sonar Pro でニュース・論文を調査する。

**関数:**

```python
def research(
    query: str,
    domain_filter: list[str] | None = None,
    recency: str = "month"
) -> dict:
    """
    Returns:
        {
            "answer": "...",
            "citations": [
                {"url": "...", "title": "...", "snippet": "...", "date": "..."}
            ],
            "usage": {"total_tokens": 123}
        }
    """

def research_multi(queries: list[str], **kwargs) -> list[dict]:
    """複数クエリを順次実行"""
```

**SDK 利用:**

- `from openai import OpenAI` を `base_url="https://api.perplexity.ai"` で初期化
- モデル: `sonar-pro`
- `extra_body` で `search_domain_filter` や `search_recency_filter` を指定
- 最新の API 仕様は https://docs.perplexity.ai を参照

**推奨デフォルト:**

- `search_recency_filter="month"` (直近1ヶ月)
- ドメインフィルタの例 (日本の製造業調査向け):
  - `["meti.go.jp", "monoist.itmedia.co.jp", "nikkei.com", "prtimes.jp"]`

### 9.7 utils.py

**責務:** 共通ユーティリティ。

- `.env` の読み込み (`python-dotenv`)
- タイムゾーン対応の `now_jst()`
- ID 生成 (`post_YYYYMMDD_HHMMSS` 形式)
- 履歴ディレクトリの初期化 (`ensure_history_dir()`)

---

## 10. ファイル仕様: skills/_x-shared/prompts/

### 10.1 post_generation.md

ポスト生成時に SKILL.md から読み込んで使うプロンプトテンプレート。

内容要件:

- ペルソナ: unkrypt のビジネスアカウント、製造業DX領域、技術と経営の両方に通じたトーン
- 制約:
  - 日本語、280字以内 (絵文字・URL・ハッシュタグ含む)
  - 1ポストに最大1つのURL
  - ハッシュタグは最大2個、製造業DX領域のもの
  - 絵文字は最大2個、業務的文脈で
  - 自社 SaaS の直接宣伝は3ポストに1回程度、他は業界知見・学び・考察
  - 競合の実名批判は禁止
- 与えられるコンテキスト:
  - lean-canvas.md の主要セクション
  - Perplexity Sonar のリサーチ結果
  - 過去30日の投稿履歴サマリ
- 出力フォーマット:
  - ポスト本文のみ (余計な説明なし)
  - 末尾に `---META---` 区切り行を入れて、`topic_tags`, `angle`, `sources` を YAML で続ける

### 10.2 quote_generation.md

引用ツイート生成用プロンプト。

内容要件:

- ペルソナ: 同上
- 制約:
  - 日本語、200字以内
  - 引用元ツイートに対して価値を付加する (単なる同意や絵文字だけの引用はNG)
  - 自社 SaaS への誘導は強引でなく、自然な流れで
  - 引用元アカウントを貶める表現は禁止
- 与えられるコンテキスト:
  - 引用元ツイート本文とメタデータ
  - lean-canvas.md の関連セクション
  - Perplexity Sonar のリサーチ結果
- 出力フォーマット:
  - コメント本文のみ
  - 末尾に `---META---` 区切り行 + YAML メタ

---

## 11. ファイル仕様: skills/_x-shared/rules/flame_rules.yaml

### 11.1 構造

```yaml
version: 1
severity_levels: [SAFE, WARN, BLOCK]

rules:
  - id: competitor_naming_negative
    severity: BLOCK
    description: 競合製品・サービスの実名を伴う否定的表現
    patterns:
      - type: regex
        pattern: "(DocuWorks|楽々Document|DX Suite|Tegaki|DNP|Oracle).{0,20}(使えない|ダメ|劣る|古い|不便)"
    examples_hit:
      - "DocuWorksは使えない"
    examples_safe:
      - "DocuWorksからの移行事例"

  - id: discrimination
    severity: BLOCK
    description: 差別的・侮辱的表現
    patterns:
      - type: keyword
        keywords: [差別用語リスト...]   # 実装時に適切なリストを作る

  - id: political_religious
    severity: BLOCK
    description: 政治・宗教に関する強い主張
    patterns:
      - type: keyword
        keywords: [自民党, 立憲民主, 共産党, 統一教会, ...]

  - id: customer_names
    severity: BLOCK
    description: PoC顧客・取引先の実名を含む可能性
    patterns:
      - type: regex
        pattern: "(株式会社|有限会社|㈱).{1,10}様"

  - id: medical_legal_unverified
    severity: BLOCK
    description: 根拠不明の医療・法律的主張
    patterns:
      - type: keyword
        keywords: [診断できる, 治癒, 法的拘束力, 合法化する]

  - id: absolute_claims
    severity: WARN
    description: 強すぎる断定表現
    patterns:
      - type: regex
        pattern: "(必ず|絶対に|100%|唯一|業界最高|No\\.?1)"

  - id: stats_without_source
    severity: WARN
    description: 数字を引用しているが出典URLがない
    check: custom_function   # scripts で実装
    custom_function: check_stats_have_source

  - id: vague_exaggeration
    severity: WARN
    description: 誇張気味の表現
    patterns:
      - type: keyword
        keywords: [革命的, 画期的, 世界初, 前代未聞]
```

### 11.2 実装上の注意

- `flame_check.py` は `check_stats_have_source` 等の custom_function を呼び出せるようにする
- 数字判定は「数字が含まれるが URL が文字列中に無い」で検出
- BLOCK のキーワードリストは実装時に慎重に作る。多すぎると正当な表現まで弾く

---

## 12. 受け入れ基準

### 12.1 機能要件

- [ ] `curl -fsSL .../install.sh | bash` で `.claude/skills/` 配下にスキル3点が配置される
- [ ] `.env` が自動作成され、`.gitignore` に追記される
- [ ] Python 依存関係が自動インストールされる
- [ ] Claude Code で `/x-post` が発火する
- [ ] Claude Code で `/x-quote` が発火する
- [ ] `lean-canvas.md` がないときに分かりやすいエラーが出る
- [ ] API キーがないときに分かりやすいエラーが出る
- [ ] ポスト生成で Perplexity Sonar が実際に呼ばれる
- [ ] 引用生成で TwitterAPI.io が実際に呼ばれる
- [ ] 炎上チェックが実行され、BLOCK/WARN/SAFE が返る
- [ ] 履歴が `.x-history/*.jsonl` に自動追記される (ユーザー確認なし)
- [ ] 同じトピックを2回連続で提案しない
- [ ] 出力は投稿せず、コピー可能な形で表示される

### 12.2 非機能要件

- [ ] 1回の /x-post 実行でのコストが $0.05 以下
- [ ] 1回の /x-quote 実行でのコストが $0.05 以下
- [ ] スクリプトがタイムアウトせず60秒以内に完了
- [ ] API 障害時にクラッシュせず、ユーザーに原因を伝える
- [ ] README.md のインストール手順通りでエラーなく導入できる

### 12.3 コード品質

- [ ] Python コードは Python 3.10 以上で動く
- [ ] 型ヒントを付ける
- [ ] 例外は具体的に捕捉する (bare `except:` 禁止)
- [ ] シークレットをログに出さない
- [ ] 日本語コメント OK、ただし関数の docstring は日本語可

---

## 13. 実装順序の推奨

以下の順で進めると詰まりにくい:

1. ディレクトリ構造を作る (セクション 4)
2. `requirements.txt` と `utils.py` を作る
3. `lean_canvas_loader.py` を作って、添付の lean-canvas.md で動作確認
4. `history.py` と `deduplicator.py` を作って、ダミーデータで動作確認
5. `flame_rules.yaml` と `flame_check.py` を作って、いくつかのテスト文で動作確認
6. `search_perplexity.py` を作って、小さなクエリで動作確認
7. `search_twitterapi.py` を作って、小さなクエリで動作確認
8. `prompts/post_generation.md` と `quote_generation.md` を作る
9. `skills/x-post/SKILL.md` を書き、手動で /x-post のフローを通す
10. `skills/x-quote/SKILL.md` を書き、手動で /x-quote のフローを通す
11. `install.sh` を作る
12. `README.md` と `docs/` を書く
13. GitHub リポジトリに push
14. 別ディレクトリで `curl | bash` を実行してインストールテスト

---

## 14. 将来の拡張 (今回はやらない)

以下は今回のスコープ外。README に Future Work として記載のみ。

- X API での自動投稿
- スケジュール投稿
- Grok API への切り替えオプション (クライアント抽象化だけは入れておく)
- X Analytics 連携による効果測定
- 複数キャンバス対応 (lean-canvas-a.md, lean-canvas-b.md 等)
- 多言語対応 (英語ポスト)

---

## 15. 参考情報

### 15.1 API ドキュメント

- TwitterAPI.io: https://docs.twitterapi.io
- Perplexity Sonar: https://docs.perplexity.ai
- Claude Code Skills: https://docs.claude.com (Skills ドキュメント)

### 15.2 注意事項

- TwitterAPI.io は X 公式ではない第三者サービス。利用規約を確認すること
- X のプラットフォームポリシーに違反する使い方をしないこと (スパム、大量自動投稿 等)
- lean-canvas.md に顧客の実名等の機密が含まれる場合、API 経由で外部送信されないよう注意 (本実装ではキャンバスの全文を API に送らず、トピックキーワードのみを送る設計)
- 生成されたポストは必ず人間の目でレビューしてから投稿する

---

_このドキュメントは unkrypt-x-ops の実装に必要な情報をまとめた仕様書です。Claude Code でこのファイルを参照して実装を進めてください。不明点はこのファイルを更新するか、実装者に確認してください。_

_Last Updated: 2026-04-20_
