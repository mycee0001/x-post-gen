---
name: x-reply
description: X (旧Twitter) で 24 時間以内に投稿された関連性の高いポストに対して「返信 (リプライ)」の原稿を、サービスごとに 5 件ずつ生成する。カレントディレクトリの lean-canvas-{service}.md (複数可) のキートピックで TwitterAPI.io から直近 24 時間のX投稿を取得し、関連性 × 新鮮度を中心に上位 5 件をサービス別に選定する(活発度は副次指標、過剰活発な炎上ポストは減点)。各候補に対して日本語70-100字推奨(140字上限)・1リプ1メッセージのリプライ原稿を作成する(調査結果: 71-100字がエンゲージメント最高)。一度提示したポストは used_tweet_ids.jsonl に全期間で記録し、再度の対象化を防ぐ(リプライ重複の禁止)。ユーザーが「リプライ」「返信」「reply」「x-reply」「/x-reply」「コメントする」「他人のポストに返信」「ツイートに返信」「絡みに行く」と言ったら必ずこのスキルをトリガーすること。投稿自体は行わず、リプライ元URLとリプライ原稿を表示するだけ。
---

# /x-reply スキル: X 活発スレッド向けリプライ生成 (サービスごと 5 候補)

## 重要な方針

- このスキルは **リプライを投稿しない**。原稿を生成して表示するだけ
- **検索は直近 24 時間を厳守**。リアルタイム性が反応率の最重要因子。古い投稿への返信は反応が薄い
- **関連性 × 新鮮度を最優先**。活発度は副次指標で、reply_count が大きいポストはむしろ「炎上・謝罪・釈明スレッド」を拾うリスクがあるため、200 件超は減点する
- ターゲットは **24 時間以内に投稿され、自サービス文脈と高関連の発信**。reply 数は 10-49 件あたりが最適ゾーン
- **同じポストへの再リプライは禁止**。一度提示した tweet_id は `used_tweet_ids.jsonl` に **全期間で記録** し、検索時の除外リストに渡す
- 1 回の実行で **サービス数 × 5 = N 個の異なる候補ポスト + それぞれへのリプライ** を提示
- 炎上チェック **BLOCK** のリプライは除外して再生成、**WARN** は警告付きで提示
- **元ポスト自体の炎上・謝罪チェックも実施**(Step 3 のスコアリングで -0.3 ペナルティ)

## マルチキャンバスモード (重要)

カレントディレクトリの `lean-canvas-{service}.md` (複数可) を **個別のサービスとして扱い、コンテキストを厳密に分離する**。

- ファイル例: `lean-canvas-synapseize.md`、`lean-canvas-stow.md`
- 各キャンバスごとに **独立に Step 1〜9 を完走** させる(検索クエリ、tuning、サブカテゴリ、生成原稿、ブラウザ採用フロー、ID 記録)
- **コンテキスト混線禁止**: あるサービスの tuning や topic_tags を別サービスの原稿生成に使わない
- 共有してよいのは `used_tweet_ids.jsonl` のみ(同じ X ユーザーへの連投を避けるため、サービス横断で除外)

## x-quote との違い

| 観点 | /x-quote | /x-reply |
|---|---|---|
| 目的 | 引用ツイートで情報発信 | **会話に参加・対話の温度を上げる** |
| 検索期間 | 直近 72 時間 | **直近 24 時間 (厳守)** |
| min_likes | 5 以上 | **30 以上** |
| min_replies | フィルタなし | **2 以上**(極端な無反応を除外) |
| max_replies | フィルタなし | スコアで減点(200 超で炎上ペナルティ) |
| スコアリング | 関連性 × エンゲージメント | **関連性 × 新鮮度 中心、活発度は副次** |
| 履歴管理 | あり | あり(全期間の重複排除) |
| 字数 | 200 字 | **70-100 字推奨 / 140 字上限** |
| トーン | 発信・論評 | 対話・共感・追加視点 |

## 前提条件

- カレントディレクトリに `lean-canvas-{service}.md` が 1 つ以上(なければ旧 `lean-canvas.md` も可)
- `.env` に `TWITTERAPI_IO_KEY`
- `.claude/skills/_x-shared/` が配置済み

## 実行フロー

### Step 0: キャンバスを discover してサービス一覧を確定

```bash
python3 .claude/skills/_x-shared/scripts/lean_canvas_loader.py --discover --json
```

返り値は **キャンバスの配列**。各要素は `{service, path, raw_text, sections, topic_tags, content_hash}`。

- 0 件ならエラー停止 (lean-canvas-*.md / lean-canvas.md を 1 ファイル以上配置するよう促す)
- 1 件以上あれば、**サービス一覧をユーザーに表示** (例: `対象サービス: synapseize, stow`)

以降の Step 1〜9 は **サービスごとに独立に実行する**。
他サービスの canvas / tuning / 生成済み原稿を一切参照しない。

---

## 各サービスごとに以下を実行

### Step 1: そのサービスの canvas を保持

Step 0 の結果から該当 service の canvas オブジェクトを取り出して使う。
追加のファイル読み込みは不要。

### Step 1.5: tuning をサービス指定で読み込む

```bash
python3 .claude/skills/_x-shared/scripts/tuning.py load \
  --kind reply \
  --service <service> \
  --since-days 30 \
  --limit 30
```

- `--service` 指定時は **同 service のエントリ + service タグ無しの旧データ** を返す(後方互換)
- 返ってきたエントリを **必ず本実行に反映** する:

| category | 適用先 |
|---|---|
| `source` | Step 2 のクエリ構築・著者フィルタ・除外アカウントに反映 |
| `content` | Step 6 の原稿生成方針に反映 |
| `flame` | Step 7 の炎上チェック解釈に反映 |
| `other` | 自由記述を読んで Claude が判断 |

エントリ 0 件なら通常通り進める。

### Step 2: 使用済みツイート ID + 検索

`used_tweet_ids.jsonl` は **サービス横断で共有**。`--service` は付けない。
**全期間の使用済み ID を取得する**(`--hours-back` を付けない)。同じポストに二度リプライしないため、検索クエリの `--exclude-ids-json` に必ず渡すこと。

```bash
python3 .claude/skills/_x-shared/scripts/used_tweets.py load
```

そのサービスの canvas の `topic_tags` から **3 クエリ** を組み立てる。**他サービスの topic_tags を混ぜない**。

```bash
python3 .claude/skills/_x-shared/scripts/search_twitterapi.py \
  --query "<クエリ>" \
  --language ja \
  --hours-back 24 \
  --min-likes 30 \
  --min-replies 2 \
  --min-author-followers 500 \
  --max-results 25 \
  --exclude-ids-json '<除外ID JSON>'
```

3 クエリ × 25 件 ≒ 75 件、重複除去。
**`--hours-back 24` を厳守**(古い投稿は反応が薄く、リプライの ROI が下がる)。
**`--min-replies 2`** にして極端な無反応(独り言)だけを弾き、活発度自体はスコアリングで扱う。

### Step 2.5: 第 1 段階フォールバック (サブカテゴリ 5 個)

3 クエリの結果を重複除去後、ユニーク数 < 8 の場合のみ実行。

```bash
python3 .claude/skills/_x-shared/scripts/subcategory_generator.py load \
  --canvas-hash <canvas.content_hash>
```

`canvas.content_hash` はサービス固有なので、サブカテゴリも自動的にサービス別に分離される。

キャッシュ miss なら `.claude/skills/_x-shared/prompts/subcategory_generation.md` の指示通りに **当該サービスの canvas.sections と topic_tags のみを入力に** Claude が 5 個生成し保存:

```bash
python3 .claude/skills/_x-shared/scripts/subcategory_generator.py save \
  --canvas-hash <canvas.content_hash> \
  --subcategories-json '<...>'
```

各サブカテゴリのクエリで `--max-results 12` で追加検索し、Step 2 結果とマージ。
由来フラグ `origin: "subcategory"` を付け、Step 3 で関連性 × 0.7。

### Step 2.6: 第 2 段階フォールバック (サブカテゴリ追加 5 個)

Step 2.5 後も < 5 件の場合のみ。`subcategory_generation.md` の「第 2 段階」に従い追加 5 個を生成し:

```bash
python3 .claude/skills/_x-shared/scripts/subcategory_generator.py append \
  --canvas-hash <canvas.content_hash> \
  --subcategories-json '<追加 5 個>'
```

### Step 2.7: 最終手段 — 軽微な条件緩和

Step 2.5 / 2.6 後も < 5 件の場合のみ。**24h 厳守の原則は崩さない**:

1. `--min-replies 2` → `1`(独り言まで許容するが、リアクション完全ゼロではないものに留める)
2. `--min-likes 30` → `15`
3. **`--hours-back 24` は維持**(リアルタイム性は反応率の最重要因子。古い投稿に拾わない)

主要クエリ (Step 2) のみ再実行。
それでも < 5 件なら **得られた分だけ提示** し、サービスごとに「24h 以内に該当議論が立っていないため候補不足」と理由を明示する。

### Step 3: スコアリング (関連性・新鮮度中心版 + 炎上ペナルティ)

| 項目 | 重み | 計算 |
|---|---:|---|
| **関連性** | **0.40** | そのサービスの canvas の topic との一致度。`origin == "subcategory"` は最後に × 0.7 |
| **新鮮度** | **0.25** | `1.0 - (hours_since_post / 24)` を 0〜1 にクリップ。投稿直後ほど高い |
| **リーチ** | 0.20 | author_reach × engagement_velocity の加重平均 |
| **活発度** | **0.10** | reply_count ベース(下記)。副次指標 |
| **認証ボーナス** | +0.05 | `author_verified` 加算 |
| **炎上ペナルティ** | **-0.30** | 下記の炎上検出に該当した場合に減点 |
| **flame_check BLOCK** | 除外 | 元ポスト or リプライ本文がBLOCK判定なら候補から外す |

#### 活発度カーブ(炎上ゾーンを減点)

| reply_count | activity score | 解釈 |
|---:|---:|---|
| 0-1 | 0.0 | フィルタで弾かれている |
| 2-9 | **0.8** | 健全な反応、リプライしやすい |
| **10-49** | **1.0 (最適)** | 適度な議論、リプライが流されにくい |
| 50-199 | 0.6 | やや過熱気味、玉石混交 |
| 200-499 | **0.3** | 炎上接近ゾーン |
| 500+ | **0.1** | 高炎上リスク、原則避ける |

#### 炎上ペナルティ判定 (新設・必須)

候補ごとに **炎上候補フラグ** を立て、該当時はスコア合計から **-0.30** する。

判定ロジック (どれか 1 つでも該当でフラグ ON):

1. **過剰反応比**: `reply_count > 200` AND `reply_count / max(like_count, 1) > 0.5`
   (返信が like を上回る or 同水準 → 反論や批判が多い)
2. **元ポスト本文のキーワード**: 以下のいずれかを含む
   - 謝罪系: 「申し訳」「謝罪」「お詫び」「すみませんでした」
   - 訂正系: 「訂正」「誤り」「誤解を招く」「撤回」「削除しました」
   - 釈明系: 「釈明」「経緯」「説明します」「弁明」
3. **引用元 / リプ元の controversy**: 元ポストが別ポストへの reply / quote で、その親が炎上している兆候(quoted_status の reply_count が 500 超等)があれば同様にフラグ
4. **author 側の status update タイプ**: 元ポスト本文が「ご報告」「お知らせ」で始まり、reply_count > 100 → 釈明/告知系の controversy 候補

判定された候補は表示時に `[炎上候補]` ラベルを付け、なぜペナルティが付いたか理由(該当ルール)を併記する。

#### リーチ Score

```
reach = 0.6 × author_reach + 0.4 × engagement_velocity
```

- `author_reach`: 1k〜100k がピーク 1.0、1k 未満は線形減点、100k 超は対数減衰
- `engagement_velocity`: `like_count / max(hours_since_post, 0.5)` を `min(velocity / 50, 1.0)` で正規化

### Step 4: 上位 5 件を選定

- BLOCK 除外
- 同一アカウント上位 2 件まで
- 5 件未満なら得られた分だけ提示し理由を明示

### Step 5: (任意) Tavily で背景補強

デフォルトはスキップ。専門用語・数字を含むトピックの場合のみ 1 回。

### Step 6: 5 候補それぞれにリプライ原稿を生成

**必読:**
- `.claude/skills/_x-shared/prompts/reply_generation.md`
- `.claude/skills/_x-shared/prompts/japanese_writing_style.md`

**サービスを跨いだ流用禁止**: 別サービスの canvas や生成済み原稿を参考にしない。
当該サービスの canvas のみを文脈とする。

主要ルール (詳細は上記 2 ファイル):
- **完全同意スタンスの強制** — 否定・反論・相対化・上から目線・敵視メタファー禁止。許される姿勢は (1) 同方向の補強 / (2) 同方向の具体化 / (3) 同方向の展開 / (4) 建設的な深掘り質問 の 4 種類
- **冒頭でカギカッコ引用パターンを使わない**
- **自己ポジショニング明示句は連発しない** — 5 リプ中 1〜2 件、文中・文末に控えめに 1 句なら許容
- **主語は相手の論点に据える**
- **文体は丁寧体（です・ます）、一人称は「私」**
- **一行最大 50 字、理想 35 字**
- **中学生でもわかる単語**(1 リプにつき 1 個までは専門用語可)
- **使用禁止用語・強い断定禁止**
- 価値付加は **機序の指摘 / 具体例 / データ裏付け / 同方向の展開**
- 自社プロダクトの宣伝は 5 件中 0〜1 件、自然な文脈のみ

出力前に `japanese_writing_style.md` 第 8 節のチェックリストで自己点検。

### Step 6.5: 同意スタンスチェック (必須)

```bash
python3 .claude/skills/_x-shared/scripts/agreement_check.py --text "<本文>"
```

- **BLOCK** → 再生成必須(最大 2 回)、ダメなら候補差し替え
- **WARN** → 再生成して SAFE を目指す
- **SAFE** → 通過

5 件すべてが SAFE になるまでループ。

### Step 7: 各リプライに炎上チェック

```bash
python3 .claude/skills/_x-shared/scripts/flame_check.py --text "<本文>"
```

- **BLOCK** → 再生成(最大 2 回)、ダメなら差し替え
- **WARN** → 警告付きで提示

### Step 8: そのサービスの 5 候補を表示

サービスごとにセクションを切る:

```
===== [service: synapseize] X リプライ候補 N件 =====

検索クエリ: ...
取得対象: 直近 24 時間、min_likes=30, min_replies=2
```

各候補:

```
--- 候補 1 [SAFE] 関連性 0.85 / 新鮮度 0.8 (5時間前) / 活発度 1.0 (reply 22) / リーチ 0.7 ---
```

炎上ペナルティが付いた候補は次のように表示:

```
--- 候補 X [SAFE / 炎上候補:過剰反応比] 関連性 0.7 / 新鮮度 0.6 / 活発度 0.3 / ペナルティ -0.30 ---
```

[リプライ先を開く](https://x.com/handle/status/id)

投稿者: @handle (name) | 投稿時刻: JST | ♥ like / 🔁 repost / 💬 reply

> 引用元本文(80字まで)

リプライ原稿:

` ``` `
70-100字推奨のリプライ
` ``` `

字数: XX/140 | 切り口: angle

---

(以降 N 件まで繰り返し)

```
💡 24h 以内のフレッシュなポストにリプライするほど、相手の通知タイムラインに乗りやすく反応率も高いです。
   reply_count が極端に多い(200+)ポストは炎上候補のことが多いので、減点表示されます。
```

**⚠️ 必須: そのサービスの候補を表示したら、続けてブラウザ採用フローを実行する。**
**サービス間でも、現在のサービスの採用フローが完了するまで次のサービスに進まない。**

```bash
python3 .claude/skills/_x-shared/scripts/present_results.py \
  --kind reply \
  --json '<そのサービスの全候補の JSON 配列>'
```

JSON 配列の各要素:
```json
{"number": 1, "url": "...", "author": "@handle", "source_text": "...", "reply_text": "...", "flame": "SAFE"}
```

ブラウザは **サービスごとに別ウィンドウ** で開かれる(タイムアウト 10 分独立)。
戻り値: `{"adopted": [...], "skipped": [...], "feedback": [...], "auto_adopted": bool}`。

### Step 9: フィードバック保存 + 使用済み ID 記録

#### 9-a: スキップフィードバック保存 (`feedback` 非空の場合)

**`--service` 指定必須**:

```bash
python3 .claude/skills/_x-shared/scripts/tuning.py save \
  --kind reply \
  --service <service> \
  --feedback-json '<feedback>'
```

#### 9-b: 使用済みツイート ID 記録 (サービス横断共有)

```bash
python3 .claude/skills/_x-shared/scripts/used_tweets.py record \
  --skill reply \
  --tweet-ids-json '["<id1>", ..., "<id5>"]'
```

#### 9-c: 完了メッセージ (そのサービス分)

`auto_adopted: true` の場合は明示。

---

## 全サービスの完了後

最後にサービスごとの結果サマリを表示:

```
=== 全サービス完了 ===
- synapseize: 採用 N / スキップ M
- stow: 採用 N / スキップ M
```

## エラーハンドリング

| 状況 | 対応 |
|---|---|
| `lean-canvas-*.md` / `lean-canvas.md` が無い | エラー停止、配置を促す |
| `TWITTERAPI_IO_KEY` が空 | .env 設定を促して停止 |
| 主要クエリのユニーク取得が 8 件未満 | Step 2.5 → 2.6 → 2.7 の順にフォールバック |
| 5 件取得できるが全て BLOCK | そのサービスのみクエリ変更を促し、次のサービスへ進む |
| TwitterAPI.io が `429` | 3 秒待って 1 回リトライ |
| TwitterAPI.io が `402`(クレジット不足) | それまでの結果で続行。完全に 0 件かつ未着手サービスがあればそのサービスはスキップしてユーザーに明示 |

## 注意事項

- **サービス間のコンテキスト分離は厳守**。あるサービスの reply 原稿に別サービスの UVP を絶対に書かない
- **リアルタイム性が反応率の最重要因子** — 24h 厳守。古い投稿に拾わない
- **reply_count 10-49 が最適ゾーン**。50-199 は玉石混交、200+ は炎上候補として減点
- **元ポスト自体の炎上・謝罪・釈明シグナルを Step 3 で必ずチェック**(過剰反応比 / 謝罪キーワード / quote 元の controversy)
- 自社 SaaS を毎回出さない(5 件中 1 件程度)
- 絵文字 1 個まで、ハッシュタグ無し
- 5 件未満なら **得られた分だけ提示し理由を明示**(無理に 5 件揃えない)
