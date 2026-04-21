---
name: x-post
description: X (旧Twitter) ビジネスアカウント用の新規ポスト原稿を生成する。カレントディレクトリの lean-canvas.md を参照し、Tavily Search で関連ニュース・論文を調査した上で、日本語280字以内のポスト原稿を「5つの異なる切り口」でまとめて生成する。過去の投稿履歴 (.x-history/posts.jsonl) と重複しないトピック・切り口を自動選択し、炎上チェックを通してから出力する。ユーザーが「ポスト」「ツイート」「X投稿」「Twitter投稿」「x-post」「/x-post」「SaaSのPR」「unkryptのX運用」と言ったら必ずこのスキルをトリガーすること。投稿自体は行わず、5候補をコピー可能な形で表示し、採用番号をユーザーに確認してから履歴に追記する。
---

# /x-post スキル: X 新規ポスト生成 (5候補)

## 重要な方針

- このスキルは **ポストを投稿しない**。原稿を生成して表示するだけ
- 1 回の実行で **5 つの異なる切り口のポスト案** を提示する
- 履歴への書き込みは **ユーザーが採用番号を選んだ後** に行う(その書き込み自体はユーザー許可不要)
- 炎上チェック **BLOCK** のポストは除外して再生成(ユーザーには提示しない)
- 炎上チェック **WARN** のポストは警告マーク付きで提示し、最終判断はユーザーに委ねる

## 前提条件

- カレントディレクトリに `lean-canvas.md` が存在すること
- `.env` に `TAVILY_API_KEY` が設定されていること
- `.claude/skills/_x-shared/` 配下のスクリプト・プロンプト・ルールが存在すること

## 実行フロー

### Step 1: lean-canvas.md を読み込む

```bash
python3 .claude/skills/_x-shared/scripts/lean_canvas_loader.py --path ./lean-canvas.md --json
```

- ファイルが無い場合は以下のメッセージを出して停止:
  > `lean-canvas.md` が見つかりません。カレントディレクトリにキャンバスを配置してください。サンプルは `.claude/skills/_x-shared/examples/lean-canvas-sample.md` にあります。

### Step 2: 履歴を読み込み、低頻度トピックを提案

```bash
python3 .claude/skills/_x-shared/scripts/history.py load --kind post --since-days 30
python3 .claude/skills/_x-shared/scripts/deduplicator.py suggest-topics \
  --canvas-topics-json '<topic_tags JSON>' \
  --history-json '<history JSON>' \
  --top-n 5
```

- 返ってきたトピックの中から、**今回取り上げる 1 トピック** を選ぶ(先頭を採用して良い)
- そのトピックをユーザーにも表示: 「今回のトピック: 〇〇」

### Step 3: Tavily Search でトピック関連情報を調査

選ばれたトピックに関連するクエリを 1〜2 個組み立てる。例:

- `{topic} 2025 日本 製造業 最新動向`
- `{topic} 論文 研究 学術`

```bash
python3 .claude/skills/_x-shared/scripts/search_tavily.py \
  --query '<クエリ>' \
  --mfg-preset \
  --recency month
```

- `--mfg-preset` は製造業向け推奨ドメインフィルタを使う
- citations と answer をまとめてポスト生成の材料にする

### Step 4: 5 つの切り口でポスト案を生成

`.claude/skills/_x-shared/prompts/post_generation.md` のプロンプトテンプレートに従い、**Claude 自身** が 5 バリエーションを生成する。

生成時の入力:
- lean-canvas.md の関連セクション (PROBLEM / UVP / SOLUTION / UNFAIR ADVANTAGE)
- 選ばれたトピック
- Tavily のリサーチ結果 (answer + citations)
- 過去 30 日の投稿履歴サマリ(どんな切り口が使われたか)

5 ポストは **切り口を明確に変える**:
1. 一次情報ベース / データ起点
2. 現場視点 / 具体シーン
3. 経営視点 / ROI
4. 技術トレンド視点
5. 示唆・問いかけ

### Step 5: 各ポストに炎上チェックをかける

5 件それぞれに対して:

```bash
python3 .claude/skills/_x-shared/scripts/flame_check.py \
  --text '<ポスト本文>' \
  --context-json '{"sources": [...]}'
```

- **BLOCK** が返ってきたら、そのポストを除外し、別の切り口で再生成する(最大 2 回まで)
- **WARN** の場合は `⚠️ WARN: <理由>` を付けて提示
- **SAFE** は通常提示

### Step 6: 各ポストに重複チェックをかける

各ポストの新規エントリ(text + topic_tags + simhash)を作り:

```bash
python3 .claude/skills/_x-shared/scripts/deduplicator.py check-post \
  --entry-json '<entry JSON>' \
  --history-json '<history JSON>'
```

- `is_duplicate=true` のポストは `♻️ 重複: <理由>` を付けて提示(除外はしない)

### Step 7: 5 候補を番号付きで表示

以下のフォーマットで出力する:

```
===== X ポスト候補 5件 =====

トピック: <選ばれたトピック>
リサーチ: <Tavily answer の要約 1-2 文>
主な出典:
  - <URL1>
  - <URL2>

--- 候補 1 (切り口: 一次情報ベース) [SAFE] ---
\`\`\`
<ポスト本文1>
\`\`\`
字数: XX/280
出典: <URL>

--- 候補 2 (切り口: 現場視点) [WARN: 強い断定あり] ---
\`\`\`
<ポスト本文2>
\`\`\`
...

(以下 5 件まで)

===========================
```

**⚠️ 必須: 候補を表示したら、必ず以下の採用確認を行うこと。**
**他のスキルの実行や別の話題に移る前に、必ずこの確認を完了させること。**

候補表示の直後に、`AskUserQuestion` ツールを使って以下の質問をユーザーに投げかける:

> 採用する候補番号を教えてください（複数可: "1,3" / 全部採用: "all" / 破棄: "none"）

- ユーザーが回答するまで **次のステップに進まない**
- ユーザーが別の話題やスキルを実行しようとした場合でも、まずこの採用確認を完了させる
- 回答を受け取ったら即座に Step 8 に進む

### Step 8: ユーザーの採用指示を受けて履歴に追記

ユーザーが「1,3」「all」「none」等を回答したら、それに応じて履歴追記:

```bash
python3 .claude/skills/_x-shared/scripts/history.py append \
  --kind post \
  --data-json '<entry JSON>'
```

エントリのスキーマ:

```json
{
  "id": "post_YYYYMMDD_HHMMSS_N",
  "created_at": "ISO8601 JST",
  "topic_tags": ["..."],
  "angle": "切り口の説明",
  "sources": [{"url": "...", "title": "..."}],
  "text": "本文",
  "char_count": 123,
  "simhash": "hex",
  "flame_score": "SAFE|WARN",
  "flame_warnings": [],
  "canvas_hash": "<content_hash>"
}
```

- `simhash` は `deduplicator.py simhash --text "..."` で取得
- 採用した件数だけループで append する

### Step 9: 完了メッセージ

```
✅ 採用: N件を .x-history/posts.jsonl に記録しました
⚠️ 未採用: M件(履歴には残しません)

X への投稿は手動で行ってください。上記コードブロックをコピーしてご使用ください。
```

## エラーハンドリング

| 状況 | 対応 |
|---|---|
| `lean-canvas.md` が無い | 上記のエラーメッセージを出して停止 |
| `TAVILY_API_KEY` が空 | `.env` 設定を促して停止 |
| Tavily が失敗(API 障害) | エラー内容をユーザーに伝え、リサーチなしで生成するか聞く |
| 5 件生成しても BLOCK ばかりで提示できない | トピック変更を提案 |
| 履歴 append が失敗 | 原稿はユーザーに表示済みなので、ファイル書き込みエラーを明示 |

## 注意事項

- Tavily API の失敗時でも、**ユーザーに原稿をまったく返さない** のではなく、「リサーチなしで出しますか?」と確認すること
- 字数 280 超過のポストは自動的に削り、コメントで注記する
- 数字(統計・割合)を含むのに出典 URL がない場合は炎上チェックで WARN が出る。その場合は citations から適切な URL を挿入するか、数字を外す
