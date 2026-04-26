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
- `.env` に `TWITTERAPI_IO_KEY` と `TAVILY_API_KEY`
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
python3 .claude/skills/_x-shared/scripts/used_tweets.py load --hours-back 48
```

- `accounts_quoted_last_30d` を控えておく(同じアカウントを 2 回以上引用しないため)
- `used_tweets.py load` の返り値(JSON 配列)を `<除外ID JSON>` として Step 3 に渡す
  - これにより **x-reply で既に使用した候補ツイートを除外** できる

### Step 3: TwitterAPI.io で X 内ツイートを検索

lean-canvas.md の `topic_tags` からクエリを 2〜3 個組み立てる。例:

- `製造業DX OR ものづくりDX`
- `手書きOCR OR 図面電子化`
- `2025年問題 製造業`

**引用ツイートは普遍的な内容やバズっているポストを狙う。**
リアルタイム性よりも **エンゲージメント(いいね・RT)が大きいポスト** を優先する。

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

- `--hours-back 24`(72h から短縮。ただし普遍的な内容を狙うため、24h 以内で十分バズっているものを対象)
- `--min-likes 20`(高エンゲージメントに絞る。10 → 20 に引き上げ、ノイズを更に削減)
- **`--min-author-followers 1000`** で著者リーチを担保(中堅以上のアカウント)
- **`--max-replies 300`** でメガバイラル除外(自分の引用が埋もれる投稿を回避)
- `--exclude-ids-json` に Step 2 で取得した使用済み ID を渡す
- 3 クエリで合計 ~90 件 → 重複除去後ひと山に
- API キー不正 / ネットワーク障害は明示的に伝える
- 結果が少なすぎる場合は **Step 3.5 (サブカテフォールバック)** に進む (フィルタを緩めるより質を保つ方を優先)

### Step 3.5: 第 1 段階フォールバック (サブカテゴリ 3 個)

**3 クエリの結果を重複除去した後、ユニークツイート数 < 5 の場合のみ実行する。**
ユニーク数 ≥ 5 ならこの Step はスキップして Step 4 へ進む。

#### 3.5-a: サブカテゴリのキャッシュ確認

```bash
python3 .claude/skills/_x-shared/scripts/subcategory_generator.py load \
  --canvas-hash <Step 1 で取得した canvas.content_hash>
```

返り値:
- `{"hit": true, "entry": {...}}` → キャッシュあり。`entry.subcategories` を使って 3.5-c へ
- `{"hit": false}` → キャッシュなし。3.5-b へ

#### 3.5-b: Claude がサブカテゴリを生成 (キャッシュ miss 時のみ)

`.claude/skills/_x-shared/prompts/subcategory_generation.md` を読み込み、
そのプロンプトの指示通りに **Claude 自身が 3 個のサブカテゴリを生成** する。

入力コンテキスト:
- Step 1 の `canvas.sections` (problem / solution / customer_segments / channels / uvp / unfair_advantage)
- Step 1 の `canvas.topic_tags` (主要クエリで既に使用したキーワード — これと完全一致しないこと)

生成後、必ずキャッシュに保存する:

```bash
python3 .claude/skills/_x-shared/scripts/subcategory_generator.py save \
  --canvas-hash <canvas.content_hash> \
  --subcategories-json '<生成した 3 個のサブカテゴリ JSON 配列>'
```

#### 3.5-c: サブカテゴリの各クエリで追加検索

各サブカテゴリの `queries` を `search_twitterapi.py` に渡して追加検索する。
**API クレジット節約のため `--max-results 10` に縮小する。** リーチフィルタは Step 3 と同じ値を使う。

```bash
python3 .claude/skills/_x-shared/scripts/search_twitterapi.py \
  --query "<subcategory.queries[i]>" \
  --language ja \
  --hours-back 24 \
  --min-likes 20 \
  --min-author-followers 1000 \
  --max-replies 300 \
  --max-results 10 \
  --exclude-ids-json '<除外ID JSON>'
```

3 サブカテゴリ × 1〜2 クエリ ≒ 30〜60 件を追加で取得し、Step 3 の主要結果とマージ (重複除去)。

**重要:** マージ時、各候補に **由来フラグ** を付ける。
- `origin: "main"` (Step 3 由来) → スコアそのまま
- `origin: "subcategory"` (Step 3.5-c 由来) → Step 5 のスコアリング時に **関連性スコア × 0.7** を適用

### Step 3.6: 第 2 段階フォールバック (サブカテゴリ追加 3 個)

Step 3.5 完了後、リーチフィルタ通過後のユニークツイート数が **依然として < 5** の場合のみ実行する。

`subcategory_generation.md` の **「第 2 段階」セクション** に従い、Claude が **既存 3 個と異なる** サブカテゴリを **追加 3 個** 生成する。

```bash
python3 .claude/skills/_x-shared/scripts/subcategory_generator.py append \
  --canvas-hash <canvas.content_hash> \
  --subcategories-json '<追加 3 個の JSON>'
```

その後、追加 3 サブカテゴリのクエリで Step 3.5-c と同じパラメータで検索し、結果をマージ (`origin: "subcategory"` のまま)。

**この段階でも < 5 件なら Step 3.7 (フィルタ緩和) に進む。**

### Step 3.7: 最終手段 — フィルタ緩和

Step 3.5 / 3.6 後も < 5 件の場合のみ、**最後の手段** として以下のフィルタを段階的に緩める:

1. `--min-likes 20` → `10`
2. それでも 5 件未満なら `--min-author-followers 1000` → `500`

これらは質を犠牲にするため最終手段とする。
ここまで来ても 0 件なら、ユーザーに lean-canvas のトピックタグ見直しを促す。

### Step 4: Tavily Search で背景補強 (1 回のみ)

候補ツイートの主要トピックで 1 回だけ調査:

```bash
python3 .claude/skills/_x-shared/scripts/search_tavily.py \
  --query "<背景調査クエリ>" \
  --mfg-preset
```

### Step 5: 候補をスコアリング (Claude が担当)

各候補ツイートに以下の重み付きスコアを計算:

| 項目 | 重み | 計算 |
|---|---|---|
| **関連性** | 0.30 | lean-canvas.md のキートピックとの一致度 (0-1)。**`origin == "subcategory"` の候補は最後に × 0.7** |
| **リーチ** (新規) | 0.45 | 下記 3 サブシグナルの加重平均。**従来のエンゲージメント (0.40) を置換・拡張** |
| **炎上リスク(負)** | 0.15 | 本文を flame_check にかけて BLOCK=-1, WARN=-0.5, SAFE=0 |
| **重複ペナルティ(負)** | 0.10 | 過去 30 日に同じアカウントを引用済みなら -1、同一 tweet_id は -∞ |

BLOCK のツイートは除外。Top 5 を選ぶ。

#### リーチ Score の計算

```
reach = 0.45 × author_reach
      + 0.35 × engagement_velocity
      + 0.20 × conversation_activity
```

- `author_reach`: フォロワー数を**ベル型** (1k〜50k がピーク 1.0)。1k 未満は線形減点、50k 超は対数減衰 (大物アカは引用が埋もれる)
- `engagement_velocity`: `like_count / max(hours_since_post, 0.5)` を `min(velocity / 30, 1.0)` で正規化 (1 時間あたり 30 like で 1.0)
- `conversation_activity`: `reply_count` が 5〜30 で 1.0、0 で 0.3、50+ で 0.5

※ 認証済み (`author_verified`) の候補は最後に **+0.05** ボーナス (アルゴリズムブースト考慮)。

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
背景調査: <Tavily answer の要約 1 文>

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
```

**⚠️ 必須: 候補を表示したら、必ず以下の採用確認を行うこと。**
**他のスキルの実行や別の話題に移る前に、必ずこの確認を完了させること。**

候補表示の直後に、`AskUserQuestion` ツールを使って以下の質問をユーザーに投げかける:

> 採用する候補番号を教えてください（複数可: "1,3" / 全部: "all" / 破棄: "none"）

- ユーザーが回答するまで **次のステップに進まない**
- ユーザーが別の話題やスキルを実行しようとした場合でも、まずこの採用確認を完了させる
- 回答を受け取ったら即座に Step 10 に進む

### Step 10: 採用指示を受けて履歴に追記 + 使用済みツイート ID を記録

```bash
python3 .claude/skills/_x-shared/scripts/history.py append \
  --kind quote \
  --data-json '<entry JSON>'
```

**採用・不採用に関わらず、候補として提示した 5 件すべてのツイート ID を使用済みとして記録する:**

```bash
python3 .claude/skills/_x-shared/scripts/used_tweets.py record \
  --skill quote \
  --tweet-ids-json '["<tweet_id_1>", "<tweet_id_2>", ..., "<tweet_id_5>"]'
```

これにより、同じタイミングや近いタイミングで `/x-reply` を実行しても、
ここで候補に挙がったツイートは除外される。

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
| `TAVILY_API_KEY` が空 | 同上(Tavily スキップで続けるか確認) |
| 主要クエリのユニーク取得が 5 件未満 | **Step 3.5 (第 1 段階サブカテ 3 個)** → **Step 3.6 (第 2 段階サブカテ追加 3 個 計 6 個)** → **Step 3.7 (フィルタ緩和)** の順にフォールバック |
| サブカテゴリ生成が JSON 不正 | プロンプトを再読込して再生成 (最大 2 回)、それでも失敗ならスキップして次の Step へ |
| スコアリング後 5 件未満 | 得られた分だけ提示、理由を明示 |
| 全候補 BLOCK | クエリ変更を促して停止 |

## 注意事項

- 同じアカウントを 2 回以上引用しない(多様性確保)
- 引用元本文を全文表示しない(抜粋 80 字程度)
- スコア内訳をユーザーに見せると納得感が上がるので、できれば簡潔に
- API 障害時はすぐに中断せず、「別の方法で続けるか」を提案する
