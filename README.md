# x-post-gen

X (旧 Twitter) のビジネスアカウント運用を支援する **Claude Code スラッシュコマンド集**。
lean-canvas.md を唯一の真実の源 (SoT) として、キャンバスに沿った **ポスト 5 候補 / 引用ツイート 5 候補** を 1 コマンドで自動生成します。
実際の投稿はユーザー側で手動で行います(投稿機能は持ちません)。

---

## 機能

| コマンド | 用途 | 生成数 |
|---|---|---|
| `/x-post` | 新規ポスト原稿を 5 つの異なる切り口で生成 | 5 |
| `/x-quote` | X 上の関連ツイートを検索し、Top 5 に対するコメント原稿を生成 | 5 |

共通のコア機能:
- **lean-canvas.md 参照** — キャンバスのトピックから発信軸を自動抽出
- **Web リサーチ** — Tavily Search API で一次情報・ニュース・論文を調査し出典 URL を付与
- **X 内検索** — TwitterAPI.io で引用候補ツイートを取得
- **炎上チェック** — `flame_rules.yaml` のルールで BLOCK/WARN/SAFE を自動判定
- **履歴自動管理** — `.x-history/*.jsonl` に自動追記(simhash で重複検出)
- **5 候補提示 → ユーザーが採用番号を選ぶ → 採用分だけ履歴追記**

---

## 前提条件

- [Claude Code](https://docs.claude.com) がインストール済み
- Python 3.10+
- [TwitterAPI.io](https://twitterapi.io/dashboard) アカウント (引用ツイート機能で使用)
- [Tavily](https://app.tavily.com/home) アカウント (Web 調査で使用。月 1,000 リクエストまで無料枠あり)

---

## ワンコマンドインストール

プロジェクトのルートディレクトリで実行:

```bash
cd /path/to/your-project
curl -fsSL https://raw.githubusercontent.com/mycee0001/x-post-gen/main/install.sh | bash
```

これで以下が自動セットアップされます:
- `.claude/skills/x-post/` / `x-quote/` / `_x-shared/` を配置
- `.env` を `.env.example` から作成(既存は上書きしない)
- `.gitignore` に `.env` と `.x-history/` を追記
- Python 依存関係を `pip --user` でインストール
- `lean-canvas.md` の有無をチェック

### インストールオプション

```bash
# グローバルインストール (~/.claude/skills/ に配置)
curl -fsSL https://raw.githubusercontent.com/mycee0001/x-post-gen/main/install.sh | bash -s -- --global

# 別ブランチから
curl -fsSL https://raw.githubusercontent.com/mycee0001/x-post-gen/main/install.sh | bash -s -- --branch dev

# アンインストール
curl -fsSL https://raw.githubusercontent.com/mycee0001/x-post-gen/main/install.sh | bash -s -- --uninstall
```

### 手動インストール

```bash
git clone https://github.com/mycee0001/x-post-gen.git
cd x-post-gen
bash install.sh
```

---

## セットアップ後にやること

### 1) `.env` に API キーを入力

ワンコマンドインストール後、プロジェクトルートに `.env` が作成されています。
以下 2 つのキーを設定してください:

```bash
# TwitterAPI.io  https://twitterapi.io/dashboard
TWITTERAPI_IO_KEY=pk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Tavily Search API  https://app.tavily.com/home
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

オプション設定(デフォルトで動きます):

| 変数名 | 既定値 | 説明 |
|---|---|---|
| `X_HISTORY_RETENTION_DAYS` | `30` | 重複チェックの対象期間(日) |
| `X_HISTORY_SIMHASH_THRESHOLD` | `4` | 本文類似度(ハミング距離)の重複判定閾値。小さいほど厳しい |
| `X_POST_VARIANTS` | `5` | `/x-post` で生成するポスト数 |
| `X_QUOTE_VARIANTS` | `5` | `/x-quote` で生成する候補数 |

### 2) `lean-canvas.md` をプロジェクトルートに配置

```bash
# サンプルから始める
cp .claude/skills/_x-shared/examples/lean-canvas-sample.md ./lean-canvas.md

# 自社の情報に書き換える
$EDITOR ./lean-canvas.md
```

推奨構成:
- `## N. PROBLEM` / `## N. UVP` / `## N. SOLUTION` / `## N. UNFAIR ADVANTAGE` のセクション分け
- 各セクション内は箇条書き(`-`)
- ハッシュタグ候補を「主要トピックタグ」セクションに羅列

サンプル: [examples/lean-canvas-sample.md](examples/lean-canvas-sample.md)

### 3) Claude Code で実行

```
/x-post     # 新規ポスト 5 候補
/x-quote    # 引用ツイート 5 候補
```

---

## 使い方

### `/x-post` — 新規ポスト生成

```
あなた: /x-post
```

Claude Code が以下を実行します:
1. `lean-canvas.md` を読み込み、トピックタグを抽出
2. 履歴 (`.x-history/posts.jsonl`) から低頻度トピックを選定
3. Tavily Search で関連ニュース・論文を 1 回調査 (`--mfg-preset` でドメインフィルタ、`search_depth=advanced`)
4. 5 つの異なる切り口で 280 字以内のポスト案を生成
   - 一次情報ベース / 現場視点 / 経営視点 / 技術トレンド / 示唆・問い
5. 各ポストに炎上チェック & 重複チェック
6. 5 候補を番号付きでコピー可能なコードブロックで表示
7. ユーザーが採用番号を指定(`1,3` / `all` / `none`)
8. 採用分のみ `.x-history/posts.jsonl` に追記

### `/x-quote` — 引用ツイート生成

```
あなた: /x-quote
```

1. `lean-canvas.md` 読み込み
2. TwitterAPI.io で直近 72 時間、日本語、min_likes 5 以上の関連ツイートを最大 30 件取得
3. Tavily で背景情報を補強
4. 関連性 / エンゲージメント / 炎上リスク / 重複ペナルティでスコアリング
5. Top 5 候補それぞれに 200 字以内のコメント原稿を生成
6. 各コメントに炎上 & 重複チェック
7. 引用元 URL + コメントを 5 件表示
8. ユーザーが採用番号を指定
9. 採用分のみ `.x-history/quotes.jsonl` に追記

---

## 月額コスト目安

| API | 想定利用 | コスト/月 |
|---|---|---|
| TwitterAPI.io | `/x-quote` 月 6 回 × 検索 3 クエリ × 30 件 ≒ 540 ツイート | 約 $0.08 |
| Tavily (Advanced search) | `/x-post` 月 6 回 + `/x-quote` 月 6 回 = 12 リクエスト | **無料枠内 $0** |
| **合計** | | **約 $0.08 / 月** |

※ Tavily は月 1,000 リクエストまで無料枠(2026-04 時点)。
月 12 リクエスト程度なら課金は発生しません。
有料枠に入っても Advanced search 2 credits × $0.008/credit ≒ $0.2/月 想定。
実コストは内容・クエリ長・リトライ有無で変動します。

---

## ディレクトリ構成

```
<your-project>/
├── lean-canvas.md                  # ユーザー作成(必須)
├── .env                            # API キー(install.sh で生成、.gitignore 済み)
├── .claude/skills/
│   ├── x-post/SKILL.md             # /x-post の挙動定義
│   ├── x-quote/SKILL.md            # /x-quote の挙動定義
│   └── _x-shared/
│       ├── requirements.txt        # Python 依存
│       ├── scripts/                # ユーティリティスクリプト群
│       ├── prompts/                # 生成プロンプトテンプレート
│       ├── rules/                  # 炎上判定ルール
│       └── examples/               # サンプル
└── .x-history/                     # 初回実行時に自動生成
    ├── posts.jsonl
    └── quotes.jsonl
```

---

## よくある質問

### Q. 投稿も自動でやってくれますか?

**やりません。** 原稿生成までがスコープです。X 公式 API の利用規約・料金を踏まえ、
投稿は人間がレビューしてから手動で行う運用を前提としています。

### Q. Tavily ではなく Claude Code の WebSearch / Perplexity を使えますか?

現状は Tavily Search API 固定です。`include_domains` でのドメインフィルタ、
`time_range` での鮮度制御、`include_answer` での AI 要約、月 1,000 リクエスト無料枠など
本ツールの運用要件に最も適していると判断したためです。
将来的に切り替えオプション(WebSearch / Perplexity / Grok 等)を追加する可能性はあります。
`search_tavily.py` と同じインターフェースで別エンジンを実装することで差し替えられます。

### Q. 炎上チェックのルールはどこ?

`.claude/skills/_x-shared/rules/flame_rules.yaml` です。
競合実名批判、政治・宗教、差別表現、根拠不明の医療/法律断言などを `BLOCK` に、
強い断定や誇張表現を `WARN` に分類しています。自分の運用に合わせて編集可能です。

### Q. TwitterAPI.io は X 公式ですか?

**公式ではありません**。第三者サービスです。利用規約を確認の上でお使いください。
X 社のポリシー変更で突然使えなくなるリスクがあります。

### Q. 月のコマンド実行回数を増やすとコストはどうなりますか?

Tavily は月 1,000 リクエストまで無料(2026-04 時点)。超過分は Advanced search で 2 credits / 約 $0.016/req。
TwitterAPI.io は $0.15/1,000ツイート。
`/x-post` 1 回 ≒ 無料枠内($0)、`/x-quote` 1 回 ≒ $0.01〜$0.02 を目安に試算してください。

---

## ドキュメント

- [docs/architecture.md](docs/architecture.md) — アーキテクチャ詳細
- [docs/api-costs.md](docs/api-costs.md) — API コストの詳細試算
- [docs/troubleshooting.md](docs/troubleshooting.md) — トラブルシューティング

---

## 将来の拡張 (Future Work)

今回のスコープ外だが、クライアント抽象化はしてあります。

- X 公式 API での自動投稿
- スケジュール投稿
- Grok API / WebSearch / Perplexity への Tavily 代替
- X Analytics 連携による効果測定
- 複数キャンバス対応 (`lean-canvas-a.md`, `lean-canvas-b.md` 等)
- 英語ポスト / 多言語対応

---

## ライセンス

MIT License — 詳細は [LICENSE](LICENSE) を参照。

## 作者

unkrypt ([GitHub](https://github.com/mycee0001))
