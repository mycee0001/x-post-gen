---
name: x-quote
description: X (旧Twitter) で他人のツイートを引用する引用ツイート (QT) の原稿を、サービスごとに 5 件ずつ生成する。カレントディレクトリの lean-canvas-{service}.md (複数可) のキートピックで TwitterAPI.io から直近のX投稿を検索し、関連性・エンゲージメント・炎上リスクで候補をスコアリングしたのち「上位5件」をサービス別に生成する。過去の引用履歴 (.x-history/quotes.jsonl) と service 別に重複チェック。ユーザーが「引用ツイート」「QT」「x-quote」「/x-quote」「引用RT」「他人のツイートに乗っかる」と言ったら必ずこのスキルをトリガーすること。投稿自体は行わず、サービス別 5 候補をコピー可能な形で表示し、採用番号をユーザーに確認してから履歴に追記する。
---

# /x-quote スキル: X 引用ツイート生成 (サービスごと 5 候補)

## 重要な方針

- このスキルは **引用ツイートを投稿しない**。原稿を生成して表示するだけ
- 1 回の実行で **サービス数 × 5 = N 個の異なる候補ツイートそれぞれに対するコメント案** を提示
- 履歴への書き込みは **ユーザーが採用番号を選んだ後**(書き込み自体はユーザー許可不要)
- 炎上チェック **BLOCK** 除外、**WARN** 警告付き提示

## マルチキャンバスモード (重要)

カレントディレクトリの `lean-canvas-{service}.md` (複数可) を **個別のサービスとして扱い、コンテキストを厳密に分離する**。

- 各キャンバスごとに **独立に Step 1〜11 を完走**
- **コンテキスト混線禁止**: あるサービスの canvas / tuning / 履歴を別サービスの原稿生成に使わない
- 共有してよいのは `used_tweet_ids.jsonl` のみ

## 前提条件

- カレントディレクトリに `lean-canvas-{service}.md` が 1 つ以上
- `.env` に `TWITTERAPI_IO_KEY` と `TAVILY_API_KEY`
- `.claude/skills/_x-shared/` が配置済み

## 実行フロー

### Step 0: キャンバスを discover してサービス一覧を確定

```bash
python3 .claude/skills/_x-shared/scripts/lean_canvas_loader.py --discover --json
```

返り値配列の各要素は `{service, path, raw_text, sections, topic_tags, content_hash}`。
ユーザーに対象サービスを表示。

以降の Step 1〜11 は **サービスごとに独立に実行する**。

---

## 各サービスごとに以下を実行

### Step 1: そのサービスの canvas を保持

Step 0 の結果から service の canvas を取り出す。

### Step 1.5: tuning をサービス指定で読み込む

```bash
python3 .claude/skills/_x-shared/scripts/tuning.py load \
  --kind quote \
  --service <service> \
  --since-days 30 --limit 30
```

| category | 適用先 |
|---|---|
| `source` | Step 3 のクエリ構築・著者フィルタに反映 |
| `content` | Step 6 の原稿生成方針に反映 |
| `flame` | Step 7 の炎上チェック解釈に反映 |
| `other` | Claude が判断 |

### Step 2: 履歴をサービス指定で読み込み

```bash
python3 .claude/skills/_x-shared/scripts/history.py load \
  --kind quote \
  --service <service> \
  --since-days 30
python3 .claude/skills/_x-shared/scripts/history.py stats \
  --kind quote \
  --service <service>
python3 .claude/skills/_x-shared/scripts/used_tweets.py load
```

- `accounts_quoted_last_30d` (そのサービス内) を控えておく(同じアカウントを 2 回以上引用しない)
- `used_tweets.py load` の返り値はサービス横断で共有(除外 ID JSON として Step 3 へ)

### Step 3: TwitterAPI.io で X 内ツイートを検索

そのサービスの canvas の `topic_tags` からクエリを 2〜3 個。**他サービスの topic_tags を混ぜない**。

#### 引用元として適切なポストの定義

x-quote は引用元と同じ問題を抱える広いオーディエンスに刺さる発信を作るための踏み台として使う。

**狙う型:**
- 観察・原則・パターン提示
- データ・ニュース・調査・研究
- 問いかけ・呼びかけ
- 業界トレンド・社会論評
- 共感されやすい認知パターンの言語化

**避ける型:**
- 個人的なつぶやき・愚痴・日記
- ピンポイントな相談・SOS (x-reply の領分)
- 私生活・身体・精神状態の生々しい描写
- 身内ネタ・界隈内自虐
- 強い政治的・宗教的主張
- 炎上リスクの高いポスト

```bash
python3 .claude/skills/_x-shared/scripts/search_twitterapi.py \
  --query "<クエリ>" \
  --language ja \
  --hours-back 24 \
  --min-likes 20 \
  --min-author-followers 1000 \
  --max-replies 300 \
  --max-results 30 \
  --exclude-ids-json '<除外ID JSON>'
```

3 クエリで合計 ~90 件 → 重複除去後ひと山。

### Step 3.5: 第 1 段階フォールバック (サブカテゴリ 5 個)

ユニーク数 < 5 の場合のみ実行。サブカテゴリは canvas_hash 別にキャッシュされるためサービス自動分離。

```bash
python3 .claude/skills/_x-shared/scripts/subcategory_generator.py load \
  --canvas-hash <canvas.content_hash>
```

キャッシュ miss なら **当該サービスの canvas のみ** を入力に Claude が 5 個生成 (`subcategory_generation.md` 参照) → 保存。

各サブカテゴリで `--max-results 10` で追加検索 (リーチフィルタは Step 3 と同値)。
`origin: "subcategory"` フラグを付け、Step 5 で関連性 × 0.7。

### Step 3.6: 第 2 段階フォールバック (サブカテゴリ追加 5 個)

Step 3.5 後も < 5 件のみ実行。

### Step 3.7: 最終手段 — フィルタ緩和

Step 3.5 / 3.6 後も < 5 件のみ:

1. `--min-likes 20` → `10`
2. `--min-author-followers 1000` → `500`

### Step 4: Tavily Search で背景補強 (1 回のみ)

そのサービス文脈に沿った背景調査クエリで:

```bash
python3 .claude/skills/_x-shared/scripts/search_tavily.py \
  --query "<背景調査>" \
  --mfg-preset
```

### Step 5: 候補をスコアリング

| 項目 | 重み | 計算 |
|---|---|---|
| **関連性** | 0.20 | そのサービスの canvas との一致度。`origin == "subcategory"` は × 0.7 |
| **引用元適性** | 0.30 | 観察・データ・問いかけは加点、私的・SOS・身内ネタは減点 |
| **リーチ** | 0.30 | author_reach × engagement_velocity × conversation_activity |
| **炎上リスク(負)** | 0.10 | flame_check で BLOCK=-1, WARN=-0.5 |
| **重複ペナルティ(負)** | 0.10 | 同サービスで過去 30 日同アカウント引用済みなら -1 |

BLOCK 除外、引用元適性 < 0.4 も除外。Top 5。

#### 引用元適性 Score

| シグナル | 寄与 |
|---|---|
| 観察・原則・パターン提示 | +0.4 |
| データ・調査・研究 | +0.3 |
| 問いかけ・大喜利型 | +0.2 |
| 業界トレンド・社会論評 | +0.2 |
| 普遍的な認知描写 | +0.2 |
| 私生活実況・愚痴・日記 | -0.4 |
| 個人相談・SOS | -0.3 |
| 身内ネタ・自己定義スレッド | -0.4 |
| 私生活・精神状態の生々しい描写 | -0.5 |
| 政治的・宗教的主張 | -0.4 |

合算→0〜1 クリップ。0.4 未満は除外。

#### リーチ Score

```
reach = 0.45 × author_reach + 0.35 × engagement_velocity + 0.20 × conversation_activity
```

- author_reach: 1k〜50k がピーク 1.0
- engagement_velocity: `min(velocity / 30, 1.0)`
- conversation_activity: reply_count 5〜30 で 1.0、0 で 0.3、50+ で 0.5
- 認証済みは最後に +0.05

### Step 6: そのサービスの 5 候補にコメント原稿を生成

**必読:**
- `.claude/skills/_x-shared/prompts/quote_generation.md`
- `.claude/skills/_x-shared/prompts/japanese_writing_style.md`

**サービスを跨いだ流用禁止**: 当該サービスの canvas のみを文脈とする。

主要ルール:
- **完全同意スタンスの強制**
- **冒頭でカギカッコ引用パターンを使わない**
- **自己ポジショニング明示句を使わない**(専門性は言葉の精度・機序で滲ませる)
- **文体は丁寧体、一人称は「私」**
- **一行最大 50 字、理想 35 字**
- **中学生でもわかる単語**
- **使用禁止用語・強い断定禁止**
- **宛先は引用元投稿者ではなく "同じ問題を抱えている広いオーディエンス"**

引用元の内容に応じて切り口を変える(同方向の補強 / データ裏付け / 同方向の展開 / 実践示唆 / トレンド位置づけ)。

### Step 6.5: 同意スタンスチェック (必須)

```bash
python3 .claude/skills/_x-shared/scripts/agreement_check.py --text "<コメント>"
```

BLOCK → 再生成 → 差し替え。WARN → 再生成して SAFE を目指す。

### Step 7: 各コメントに炎上チェック

```bash
python3 .claude/skills/_x-shared/scripts/flame_check.py --text "<コメント>"
```

### Step 8: 各コメントに重複チェック

```bash
python3 .claude/skills/_x-shared/scripts/deduplicator.py check-quote \
  --entry-json '<entry>' \
  --history-json '<同サービスの履歴>'
```

### Step 9: そのサービスの 5 候補を表示

```
===== [service: synapseize] X 引用ツイート候補 N件 =====
```

各候補:

```
--- 候補 1 [SAFE] スコア 0.82 ---
```

[引用元を開く](https://x.com/handle/status/id)

投稿者: @handle | ♥ like / 🔁 repost

> 引用元本文(80字)

コメント原稿:

` ``` `
200 字以内のコメント
` ``` `

字数: XX/200 | 切り口: angle

---

**⚠️ 必須: そのサービスの候補表示の直後にブラウザ採用フロー。次のサービスに進む前に必ず完了させる。**

```bash
python3 .claude/skills/_x-shared/scripts/present_results.py \
  --kind quote \
  --json '<そのサービスの全候補>'
```

ブラウザはサービスごとに別ウィンドウ。

### Step 10: フィードバック保存 + 履歴追記 + 使用済み ID 記録

#### 10-a: スキップフィードバック (`feedback` 非空のみ)

```bash
python3 .claude/skills/_x-shared/scripts/tuning.py save \
  --kind quote \
  --service <service> \
  --feedback-json '<feedback>'
```

#### 10-b: 採用エントリを quotes.jsonl に追記

エントリには **`service` フィールド必須**:

```json
{
  "id": "quote_YYYYMMDD_HHMMSS_N",
  "created_at": "ISO8601 JST",
  "service": "<service>",
  "topic_tags": ["..."],
  "quoted_tweet": {
    "url": "...", "tweet_id": "...", "author_handle": "...",
    "author_id": "...", "text": "...", "posted_at": "...",
    "like_count": 0, "repost_count": 0
  },
  "comment_text": "...",
  "comment_char_count": 180,
  "simhash": "hex",
  "flame_score": "SAFE",
  "flame_warnings": [],
  "canvas_hash": "..."
}
```

```bash
python3 .claude/skills/_x-shared/scripts/history.py append \
  --kind quote \
  --data-json '<entry JSON>'
```

候補 5 件全てを使用済みとして記録(サービス横断):

```bash
python3 .claude/skills/_x-shared/scripts/used_tweets.py record \
  --skill quote \
  --tweet-ids-json '["<id1>", ..., "<id5>"]'
```

### Step 11: 完了メッセージ (そのサービス分)

```
✅ [service: <service>] 採用 N 件を quotes.jsonl に記録しました
```

---

## 全サービスの完了後

サービスごとのサマリを表示。

## エラーハンドリング

| 状況 | 対応 |
|---|---|
| `lean-canvas-*.md` / `lean-canvas.md` が無い | エラー停止 |
| `TWITTERAPI_IO_KEY` が空 | .env 設定を促す |
| `TAVILY_API_KEY` が空 | Tavily スキップで続けるか確認 |
| 主要クエリのユニーク取得 < 5 | Step 3.5 → 3.6 → 3.7 の順にフォールバック |
| 全候補 BLOCK | そのサービスのみスキップ、ユーザーに明示し次へ |
| TwitterAPI.io `402` | 部分結果で続行。0 件のサービスはスキップ |

## 注意事項

- **サービス間のコンテキスト分離は厳守**
- 同じアカウントを同サービス内で 2 回以上引用しない
- 引用元本文は抜粋(80 字程度)
- API 障害時はすぐに中断せず代替を提案
