# アーキテクチャ

## 全体像

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Claude Code セッション                        │
│                                                                      │
│   /x-post / /x-quote                                                 │
│      │                                                               │
│      ▼                                                               │
│   SKILL.md (フロー定義)                                               │
│      │  (bash ツールで Python スクリプト呼び出し)                       │
│      ▼                                                               │
└──────┼───────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    .claude/skills/_x-shared/scripts/                 │
│                                                                      │
│   lean_canvas_loader.py  ← ./lean-canvas.md                          │
│   history.py             ↔ ./.x-history/*.jsonl                      │
│   deduplicator.py        (simhash 重複判定)                          │
│   flame_check.py         ← rules/flame_rules.yaml                    │
│   search_tavily.py       ──▶ Tavily Search API                       │
│   search_twitterapi.py   ──▶ TwitterAPI.io                           │
│   utils.py               (共通: env, 時刻, ID)                       │
└──────────────────────────────────────────────────────────────────────┘
```

## 責務分担

### Claude Code (セッション内の Claude 自身)

- SKILL.md のフローに沿って、スクリプトを順次呼び出す
- **原稿生成・スコアリングの判断** は Claude 自身が担当(外部 LLM は呼ばない)
- プロンプトテンプレート (`prompts/*.md`) を参照
- ユーザーとの対話(採用番号の確認)を担当

### Python スクリプト (`_x-shared/scripts/`)

- ファイル I/O、API 呼び出し、正規表現チェック等の **決定的な処理**
- 各スクリプトは **CLI としても呼べる**(テスト容易)
- 例外は具体的に捕捉、シークレットはログに出さない

### 設定・ルール (`_x-shared/rules/`, `prompts/`)

- 編集だけで挙動を調整できる宣言的な資産
- コード変更なしで運用ポリシーを変えられる

## データフロー: /x-post

```
lean-canvas.md ──┐
                 ▼
         lean_canvas_loader.py ── { sections, topic_tags }
                                       │
                                       ▼
                       history.py load  ◀─ .x-history/posts.jsonl
                                       │
                       deduplicator.py suggest-topics
                                       │
                                       ▼
                      < 選ばれたトピック >
                                       │
                                       ▼
                         search_tavily.py ── { answer, citations }
                                       │
                                       ▼
              Claude Code が 5 バリエーション生成
                                       │
                                       ▼
                  for each post:
                    flame_check.py  → SAFE/WARN/BLOCK
                    deduplicator.py → 重複判定
                                       │
                                       ▼
              5 候補をユーザーに提示 → 採用番号受領
                                       │
                                       ▼
                 採用分だけ history.py append
```

## データフロー: /x-quote

```
lean-canvas.md ──────┐
.x-history/quotes ──▶│
                     ▼
             topic_tags + accounts_last_30d
                     │
                     ▼
        search_twitterapi.py (3 クエリ × 30 件)
                     │
                     ▼
              候補 ~60〜90 件
                     │
                     ▼
       search_tavily.py (背景補強 1 回)
                     │
                     ▼
    Claude Code がスコアリング → Top 5 選定
                     │
                     ▼
      5 候補それぞれにコメント生成 (Claude)
                     │
                     ▼
        flame_check + deduplicator
                     │
                     ▼
            ユーザー提示 → 採用番号
                     │
                     ▼
            history.py append
```

## 設計上のトレードオフ

### なぜ LLM 呼び出しを Python 側でやらないか

- Claude Code セッション内の Claude を使う方が **追加 LLM 費用ゼロ**
- プロンプトを `prompts/*.md` に置けば、Claude 自身が読み込んで文脈に応じて調整できる
- 原稿の品質はモデルの能力に依存するので、Claude の最新版をそのまま使うのが合理的

### なぜ Web 検索に Tavily を選んだか

- **無料枠(月 1,000 リクエスト)** があり、本ツールの月 12 回程度の利用規模では **実質無料**
- `include_domains` / `exclude_domains` でドメインフィルタ可能
- `time_range` で鮮度制御(day / week / month / year)
- `include_answer=True` で LLM 要約 answer も取得できる(Perplexity 相当の挙動)
- `search_depth="advanced"` で高品質な結果を取得

### なぜ X 内検索は TwitterAPI.io なのか

- 公式 X API は月額高額($100〜)で、個人事業主にはオーバースペック
- TwitterAPI.io は $0.15/1,000 ツイートの従量課金で、月数百ツイート取得でも数十円レベル
- 公式ではないため規約変更リスクはあるが、クライアントは抽象化しやすく書いてある

### 投稿機能を意図的に外す理由

- X 公式 API は有料で規約も厳しく、自動投稿は規約違反リスクが大きい
- 人間レビューを挟む運用の方が、炎上・誤情報リスクを大幅に下げられる

## 拡張ポイント

| ポイント | 現状 | 拡張方法 |
|---|---|---|
| Web 検索エンジン | Tavily 固定 | `search_tavily.py` と同じインターフェースで `search_websearch.py` や `search_perplexity.py` を追加して SKILL.md の呼び出しを切り替え |
| X 検索エンジン | TwitterAPI.io 固定 | `search_twitterapi.py` を抽象化して切り替え可能に |
| 炎上ルール | `flame_rules.yaml` | YAML 編集のみで追加・変更可能 |
| プロンプト | `prompts/*.md` | テキスト編集でトーン変更 |
| 履歴管理 | JSONL 追記専用 | SQLite に切り替える場合は `history.py` だけ差し替え |

## セキュリティ考慮

- `.env` は `.gitignore` 済み
- スクリプトはシークレットをログに出さない(`utils.mask_secret` を使用)
- API レスポンスのエラー本文は抜粋(200 文字)のみを表示
- lean-canvas.md を API に送らず、トピックキーワードのみを送る設計(機密情報流出の最小化)
