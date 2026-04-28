---
name: x-reply
description: X (旧Twitter) でリアルタイムに流れている他人のツイートに対して「返信 (リプライ)」の原稿を 5 件生成する。カレントディレクトリの lean-canvas.md のキートピックで TwitterAPI.io から直近 6〜12 時間のX投稿を最新順に取得し、関連性 × 新鮮度で上位 5 件を選定。各候補に対して日本語200字以内のリプライ原稿を作成する。リプライはリアルタイム性と会話参加の適切さが最重要なため、履歴管理は行わない(同じポストに後日リプライしても自然)。ユーザーが「リプライ」「返信」「reply」「x-reply」「/x-reply」「コメントする」「他人のポストに返信」「ツイートに返信」「絡みに行く」と言ったら必ずこのスキルをトリガーすること。投稿自体は行わず、リプライ元URLとリプライ原稿を表示するだけ。
---

# /x-reply スキル: X リアルタイムリプライ生成 (5候補)

## 重要な方針

- このスキルは **リプライを投稿しない**。原稿を生成して表示するだけ
- **リアルタイム性が最重要**。検索は直近 6〜12 時間、queryType=Latest で最新順
- **履歴管理は行わない**(リプライは会話の一部なので、後日同ポストに返しても自然)
- 1 回の実行で **5 つの異なる候補ポスト + それぞれへのリプライ** を提示
- 炎上チェック **BLOCK** のリプライは除外して再生成
- 炎上チェック **WARN** は警告付きで提示

## x-quote との違い

| 観点 | /x-quote | /x-reply |
|---|---|---|
| 目的 | 引用ツイートで情報発信 | 会話に参加・関係構築 |
| 検索期間 | 直近 72 時間 | **直近 6〜12 時間(リアルタイム)** |
| min_likes | 5 以上 | **2 以上(新鮮ポスト拾うため緩く)** |
| スコアリング | 関連性 × エンゲージメント | **関連性 × 新鮮度** |
| 履歴管理 | あり | **なし** |
| 字数 | 200 字 | 200 字(柔らかめ) |
| トーン | 発信・論評 | 対話・共感・追加視点 |

## 前提条件

- カレントディレクトリに `lean-canvas.md`
- `.env` に `TWITTERAPI_IO_KEY`(Tavily は任意 — リアルタイム性重視のため省略も可)
- `.claude/skills/_x-shared/` が配置済み

## 実行フロー

### Step 1: lean-canvas.md を読み込む

```bash
python3 .claude/skills/_x-shared/scripts/lean_canvas_loader.py --path ./lean-canvas.md --json
```

- 無ければエラーメッセージで停止

### Step 1.5: プロジェクトローカルな調整ロジック (tuning) を読み込む

過去にユーザーがスキップした候補のフィードバックを読み込み、本実行で適用する:

```bash
python3 .claude/skills/_x-shared/scripts/tuning.py load --kind reply --since-days 30 --limit 30
```

返ってきたエントリを **必ず本実行に反映** する:

| category | 適用先 |
|---|---|
| `source` | Step 2 のクエリ構築・著者フィルタ・除外アカウントに反映(同種のポストを拾わないようクエリ調整 / 著者ハンドルを除外) |
| `content` | Step 6 の原稿生成方針に反映(指摘されたトーン/切り口/自己言及度を回避) |
| `flame` | Step 7 の炎上チェック解釈に反映(誤検知ならその種の WARN を許容、見逃しなら追加で再生成) |
| `other` | 自由記述を読んで Claude が判断 |

**重要:** このチューニングは `.x-history/tuning.jsonl` に保存されており、プロジェクト固有。
別プロジェクト(別の cwd)では別のチューニングが効く設計。

エントリ 0 件なら通常通り進める。

### Step 2: 使用済みツイート ID を取得 + TwitterAPI.io でリアルタイムに関連ポストを検索

まず他スキル(x-quote)で使用済みのツイート ID を取得して除外リストにする:

```bash
python3 .claude/skills/_x-shared/scripts/used_tweets.py load --hours-back 48
```

返り値の JSON 配列を `<除外ID JSON>` として検索に渡す。

lean-canvas.md の `topic_tags` から **3 クエリ** を組み立てる。例:

- `製造業DX OR ものづくりDX`
- `手書きOCR OR 図面電子化`
- `2025年問題 製造業 OR 技能継承`

**リアルタイム性 + リーチ重視の設定:**

```bash
python3 .claude/skills/_x-shared/scripts/search_twitterapi.py \
  --query "<クエリ>" \
  --language ja \
  --hours-back 12 \
  --min-likes 5 \
  --min-author-followers 500 \
  --max-replies 300 \
  --max-results 20 \
  --exclude-ids-json '<除外ID JSON>'
```

- `--hours-back 12`(必要なら 6 に短縮)で **直近ツイートのみ**
- `--min-likes 5` でフレッシュさを保ちつつフロアを上げる(2 → 5)
- **`--min-author-followers 500`** で著者リーチを担保(中堅アカウント以上)
- **`--max-replies 300`** でメガバイラル除外(自分のリプが埋もれる投稿を回避)
- `--exclude-ids-json` で **x-quote で使用済みのツイートを除外**
- 3 クエリ × 20 件 ≒ 60 件を取得、重複除去

**重要:** `search_twitterapi.py` は内部で `queryType=Latest` をデフォルトで使用するため、
**最新順** で返ってくる。スコアリング前の時点で既に新鮮。

### Step 2.5: 第 1 段階フォールバック (サブカテゴリ 3 個)

**3 クエリの結果を重複除去した後、ユニークツイート数 < 5 の場合のみ実行する。**
ユニーク数 ≥ 5 ならこの Step はスキップして Step 3 へ進む。

#### 2.5-a: サブカテゴリのキャッシュ確認

```bash
python3 .claude/skills/_x-shared/scripts/subcategory_generator.py load \
  --canvas-hash <Step 1 で取得した canvas.content_hash>
```

返り値:
- `{"hit": true, "entry": {...}}` → キャッシュあり。`entry.subcategories` を使って 2.5-c へ
- `{"hit": false}` → キャッシュなし。2.5-b へ

#### 2.5-b: Claude がサブカテゴリを生成 (キャッシュ miss 時のみ)

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

#### 2.5-c: サブカテゴリの各クエリで追加検索

各サブカテゴリの `queries` を `search_twitterapi.py` に渡して追加検索する。
**API クレジット節約のため `--max-results 10` に縮小する。**
リーチフィルタ (`--min-author-followers` / `--max-replies`) は Step 2 と同じ値を使う。

```bash
python3 .claude/skills/_x-shared/scripts/search_twitterapi.py \
  --query "<subcategory.queries[i]>" \
  --language ja \
  --hours-back 12 \
  --min-likes 5 \
  --min-author-followers 500 \
  --max-replies 300 \
  --max-results 10 \
  --exclude-ids-json '<除外ID JSON>'
```

3 サブカテゴリ × 1〜2 クエリ ≒ 30〜60 件を追加で取得し、Step 2 の主要結果とマージ (重複除去)。

**重要:** マージ時、各候補に **由来フラグ** を付ける。
- `origin: "main"` (Step 2 由来) → スコアそのまま
- `origin: "subcategory"` (Step 2.5-c 由来) → Step 3 のスコアリング時に **関連性スコア × 0.7** を適用

### Step 2.6: 第 2 段階フォールバック (サブカテゴリ追加 3 個)

Step 2.5 完了後、リーチフィルタ通過後のユニークツイート数が **依然として < 5** の場合のみ実行する。

`subcategory_generation.md` の **「第 2 段階」セクション** に従い、Claude が **既存 3 個と異なる** サブカテゴリを **追加 3 個** 生成する。

```bash
python3 .claude/skills/_x-shared/scripts/subcategory_generator.py append \
  --canvas-hash <canvas.content_hash> \
  --subcategories-json '<追加 3 個の JSON>'
```

その後、追加 3 サブカテゴリのクエリで Step 2.5-c と同じパラメータで検索し、結果をマージ (`origin: "subcategory"` のまま)。

**この段階でも < 5 件なら Step 2.7 (時間拡張) に進む。**

### Step 2.7: 最終手段 — 時間窓拡張

Step 2.5 / 2.6 後も < 5 件の場合のみ、**最後の手段** として `--hours-back 24` に拡張して主要クエリ (Step 2) のみ再実行する。
鮮度を犠牲にするため、ここまで来たら鮮度減点を覚悟する。

### Step 3: スコアリング (リアルタイム + リーチ版)

各候補に以下の重み付きスコアを計算:

| 項目 | 重み | 計算 |
|---|---:|---|
| **関連性** | 0.30 | lean-canvas.md のキートピックとの一致度 (0-1)。**`origin == "subcategory"` の候補は最後に × 0.7** |
| **新鮮度** | 0.20 | `1.0 - (hours_since_post / 12)` を 0〜1 にクリップ |
| **リーチ** (新規) | 0.30 | 下記 3 サブシグナルの加重平均 |
| **会話参加性** | 0.20 | `reply_count` が適度(5〜30)なら +、0 や 50+ は減点 |
| **炎上リスク(負)** | - | 引用元本文を flame_check にかけて BLOCK なら **除外** |

#### リーチ Score の計算

```
reach = 0.45 × author_reach
      + 0.35 × engagement_velocity
      + 0.20 × conversation_activity
```

- `author_reach`: フォロワー数を**ベル型** (1k〜50k がピーク 1.0)。1k 未満は線形減点、50k 超は対数減衰 (大物アカウントは競合が多すぎてリプが埋もれる)
- `engagement_velocity`: `like_count / max(hours_since_post, 0.5)` を `min(velocity / 20, 1.0)` で正規化 (1 時間あたり 20 like で 1.0)
- `conversation_activity`: `reply_count` が 5〜30 で 1.0、0 で 0.3、50+ で 0.5 (会話に巻き込まれて表示される効果)

※ エンゲージメント絶対値ではなく **速度** を見るのは、12 時間幅で公平比較するため。
※ 認証済み (`author_verified`) の候補は最後に **+0.05** ボーナス (アルゴリズムブースト考慮)。

### Step 4: 上位 5 件を選定

- BLOCK のポストは除外
- 同一アカウントは上位 2 件まで(多様性)
- 5 件に満たない場合はクエリを増やして再検索するか、得られた分だけ提示

### Step 5: (任意) Tavily で背景補強

**デフォルトはスキップ**。リプライは「その場のノリ」が重要なので、詳細調査は不要なことが多い。
ただし専門用語や数字を含むトピックの場合のみ 1 回だけ呼ぶ:

```bash
python3 .claude/skills/_x-shared/scripts/search_tavily.py \
  --query "<背景補強クエリ>" \
  --recency week
```

### Step 6: 5 候補それぞれにリプライ原稿を生成

`.claude/skills/_x-shared/prompts/reply_generation.md` のテンプレートに従い、**Claude 自身** が 5 件分のリプライ原稿を作る。

リプライの基本方針:
- **価値付加**: 現場経験/データ/別視点のいずれかを加える
- **対話的**: 相手のポストを踏まえたうえで会話を前に進める(一方的な発信にならない)
- **自然なトーン**: 絵文字 1 個まで、くだけすぎない
- **自社 SaaS は出さない**: リプライで PR は強引。関係構築を優先

### Step 7: 各リプライに炎上チェック

```bash
python3 .claude/skills/_x-shared/scripts/flame_check.py --text "<リプライ本文>"
```

- **BLOCK** → そのリプライを再生成(最大 2 回)、ダメなら候補差し替え
- **WARN** → 警告付きで提示

### Step 8: 5 候補を番号付きで表示

**出力フォーマット（CLI 操作性重視）:**

各候補は以下の構造で出力する。ポイント:
- **リプライ先 URL** はマークダウンリンク `[リプライ先を開く](URL)` で表示 → CLI 上でクリックして X に遷移可能
- **リプライ原稿** は独立したコードブロック（` ``` `）で表示 → CLI 上のコピーボタンでクリップボードにコピー可能
- 各候補の間は `---` で区切る

```
===== X リプライ候補 N件 =====

検索クエリ: <使用したクエリ>
検索時刻: <現在時刻>
取得対象: 直近 12 時間、最新順
```

各候補:

```
--- 候補 1 [SAFE] 関連性 0.8 / 新鮮度 0.9 (2時間前) ---
```

[リプライ先を開く](https://x.com/handle/status/id)

投稿者: @handle (name) | 投稿時刻: JST | ♥ like / 🔁 repost / 💬 reply

> 引用元本文(80字まで)

リプライ原稿:

` ``` `
200 字以内のリプライ
` ``` `

字数: XX/200 | 切り口: angle

---

(以降 N 件まで繰り返し)

```
💡 リプライはリアルタイム性が重要なので、早めに投稿することを推奨します。
```

**⚠️ 必須: 候補を表示したら、必ず以下のブラウザ採用フローを実行すること。**
**他のスキルの実行や別の話題に移る前に、必ずこのフローを完了させること。**

候補表示の直後に、`present_results.py` でブラウザを開き、ユーザーに採用/不採用を判断してもらう:

```bash
python3 .claude/skills/_x-shared/scripts/present_results.py \
  --kind reply \
  --json '<全候補の JSON 配列>'
```

JSON 配列の各要素:
```json
{"number": 1, "url": "https://x.com/...", "author": "@handle", "source_text": "引用元80字", "reply_text": "リプライ本文", "flame": "SAFE"}
```

**ブラウザ上で:**
- 各候補に **Adopt / Skip ボタン**、**Copy ボタン**、**Open in X リンク** が表示される
- ユーザーが全候補の判定を終えて **Complete ボタン** を押す
- **スキップが 1 件でもあれば** 自動的にスキップ理由フォームが表示される(カテゴリ: source / content / flame / other + 自由記述)
- フォーム入力後 **Complete を再度クリック** で送信され、スクリプトが結果 JSON を stdout に返す
- 戻り値: `{"adopted": [1, 3], "skipped": [2, 4, 5], "feedback": [...], "auto_adopted": false}`

**タイムアウト動作 (10 分):**
ユーザーがブラウザで何も応答しないまま 10 分経過すると、`present_results.py` は
**全候補を強制的に「採用」扱い** で返す (`{"adopted": [全番号], "skipped": [], "feedback": [], "auto_adopted": true}`)。
これにより履歴管理が中断されず、ブラウザのタブも自然に閉じられる。

### Step 9: フィードバックを保存 + 使用済みツイート ID を記録 + 完了

#### 9-a: スキップフィードバックの保存 (`feedback` が非空の場合のみ)

ブラウザから返ってきた `feedback` 配列を tuning に保存:

```bash
python3 .claude/skills/_x-shared/scripts/tuning.py save \
  --kind reply \
  --feedback-json '<feedback 配列の JSON>'
```

これは次回 `/x-reply` 実行時の Step 1.5 で読み込まれ、ロジック調整に使われる。

#### 9-b: 使用済みツイート ID の記録

**リプライの履歴管理(quotes.jsonl 的なもの)は行わない** が、
候補として提示した 5 件のツイート ID は **使用済みステートに記録する**:

```bash
python3 .claude/skills/_x-shared/scripts/used_tweets.py record \
  --skill reply \
  --tweet-ids-json '["<tweet_id_1>", "<tweet_id_2>", ..., "<tweet_id_5>"]'
```

これにより、同じタイミングや近いタイミングで `/x-quote` を実行しても、
ここで候補に挙がったツイートは除外される。

#### 9-c: 完了メッセージ

ユーザーは気に入った候補を選んで手動でリプライする。
`auto_adopted: true` の場合は「ブラウザでの応答がなかったため全候補を自動採用しました」を明示する。

## エラーハンドリング

| 状況 | 対応 |
|---|---|
| `lean-canvas.md` が無い | エラーで停止 |
| `TWITTERAPI_IO_KEY` が空 | .env 設定を促して停止 |
| 主要クエリのユニーク取得が 5 件未満 | **Step 2.5 (第 1 段階サブカテ 3 個)** → **Step 2.6 (第 2 段階サブカテ追加 3 個 計 6 個)** → **Step 2.7 (時間拡張)** の順にフォールバック |
| サブカテゴリ生成が JSON 不正 | プロンプトを再読込して再生成 (最大 2 回)、それでも失敗ならスキップして次の Step へ |
| 5 件取得できるが全て BLOCK | クエリ変更を促して停止 |
| スコアリング後 5 件未満 | 得られた分だけ提示、理由を明示 |
| TwitterAPI.io が `429` | 3 秒待って 1 回リトライ(search_twitterapi.py 内で対応) |
| TwitterAPI.io が `402`(クレジット不足) | **それまでに成功したクエリの結果を使って候補生成を続行する**。1 件も取得できていない場合のみ停止し、クレジットリチャージを促す。途中で 402 になった旨をユーザーに明示する |

## 注意事項

- **リアルタイム性が命**。ユーザーが画面で見た時から時間が経つほど価値が下がる
- 候補ポストがまだ反応が少ない(likes=2 とか)のは **悪くない**。むしろフレッシュな会話に早く入れる
- 炎上中の長いスレッド(reply_count 50+)には参戦しない(スコアで -0.3)
- リプライは「相手との関係構築」。発信モードではなく **対話モード** のトーンで
- 自社 SaaS「STOW.」を毎回出さない。5 件中 1 件程度に自然な形で言及がある、くらいが丁度いい
- 絵文字は 1 個まで、ハッシュタグは付けない(リプライでは不要)
