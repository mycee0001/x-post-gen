---
name: x-quote
description: X (旧Twitter) で他人のツイートを引用する引用ツイート (QT) の原稿を生成する。カレントディレクトリの lean-canvas.md のキートピックで TwitterAPI.io から直近のX投稿を検索し、関連性・エンゲージメント・炎上リスクで候補をスコアリングしたのち「上位5件」に対してそれぞれコメント原稿 (日本語200字以内) を生成する。過去の引用履歴 (.x-history/quotes.jsonl) と重複しないよう自動チェックする。ユーザーが「引用ツイート」「QT」「x-quote」「/x-quote」「引用RT」「他人のツイートに乗っかる」と言ったら必ずこのスキルをトリガーすること。投稿自体は行わず、5候補をコピー可能な形で表示し、採用番号をユーザーに確認してから履歴に追記する。
---

# /x-quote スキル: X 引用ツイート生成 (5候補)

## 重要な方針

- このスキルは **引用ツイートを投稿しない**。原稿を生成して表示するだけ
- 1 回の実行で **5 つの異なる候補ツイートそれぞれに対するコメント案** を提示する
- 履歴への書き込みは **ユーザーが採用番号を選んだ後**(書き込み自体はユーザー許可不要)
- 炎上チェック **BLOCK** の候補は除外
- 炎上チェック **WARN** は警告付きで提示

## 前提条件

- カレントディレクトリに `lean-canvas.md`
- `.env` に `TWITTERAPI_IO_KEY` と `PERPLEXITY_API_KEY`
- `.claude/skills/_x-shared/` が配置済み

## 実行フロー

### Step 1: lean-canvas.md を読み込む

```bash
python3 .claude/skills/_x-shared/scripts/lean_canvas_loader.py --path ./lean-canvas.md --json
```

- 無ければエラー停止(x-post と同様)

### Step 2: 履歴を読み込み

```bash
python3 .claude/skills/_x-shared/scripts/history.py load --kind quote --since-days 30
python3 .claude/skills/_x-shared/scripts/history.py stats --kind quote
```

- `accounts_quoted_last_30d` を控えておく(同じアカウントを 2 回以上引用しないため)

### Step 3: TwitterAPI.io で X 内ツイートを検索

lean-canvas.md の `topic_tags` からクエリを 2〜3 個組み立てる。例:

- `製造業DX OR ものづくりDX`
- `手書きOCR OR 図面電子化`
- `2025年問題 製造業`

```bash
python3 .claude/skills/_x-shared/scripts/search_twitterapi.py \
  --query "<クエリ>" \
  --language ja \
  --hours-back 72 \
  --min-likes 5 \
  --max-results 30
```

- 3 クエリで合計 ~90 件 → 重複除去後ひと山に
- API キー不正 / ネットワーク障害は明示的に伝える

### Step 4: Perplexity Sonar で背景補強 (1 回のみ)

候補ツイートの主要トピックで 1 回だけ調査:

```bash
python3 .claude/skills/_x-shared/scripts/search_perplexity.py \
  --query "<背景調査クエリ>" \
  --mfg-preset
```

### Step 5: 候補をスコアリング (Claude が担当)

各候補ツイートに以下の重み付きスコアを計算:

| 項目 | 重み | 計算 |
|---|---|---|
| **関連性** | 0.4 | lean-canvas.md のキートピックとの一致度 (0-1) |
| **エンゲージメント** | 0.3 | `min(like_count / 100, 1.0)` 等の正規化 |
| **炎上リスク(負)** | 0.2 | 本文を flame_check にかけて BLOCK=-1, WARN=-0.5, SAFE=0 |
| **重複ペナルティ(負)** | 0.1 | 過去 30 日に同じアカウントを引用済みなら -1、同一 tweet_id は -∞ |

BLOCK のツイートは除外。Top 5 を選ぶ。

### Step 6: 5 候補それぞれにコメント原稿を生成

`.claude/skills/_x-shared/prompts/quote_generation.md` のテンプレートに従い、**Claude 自身** が 5 件分のコメント原稿を作る。

引用元の内容に応じて切り口を変える(現場経験 / データ裏付け / 別角度 / 実践示唆 / トレンド位置づけ)。

### Step 7: 各コメントに炎上チェック

```bash
python3 .claude/skills/_x-shared/scripts/flame_check.py --text "<コメント本文>"
```

- **BLOCK** → そのコメントを再生成(最大 2 回)、それでもダメなら候補を差し替え
- **WARN** → 警告付きで提示

### Step 8: 各コメントに重複チェック

```bash
python3 .claude/skills/_x-shared/scripts/deduplicator.py check-quote \
  --entry-json '<entry JSON>' \
  --history-json '<history JSON>'
```

重複の場合は `♻️` マーク付きで提示。

### Step 9: 5 候補を番号付きで表示

```
===== X 引用ツイート候補 5件 =====

検索クエリ: <使用したクエリ>
背景調査: <Perplexity answer の要約 1 文>

--- 候補 1 [SAFE] スコア 0.82 ---
引用元: https://x.com/<handle>/status/<id>
投稿者: @<handle> (<name>)
エンゲージメント: ♥ <like> / 🔁 <repost>
引用元本文(抜粋):
  > <80 字まで>

コメント原稿:
\`\`\`
<200 字以内のコメント>
\`\`\`
字数: XX/200
切り口: <angle>

--- 候補 2 [WARN: ...] スコア 0.71 ---
...

(5 件まで)

===============================

採用する候補番号を教えてください(複数可: "1,3" / 全部: "all" / 破棄: "none")。
採用されたものだけ .x-history/quotes.jsonl に追記されます。
```

### Step 10: 採用指示を受けて履歴に追記

```bash
python3 .claude/skills/_x-shared/scripts/history.py append \
  --kind quote \
  --data-json '<entry JSON>'
```

エントリ:

```json
{
  "id": "quote_YYYYMMDD_HHMMSS_N",
  "created_at": "ISO8601 JST",
  "topic_tags": ["..."],
  "quoted_tweet": {
    "url": "...",
    "tweet_id": "...",
    "author_handle": "...",
    "author_id": "...",
    "text": "引用元本文",
    "posted_at": "...",
    "like_count": 0,
    "repost_count": 0
  },
  "comment_text": "コメント本文",
  "comment_char_count": 180,
  "simhash": "hex",
  "flame_score": "SAFE",
  "flame_warnings": [],
  "canvas_hash": "..."
}
```

### Step 11: 完了メッセージ

```
✅ 採用: N件を .x-history/quotes.jsonl に記録しました
引用ツイートは手動で X にて投稿してください。
引用元 URL と上記コメントをそれぞれコピーしてお使いください。
```

## エラーハンドリング

| 状況 | 対応 |
|---|---|
| `lean-canvas.md` が無い | エラーメッセージで停止 |
| `TWITTERAPI_IO_KEY` が空 | .env 設定を促して停止 |
| `PERPLEXITY_API_KEY` が空 | 同上(Perplexity スキップで続けるか確認) |
| TwitterAPI.io が 0 件 | クエリを緩めて再検索するか、ユーザーに確認 |
| スコアリング後 5 件未満 | 得られた分だけ提示、理由を明示 |
| 全候補 BLOCK | クエリ変更を促して停止 |

## 注意事項

- 同じアカウントを 2 回以上引用しない(多様性確保)
- 引用元本文を全文表示しない(抜粋 80 字程度)
- スコア内訳をユーザーに見せると納得感が上がるので、できれば簡潔に
- API 障害時はすぐに中断せず、「別の方法で続けるか」を提案する
