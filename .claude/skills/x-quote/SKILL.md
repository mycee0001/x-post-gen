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

### Step 1.5: プロジェクトローカルな調整ロジック (tuning) を読み込む

過去にユーザーがスキップした候補のフィードバックを読み込み、本実行で適用する:

```bash
python3 .claude/skills/_x-shared/scripts/tuning.py load --kind quote --since-days 30 --limit 30
```

返ってきたエントリを **必ず本実行に反映** する:

| category | 適用先 |
|---|---|
| `source` | Step 3 のクエリ構築・著者フィルタ・除外アカウントに反映(同種のポストを拾わないようクエリ調整 / 著者ハンドルを除外) |
| `content` | Step 6 のコメント原稿生成方針に反映(指摘されたトーン/切り口/自己言及度を回避) |
| `flame` | Step 7 の炎上チェック解釈に反映(誤検知ならその種の WARN を許容、見逃しなら追加で再生成) |
| `other` | 自由記述を読んで Claude が判断 |

**重要:** このチューニングは `.x-history/tuning.jsonl` に保存されており、プロジェクト固有。
別プロジェクト(別の cwd)では別のチューニングが効く設計。

エントリ 0 件なら通常通り進める。

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

#### 引用元として適切なポストの定義

x-quote は **x-reply とは選定基準が根本的に違う**。引用ツイートは **引用元の投稿者に話しかけるためではなく、引用元と同じ問題を抱えている広いオーディエンスに刺さる発信を作るための踏み台** として使う。

**引用元として適切なポスト (狙うべき):**
- **観察・原則・パターンの提示** — 「ADHDの〇〇は△△である」「□□が起きるのは××だから」のような汎化された言明
- **データ・ニュース・調査・研究** — 一次情報や統計を含むポスト
- **問いかけ・呼びかけ** — 「皆さんはどうですか」「この特徴当てはまる？」のような巻き込み型
- **業界トレンド・社会論評** — 個人の出来事ではなく現象や構造を語っているもの
- **共感されやすい認知パターンの言語化** — 「これあるある」と多数が頷ける普遍的描写
- → 抽象化・具体化・事例適用・パターン応用で **広いオーディエンスに刺さるコメント** が組み立てられる

**引用元として不適切なポスト (避けるべき):**
- **個人的なつぶやき・愚痴・日記** — 「今日疲れた」「眠い」「〇〇行ってきた」のような私的状況
- **ピンポイントな相談・SOS** — 1対1で返す方が自然なポスト (これは x-reply の領分)
- **私生活・身体・精神状態の生々しい描写** — 引用すると当人がさらされる構図になりやすい
- **身内ネタ・界隈内の自虐・自己定義スレッド** — 文脈共有者にしか伝わらない、引用すると場が冷める
- **強い政治的・宗教的主張** — 引用すると派閥色がつく
- **炎上リスクが高いポスト** — 軽口・差別的暗示・センシティブ話題

クエリ構築時は **「観察・原則・データ・問いかけ・パターン」を含むポストが引っかかる語彙** を優先する。例: 「と思う」「あるある」「コツ」「特徴」「理由」「研究」「調査」「データ」「みなさん」など。

**バズっているポストを狙うのも引き続き正解** だが、バズっている=私生活実況のケースもあるので、エンゲージメントだけで選ばず Step 5 の `引用元適性` で必ず再評価する。

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
| **関連性** | 0.20 | lean-canvas.md のキートピックとの一致度 (0-1)。**`origin == "subcategory"` の候補は最後に × 0.7** |
| **引用元適性** (新規) | 0.30 | 下記参照。**個人的すぎ/相談型は強く減点、観察・原則・データ・問いかけ・パターン型は加点** |
| **リーチ** | 0.30 | 下記 3 サブシグナルの加重平均 |
| **炎上リスク(負)** | 0.10 | 本文を flame_check にかけて BLOCK=-1, WARN=-0.5, SAFE=0 |
| **重複ペナルティ(負)** | 0.10 | 過去 30 日に同じアカウントを引用済みなら -1、同一 tweet_id は -∞ |

BLOCK のツイートは除外。**引用元適性 < 0.4 の候補も除外** (たとえ関連性・リーチが高くても、x-reply の領分なので x-quote では使わない)。Top 5 を選ぶ。

#### 引用元適性 Score の計算 (新規)

ポスト本文の性質を 0〜1 で判定する。Step 3 の「引用元として適切なポストの定義」と整合させる。Claude が引用元本文を読んで以下のシグナルで採点:

| サブシグナル | スコアへの寄与 |
|---|---|
| **観察・原則・パターン提示** (「〇〇は△△である」「□□の理由は」) | +0.4 |
| **データ・調査・研究の引用・要約** | +0.3 |
| **問いかけ・呼びかけ・大喜利型** (「皆さんはどうですか」) | +0.2 |
| **業界トレンド・社会論評** (現象を構造化) | +0.2 |
| **多数が頷ける普遍的な認知描写** (「あるある」型で広い共感を呼ぶ) | +0.2 |
| **私生活実況・愚痴・日記** (「今日」「私が」「眠い」「疲れた」「行ってきた」) | -0.4 |
| **個人相談・SOS** (「教えてください」「助けて」「どうしたら」) | -0.3 |
| **身内ネタ・界隈自虐・自己定義スレッド** | -0.4 |
| **私生活・身体・精神状態の生々しい描写** (引用で当人がさらされる) | -0.5 |
| **強い政治的・宗教的主張** | -0.4 |

加点と減点を合算し、0〜1 にクリップ。**0.4 未満は候補から除外** (x-reply 向きと判定されたものは x-quote では扱わない)。

#### リーチ Score の計算

```
reach = 0.45 × author_reach
      + 0.35 × engagement_velocity
      + 0.20 × conversation_activity
```

- `author_reach`: フォロワー数を**ベル型** (1k〜50k がピーク 1.0)。1k 未満は線形減点、50k 超は対数減衰 (大物アカは引用が埋もれる)
- `engagement_velocity`: `like_count / max(hours_since_post, 0.5)` を `min(velocity / 30, 1.0)` で正規化 (1 時間あたり 30 like で 1.0、引用は速度の閾値を reply より高めに)
- `conversation_activity`: `reply_count` が 5〜30 で 1.0、0 で 0.3、50+ で 0.5

※ 認証済み (`author_verified`) の候補は最後に **+0.05** ボーナス (アルゴリズムブースト考慮)。

### Step 6: 5 候補それぞれにコメント原稿を生成

**必読:** 以下の 2 ファイルを **必ず両方読み込んだうえで** 5 件分の原稿を作る。
- `.claude/skills/_x-shared/prompts/quote_generation.md` (引用ツイート固有のルール)
- `.claude/skills/_x-shared/prompts/japanese_writing_style.md` (日本語ベストプラクティス・全 X 系共通)

主要ルール（詳細は上記 2 ファイル参照）:
- **冒頭でカギカッコ引用パターンを使わない**（「『〇〇』、〜ですね。」のような書き出しは禁止）。元ポストの語句に触れるのは、自分の主張がその語句に明確に紐づくときのみ、自分の文に自然に織り込む
- **文体は丁寧体（です・ます）、一人称は「私」**
- **一行最大 50 字、理想 35 字** で改行を入れる
- **中学生でもわかる単語** に置き換える。専門用語・略語は説明を添える
- **使用禁止用語**（略式侮蔑語・レッテル・差別用語・性的侮辱）を一切使わない
- **強い断定**（絶対・必ず・100%・唯一）を使わない

出力前に `japanese_writing_style.md` 第 7 節のチェックリストで自己点検すること。

#### 重要: コメントの宛先は「引用元の投稿者」ではなく「同じ問題を抱えている広いオーディエンス」

x-reply は引用元投稿者との対話を作るのが目的だが、x-quote は **引用元を踏み台にして、同じ問題を抱えている広いユーザーに刺さる発信を作る** のが目的。コメント原稿の宛先と書き方を以下のように切り替える:

| 観点 | x-reply (NG) | x-quote (OK) |
|---|---|---|
| **誰に話しかけているか** | 投稿者本人(「〇〇さん、その視点」) | 引用元と同じ問題を抱えている読み手(「これ、当事者なら全員ぶつかる構造で」) |
| **トーン** | 対話・共感・追加視点 | 観察の言語化・パターンの一般化・刺さる事例化 |
| **引用元の扱い** | 起点として共感する対象 | 抽象化/具体化/事例化の**素材** |
| **得たいリアクション** | 投稿者からのリプ返し・関係構築 | 同じ問題を抱える第三者からの「これ刺さる」「分かる」 |

**コメント生成のコア発想:**
- 引用元を読んだ第三者が「自分のことだ」「これ刺さる」と感じる文章にする
- 引用元の主張を **抽象化**(より広い原理に持ち上げる) または **具体化**(自分の事例で裏付ける) または **パターン適用**(別領域に応用する) のいずれかで展開
- 投稿者個人へのコメント(「〇〇さんすごい」「ありがとうございます」)は **使わない**
- 自分の専門性(ADHD向けプロダクト開発者であること)は、押し付けではなく「同じ問題に取り組んでいる側からの観察」として自然に織り込む

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

**出力フォーマット（CLI 操作性重視）:**

各候補は以下の構造で出力する。ポイント:
- **引用元 URL** はマークダウンリンク `[引用元を開く](URL)` で表示 → CLI 上でクリックして X に遷移可能
- **コメント原稿** は独立したコードブロック（` ``` `）で表示 → CLI 上のコピーボタンでクリップボードにコピー可能
- 各候補の間は `---` で区切る

```
===== X 引用ツイート候補 N件 =====

検索クエリ: <使用したクエリ>
背景調査: <Tavily answer の要約 1 文>
```

各候補:

```
--- 候補 1 [SAFE] スコア 0.82 ---
```

[引用元を開く](https://x.com/handle/status/id)

投稿者: @handle (name) | ♥ like / 🔁 repost

> 引用元本文(80字まで)

コメント原稿:

` ``` `
200 字以内のコメント
` ``` `

字数: XX/200 | 切り口: angle

---

(以降 N 件まで繰り返し)

**⚠️ 必須: 候補を表示したら、必ず以下のブラウザ採用フローを実行すること。**
**他のスキルの実行や別の話題に移る前に、必ずこのフローを完了させること。**

候補表示の直後に、`present_results.py` でブラウザを開き、ユーザーに採用/不採用を判断してもらう:

```bash
python3 .claude/skills/_x-shared/scripts/present_results.py \
  --kind quote \
  --json '<全候補の JSON 配列>'
```

JSON 配列の各要素:
```json
{"number": 1, "url": "https://x.com/...", "author": "@handle", "source_text": "引用元80字", "comment_text": "コメント本文", "flame": "SAFE"}
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

### Step 10: フィードバック保存 + 履歴に追記 + 使用済みツイート ID を記録

#### 10-a: スキップフィードバックの保存 (`feedback` が非空の場合のみ)

ブラウザから返ってきた `feedback` 配列を tuning に保存:

```bash
python3 .claude/skills/_x-shared/scripts/tuning.py save \
  --kind quote \
  --feedback-json '<feedback 配列の JSON>'
```

これは次回 `/x-quote` 実行時の Step 1.5 で読み込まれ、ロジック調整に使われる。

#### 10-b: 採用エントリを quotes.jsonl に追記

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
| TwitterAPI.io が `402`(クレジット不足) | **それまでに成功したクエリの結果を使って候補生成を続行する**。1 件も取得できていない場合のみ停止し、クレジットリチャージを促す。途中で 402 になった旨をユーザーに明示する |

## 注意事項

- 同じアカウントを 2 回以上引用しない(多様性確保)
- 引用元本文を全文表示しない(抜粋 80 字程度)
- スコア内訳をユーザーに見せると納得感が上がるので、できれば簡潔に
- API 障害時はすぐに中断せず、「別の方法で続けるか」を提案する
