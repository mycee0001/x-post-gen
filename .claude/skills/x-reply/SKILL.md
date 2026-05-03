---
name: x-reply
description: X (旧Twitter) で活発な議論が起きているポストに対して「返信 (リプライ)」の原稿を 5 件生成する。X Premium+ の返信ブースト(スレッド内上位表示・最大15倍リーチ)を最大化する設計。カレントディレクトリの lean-canvas.md のキートピックで TwitterAPI.io から直近 24 時間のX投稿を取得し、関連性 × 活発度(返信数) × リーチで上位 5 件を選定。各候補に対して日本語70-100字推奨(140字上限)・1リプ1メッセージのリプライ原稿を作成する(調査結果: 71-100字がエンゲージメント最高)。履歴管理は行わない(同じポストに後日リプライしても自然)。ユーザーが「リプライ」「返信」「reply」「x-reply」「/x-reply」「コメントする」「他人のポストに返信」「ツイートに返信」「絡みに行く」と言ったら必ずこのスキルをトリガーすること。投稿自体は行わず、リプライ元URLとリプライ原稿を表示するだけ。
---

# /x-reply スキル: X 活発スレッド向けリプライ生成 (5候補)

## 重要な方針

- このスキルは **リプライを投稿しない**。原稿を生成して表示するだけ
- **X Premium+ の返信ブーストを最大化** する設計。Premium+ はスレッド内で返信が上位表示され、アクティブな議論で 30〜40% 高い返信インプレッション、最大 15 倍のリーチ倍率を持つ
- ターゲットは **多数の返信があるアクティブな議論ポスト**(reply_count が多い = 元ポストのインプレッションも大きい = Premium+ ブーストの恩恵が最大化)
- 検索は **直近 24 時間** で、活発度(reply_count・likes)を重視。新鮮度は二次指標
- **履歴管理は行わない**(リプライは会話の一部なので、後日同ポストに返しても自然)
- 1 回の実行で **5 つの異なる候補ポスト + それぞれへのリプライ** を提示
- 炎上チェック **BLOCK** のリプライは除外して再生成、**WARN** は警告付きで提示

## x-quote との違い

| 観点 | /x-quote | /x-reply |
|---|---|---|
| 目的 | 引用ツイートで情報発信 | **会話に参加 / Premium+ 返信ブースト活用** |
| 検索期間 | 直近 72 時間 | **直近 24 時間** |
| min_likes | 5 以上 | **30 以上**(議論が走り始めたツイート) |
| min_replies | フィルタなし | **5 以上**(活発度フロア) |
| max_replies | フィルタなし | **撤廃**(メガバイラルも歓迎) |
| スコアリング | 関連性 × エンゲージメント | **関連性 × 活発度 × リーチ** |
| 履歴管理 | あり | なし |
| 字数 | 200 字 | **70-100 字推奨 / 140 字上限** (調査: 71-100字が +17% エンゲージメント) |
| トーン | 発信・論評 | 対話・共感・追加視点 |

## 前提条件

- カレントディレクトリに `lean-canvas.md`
- `.env` に `TWITTERAPI_IO_KEY`(Tavily は任意 — その場のノリ重視のため省略も可)
- `.claude/skills/_x-shared/` が配置済み
- ユーザーアカウントが **X Premium+ 加入**(返信ブースト前提のロジック)

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

### Step 2: 使用済みツイート ID を取得 + TwitterAPI.io で活発な議論ポストを検索

まず他スキル(x-quote)で使用済みのツイート ID を取得して除外リストにする:

```bash
python3 .claude/skills/_x-shared/scripts/used_tweets.py load --hours-back 48
```

返り値の JSON 配列を `<除外ID JSON>` として検索に渡す。

lean-canvas.md の `topic_tags` から **3 クエリ** を組み立てる。例:

- `製造業DX OR ものづくりDX`
- `手書きOCR OR 図面電子化`
- `2025年問題 製造業 OR 技能継承`

**活発度 + リーチ重視の設定 (Premium+ 返信ブースト最適化):**

```bash
python3 .claude/skills/_x-shared/scripts/search_twitterapi.py \
  --query "<クエリ>" \
  --language ja \
  --hours-back 24 \
  --min-likes 30 \
  --min-replies 5 \
  --min-author-followers 500 \
  --max-results 25 \
  --exclude-ids-json '<除外ID JSON>'
```

- `--hours-back 24` で **議論が成熟する時間幅** を確保(リアルタイム性は二次指標)
- `--min-likes 30` で **議論が走り始めたツイート** に絞る
- **`--min-replies 5`** で **既に会話が始まっているポスト** だけを対象にする(活発度フロア / Premium+ ブースト最適化の核)
- `--min-author-followers 500` で著者リーチを担保(中堅アカウント以上)
- **`--max-replies` は指定しない**(メガバイラル除外しない / Premium+ では多いほどブースト価値が高い)
- `--exclude-ids-json` で **x-quote で使用済みのツイートを除外**
- 3 クエリ × 25 件 ≒ 75 件を取得、重複除去

**重要:** `search_twitterapi.py` は内部で `queryType=Latest` をデフォルトで使用するため、
**最新順** で返ってくる。スコアリングで活発度を重視するので、Latest 取得後に再ランキングする。

### Step 2.5: 第 1 段階フォールバック (サブカテゴリ 5 個)

**3 クエリの結果を重複除去した後、ユニークツイート数 < 8 の場合のみ実行する。**
ユニーク数 ≥ 8 ならこの Step はスキップして Step 3 へ進む。

(注: 旧版では < 5 で発動していたが、活発度フィルタで取得数が減りやすいため閾値を緩めた)

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
そのプロンプトの指示通りに **Claude 自身が 5 個のサブカテゴリを生成** する。

入力コンテキスト:
- Step 1 の `canvas.sections` (problem / solution / customer_segments / channels / uvp / unfair_advantage)
- Step 1 の `canvas.topic_tags` (主要クエリで既に使用したキーワード — これと完全一致しないこと)

生成後、必ずキャッシュに保存する:

```bash
python3 .claude/skills/_x-shared/scripts/subcategory_generator.py save \
  --canvas-hash <canvas.content_hash> \
  --subcategories-json '<生成した 5 個のサブカテゴリ JSON 配列>'
```

#### 2.5-c: サブカテゴリの各クエリで追加検索

各サブカテゴリの `queries` を `search_twitterapi.py` に渡して追加検索する。
**API クレジット節約のため `--max-results 12` に縮小する。**
活発度・リーチフィルタは Step 2 と同じ値を使う。

```bash
python3 .claude/skills/_x-shared/scripts/search_twitterapi.py \
  --query "<subcategory.queries[i]>" \
  --language ja \
  --hours-back 24 \
  --min-likes 30 \
  --min-replies 5 \
  --min-author-followers 500 \
  --max-results 12 \
  --exclude-ids-json '<除外ID JSON>'
```

5 サブカテゴリ × 1〜2 クエリ ≒ 60〜120 件を追加で取得し、Step 2 の主要結果とマージ (重複除去)。

**重要:** マージ時、各候補に **由来フラグ** を付ける。
- `origin: "main"` (Step 2 由来) → スコアそのまま
- `origin: "subcategory"` (Step 2.5-c 由来) → Step 3 のスコアリング時に **関連性スコア × 0.7** を適用

### Step 2.6: 第 2 段階フォールバック (サブカテゴリ追加 5 個)

Step 2.5 完了後、活発度・リーチフィルタ通過後のユニークツイート数が **依然として < 5** の場合のみ実行する。

`subcategory_generation.md` の **「第 2 段階」セクション** に従い、Claude が **既存 5 個と異なる** サブカテゴリを **追加 5 個** 生成する。

```bash
python3 .claude/skills/_x-shared/scripts/subcategory_generator.py append \
  --canvas-hash <canvas.content_hash> \
  --subcategories-json '<追加 5 個の JSON>'
```

その後、追加 5 サブカテゴリのクエリで Step 2.5-c と同じパラメータで検索し、結果をマージ (`origin: "subcategory"` のまま)。

**この段階でも < 5 件なら Step 2.7 (条件緩和) に進む。**

### Step 2.7: 最終手段 — 条件緩和

Step 2.5 / 2.6 後も < 5 件の場合のみ、**最後の手段** として下記の順で条件を緩める:

1. `--min-replies 5` → `--min-replies 2` (活発度フロアを下げる)
2. `--hours-back 24` → `--hours-back 48` (時間窓を広げる)
3. `--min-likes 30` → `--min-likes 10` (likes フロアを下げる)

主要クエリ (Step 2) のみ再実行。Premium+ ブーストの恩恵は減るが、5 件確保を優先。

### Step 3: スコアリング (Premium+ 返信ブースト最適化版)

各候補に以下の重み付きスコアを計算:

| 項目 | 重み | 計算 |
|---|---:|---|
| **関連性** | 0.25 | lean-canvas.md のキートピックとの一致度 (0-1)。**`origin == "subcategory"` の候補は最後に × 0.7** |
| **活発度** (新規・重要) | 0.30 | reply_count の値で決定。下記カーブを参照 |
| **リーチ** | 0.20 | 著者フォロワー数 × engagement_velocity の加重平均 |
| **新鮮度** | 0.15 | `1.0 - (hours_since_post / 24)` を 0〜1 にクリップ |
| **認証ボーナス** | +0.05 | `author_verified` (Premium 加入者) の場合に加算 |
| **炎上リスク(負)** | - | 引用元本文を flame_check にかけて BLOCK なら **除外** |

#### 活発度 Score の計算 (reply_count ベース、Premium+ ブースト最適点は 50-199)

reply_count が多いほど元ポストのインプレッションも大きく、Premium+ のスレッド内上位表示の恩恵が最大化する:

| reply_count | activity score |
|---:|---:|
| 0-4 | 0.0 (Step 2 で除外済み) |
| 5-19 | 0.5 |
| 20-49 | 0.8 |
| **50-199** | **1.0 (最適点)** |
| 200-499 | 0.95 |
| 500-999 | 0.85 |
| 1000+ | 0.7 (飽和気味だが価値あり) |

#### リーチ Score の計算

```
reach = 0.6 × author_reach + 0.4 × engagement_velocity
```

- `author_reach`: フォロワー数を**ベル型** (1k〜100k がピーク 1.0)。1k 未満は線形減点、100k 超は対数減衰
- `engagement_velocity`: `like_count / max(hours_since_post, 0.5)` を `min(velocity / 50, 1.0)` で正規化 (1 時間あたり 50 like で 1.0 / 旧版 20 → 50 にスケールアップ)

※ メガバイラル減点は撤廃 (Premium+ ではむしろ大きい議論ほど良い)

### Step 4: 上位 5 件を選定

- BLOCK のポストは除外
- 同一アカウントは上位 2 件まで(多様性)
- 5 件に満たない場合は得られた分だけ提示し、理由を明示

### Step 5: (任意) Tavily で背景補強

**デフォルトはスキップ**。リプライは「その場のノリ」が重要なので、詳細調査は不要なことが多い。
ただし専門用語や数字を含むトピックの場合のみ 1 回だけ呼ぶ:

```bash
python3 .claude/skills/_x-shared/scripts/search_tavily.py \
  --query "<背景補強クエリ>" \
  --recency week
```

### Step 6: 5 候補それぞれにリプライ原稿を生成

**必読:** 以下の 2 ファイルを **必ず両方読み込んだうえで** 5 件分の原稿を作る。
- `.claude/skills/_x-shared/prompts/reply_generation.md` (リプライ固有のルール)
- `.claude/skills/_x-shared/prompts/japanese_writing_style.md` (日本語ベストプラクティス・全 X 系共通)

主要ルール（詳細は上記 2 ファイル参照）:
- **完全同意スタンスの強制** — 元ポストへの否定・反論・相対化・上から目線の指摘・敵視メタファーは絶対禁止。許される姿勢は (1) 同方向の補強 / (2) 同方向の具体化 / (3) 同方向の展開 / (4) 建設的な深掘り質問 の 4 種類のみ(詳細は `japanese_writing_style.md` 第 9 節)
- **冒頭でカギカッコ引用パターンを使わない** (「『〇〇』、〜ですね。」のような書き出しは禁止)
- **自己ポジショニング明示句を使わない** (「ADHD向けアプリを作っている側でも」「当事者向け設計でも」「現場でも」「私の専門領域でも」等は禁止)。権威は表に出さず、自分の知識範囲を使って役立つ考え・示唆で呼応する形にする。専門性は **言葉の精度・機序の指摘・論点の接続** で暗黙に滲ませる
- **主語は相手の論点に据える** — 主役はリプライ元のポスト。発信者の自己紹介ではない
- **文体は丁寧体（です・ます）、一人称は「私」**
- **一行最大 50 字、理想 35 字** で改行を入れる
- **中学生でもわかる単語** に置き換える。専門用語・略語は説明を添える
- **使用禁止用語**（略式侮蔑語・レッテル・差別用語・性的侮辱）に該当する語を一切使わない
- **強い断定**（絶対・必ず・100%・唯一）を使わない
- 価値付加は **機序の指摘 / 具体例 / データ裏付け / 同方向の展開** のいずれかで行う(否定方向の "別視点" は禁止、「現場経験」を地の文で語らない)
- 自社プロダクトの強引な宣伝は避ける（5 件中 0〜1 件、自然な文脈のみ）
- **活発な議論への参入として、上位スレッドで読まれる前提で書く**(短く、密度高く、同方向の補強で目立つ)

出力前に `japanese_writing_style.md` 第 8 節のチェックリストで自己点検すること。

### Step 6.5: 同意スタンスチェック (必須)

各リプライ案に対して、元ポストへの同意スタンスが保たれているかを `agreement_check.py` で機械的に検証する:

```bash
python3 .claude/skills/_x-shared/scripts/agreement_check.py --text "<リプライ本文>"
```

判定:
- **BLOCK** → 否定・反論・相対化・敵視メタファー等が検出された。**そのリプライを再生成必須(最大 2 回)**。3 回目でも BLOCK なら **その候補ツイートを差し替え**(別の元ポストに対してリプライ生成)
- **WARN** → 同意の温度を下げる前置き(逆接・限定・上から目線等)が検出された。**再生成して SAFE を目指す**。再生成しても WARN が残り、文意としては同意方向であると確信できる場合のみ警告付きで提示
- **SAFE** → 通過。Step 7 へ

5 件すべてが SAFE になるまで Step 6 ⇄ Step 6.5 をループする。

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
- **活発度を強調する** ため、reply_count を見やすく表示

```
===== X リプライ候補 N件 =====

検索クエリ: <使用したクエリ>
検索時刻: <現在時刻>
取得対象: 直近 24 時間、min_likes=30, min_replies=5
```

各候補:

```
--- 候補 1 [SAFE] 関連性 0.8 / 活発度 1.0 (reply 87) / 新鮮度 0.6 (10時間前) ---
```

[リプライ先を開く](https://x.com/handle/status/id)

投稿者: @handle (name) | 投稿時刻: JST | ♥ like / 🔁 repost / 💬 reply

> 引用元本文(80字まで)

リプライ原稿:

` ``` `
70-100字推奨のリプライ (140字上限)
` ``` `

字数: XX/140 | 切り口: angle

---

(以降 N 件まで繰り返し)

```
💡 X Premium+ の返信ブーストはスレッド内上位表示なので、reply_count が多いポストほど恩恵が大きいです。早めに投下するほど返信序盤に乗りやすく効果的。
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
| 主要クエリのユニーク取得が 8 件未満 | **Step 2.5 (第 1 段階サブカテ 5 個)** → **Step 2.6 (第 2 段階サブカテ追加 5 個 計 10 個)** → **Step 2.7 (条件緩和)** の順にフォールバック |
| サブカテゴリ生成が JSON 不正 | プロンプトを再読込して再生成 (最大 2 回)、それでも失敗ならスキップして次の Step へ |
| 5 件取得できるが全て BLOCK | クエリ変更を促して停止 |
| スコアリング後 5 件未満 | 得られた分だけ提示、理由を明示 |
| TwitterAPI.io が `429` | 3 秒待って 1 回リトライ(search_twitterapi.py 内で対応) |
| TwitterAPI.io が `402`(クレジット不足) | **それまでに成功したクエリの結果を使って候補生成を続行する**。1 件も取得できていない場合のみ停止し、クレジットリチャージを促す。途中で 402 になった旨をユーザーに明示する |

## 注意事項

- **X Premium+ の返信ブーストを活用するには、活発な議論への参入が最重要**。reply_count が多いポストほど元ポストのインプレッションも大きく、Premium+ のスレッド内上位表示の恩恵が最大化する
- reply_count **50-200** が Premium+ ブーストの最適点。1000+ でも価値あり(0.7)、5未満は除外
- リアルタイム性は二次指標(24h 許容)。活発度を優先する
- リプライは「相手との関係構築」+「Premium+ ブースト経由の自社認知獲得」。発信モードではなく **対話モード** のトーンで、ただし密度を高く書く(上位スレッドで読まれる前提)
- 自社 SaaS を毎回出さない。5 件中 1 件程度に自然な形で言及がある、くらいが丁度いい
- 絵文字は 1 個まで、ハッシュタグは付けない(リプライでは不要)
- **早めに投下すると返信序盤に乗りやすく Premium+ ブーストが効きやすい** ため、候補表示後は速やかに採用判断を行う
