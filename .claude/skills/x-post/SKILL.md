---
name: x-post
description: X (旧Twitter) ビジネスアカウント用の新規ポスト原稿を、サービスごとに 5 件ずつ生成する。カレントディレクトリの lean-canvas-{service}.md (複数可) を参照し、Tavily Search で関連ニュース・論文を調査した上で、日本語280字以内のポスト原稿を「5つの異なる切り口」でサービス別にまとめて生成する。過去の投稿履歴 (.x-history/posts.jsonl) と service 別に重複しないトピック・切り口を自動選択し、炎上チェックを通してから出力する。ユーザーが「ポスト」「ツイート」「X投稿」「Twitter投稿」「x-post」「/x-post」「SaaSのPR」と言ったら必ずこのスキルをトリガーすること。投稿自体は行わず、サービス別 5 候補をコピー可能な形で表示し、採用番号をユーザーに確認してから履歴に追記する。
---

# /x-post スキル: X 新規ポスト生成 (サービスごと 5 候補)

## 重要な方針

- このスキルは **ポストを投稿しない**。原稿を生成して表示するだけ
- 1 回の実行で **サービス数 × 5 = N 個の異なる切り口のポスト案** を提示する
- 履歴への書き込みは **ユーザーが採用番号を選んだ後**(その書き込み自体はユーザー許可不要)
- 炎上チェック **BLOCK** のポストは除外して再生成
- 炎上チェック **WARN** は警告マーク付きで提示

## マルチキャンバスモード (重要)

カレントディレクトリの `lean-canvas-{service}.md` (複数可) を **個別のサービスとして扱い、コンテキストを厳密に分離する**。

- 各キャンバスごとに **独立に Step 1〜9 を完走**
- **コンテキスト混線禁止**: あるサービスの canvas / Tavily 結果 / 履歴を別サービスのポストに使わない
- ポスト本文に他サービスの UVP / 機能名 / プロダクト名を絶対に書かない

## 前提条件

- カレントディレクトリに `lean-canvas-{service}.md` が 1 つ以上
- `.env` に `TAVILY_API_KEY` が設定されていること
- `.claude/skills/_x-shared/` 配下のスクリプト・プロンプト・ルールが存在すること

## 実行フロー

### Step 0: キャンバスを discover してサービス一覧を確定

```bash
python3 .claude/skills/_x-shared/scripts/lean_canvas_loader.py --discover --json
```

返り値配列の各要素は `{service, path, raw_text, sections, topic_tags, content_hash}`。

ファイルが 0 件の場合は以下を出して停止:
> `lean-canvas-{service}.md` または `lean-canvas.md` がカレントディレクトリに見つかりません。最低 1 ファイル配置してください。

ユーザーに対象サービスを表示。
以降の Step 1〜9 は **サービスごとに独立に実行する**。

---

## 各サービスごとに以下を実行

### Step 1: そのサービスの canvas を保持

Step 0 の結果から service の canvas を取り出す。

### Step 2: 履歴をサービス指定で読み込み、低頻度トピックを提案

```bash
python3 .claude/skills/_x-shared/scripts/history.py load \
  --kind post \
  --service <service> \
  --since-days 30
python3 .claude/skills/_x-shared/scripts/deduplicator.py suggest-topics \
  --canvas-topics-json '<そのサービスの topic_tags JSON>' \
  --history-json '<そのサービスの履歴 JSON>' \
  --top-n 5
```

返ってきたトピックの中から、今回そのサービスで取り上げる **1 トピック** を選ぶ(先頭を採用して良い)。
ユーザーにも表示: 「[service: <service>] 今回のトピック: 〇〇」

### Step 3: Tavily Search でトピック関連情報を調査

そのサービスのトピックに関連するクエリを 1〜2 個組み立てる。

```bash
python3 .claude/skills/_x-shared/scripts/search_tavily.py \
  --query '<クエリ>' \
  --recency month
```

(製造業向けの場合は `--mfg-preset` を併用)

citations と answer をそのサービスのポスト生成材料に使う。**他サービスの調査結果と混ぜない**。

### Step 4: 5 つの切り口でポスト案を生成

**必読:**
- `.claude/skills/_x-shared/prompts/post_generation.md`
- `.claude/skills/_x-shared/prompts/japanese_writing_style.md`

**サービスを跨いだ流用禁止**: そのサービスの canvas のみを文脈とし、本文に他サービスの名前・機能を書かない。

主要ルール (詳細は上記 2 ファイル):
- **文体は常体（だ・である調）をベース**。段落単位で統一
- **一人称は「私」**
- **一行最大 50 字、理想 35 字**
- **中学生でもわかる単語**。専門用語は説明を添える
- **使用禁止用語・強い断定禁止**
- 数字を引用するときは必ず出典 URL を添える

生成時の入力:
- そのサービスの canvas の関連セクション (PROBLEM / UVP / SOLUTION / UNFAIR ADVANTAGE)
- 選ばれたトピック
- そのサービスの Tavily リサーチ結果
- そのサービスの過去 30 日の投稿履歴サマリ

5 ポストは **切り口を明確に変える**:
1. 一次情報ベース / データ起点
2. 現場視点 / 具体シーン
3. 経営視点 / ROI
4. 技術トレンド視点
5. 示唆・問いかけ

### Step 5: 各ポストに炎上チェック

```bash
python3 .claude/skills/_x-shared/scripts/flame_check.py \
  --text '<ポスト本文>' \
  --context-json '{"sources": [...]}'
```

- **BLOCK** → 別の切り口で再生成(最大 2 回)
- **WARN** → `⚠️ WARN: <理由>` を付けて提示
- **SAFE** → 通常提示

### Step 6: 各ポストに重複チェック (サービス内のみ)

```bash
python3 .claude/skills/_x-shared/scripts/deduplicator.py check-post \
  --entry-json '<entry JSON>' \
  --history-json '<そのサービスの履歴>'
```

`is_duplicate=true` のポストは `♻️ 重複: <理由>` を付けて提示(除外はしない)。

### Step 7: そのサービスの 5 候補を表示

```
===== [service: <service>] X ポスト候補 5件 =====

トピック: <選ばれたトピック>
リサーチ: <Tavily answer の要約 1-2 文>
主な出典:
  - <URL1>
  - <URL2>
```

各候補:

```
--- 候補 1 (切り口: 一次情報ベース) [SAFE] ---
```

` ``` `
ポスト本文1
` ``` `

字数: XX/280 | 出典: URL

---

(以降 5 件まで繰り返し)

**⚠️ 必須: そのサービスの候補を表示したら、続けてブラウザ採用フローを実行する。次のサービスに進む前に必ず完了させる。**

```bash
python3 .claude/skills/_x-shared/scripts/present_results.py \
  --kind post \
  --json '<そのサービスの全候補の JSON 配列>'
```

JSON 配列の各要素:
```json
{"number": 1, "text": "ポスト本文", "angle": "一次情報ベース", "flame": "SAFE"}
```

ブラウザはサービスごとに別ウィンドウ。
戻り値: `{"adopted": [1, 3, 5], "skipped": [2, 4]}`

### Step 8: 採用ポストを履歴に追記 (サービスタグ必須)

エントリスキーマ:

```json
{
  "id": "post_YYYYMMDD_HHMMSS_N",
  "created_at": "ISO8601 JST",
  "service": "<service>",
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

```bash
python3 .claude/skills/_x-shared/scripts/history.py append \
  --kind post \
  --data-json '<entry JSON>'
```

`simhash` は `deduplicator.py simhash --text "..."` で取得。
採用した件数だけループで append。

### Step 9: 完了メッセージ (そのサービス分)

```
✅ [service: <service>] 採用 N 件を .x-history/posts.jsonl に記録しました
⚠️ 未採用: M 件
```

---

## 全サービスの完了後

サービスごとのサマリを表示:

```
=== 全サービス完了 ===
- synapseize: 採用 N / 未採用 M
- stow: 採用 N / 未採用 M

X への投稿は手動で行ってください。
```

## エラーハンドリング

| 状況 | 対応 |
|---|---|
| `lean-canvas-*.md` / `lean-canvas.md` が無い | エラー停止 |
| `TAVILY_API_KEY` が空 | `.env` 設定を促して停止 |
| Tavily が失敗(API 障害) | エラー内容を伝え、リサーチなしで生成するか聞く(該当サービスのみ) |
| あるサービスで 5 件生成しても BLOCK ばかり | そのサービスのみトピック変更を提案、他サービスは続行 |
| 履歴 append が失敗 | 原稿はユーザーに表示済みなので、ファイル書き込みエラーを明示 |

## 注意事項

- **サービス間のコンテキスト分離は厳守**。あるサービスのポスト本文に別サービスの機能・UVP・プロダクト名を絶対に書かない
- Tavily API の失敗時でも、まったく返さないのではなく「リサーチなしで出すか」確認
- 字数 280 超過のポストは自動的に削り、コメントで注記
- 数字(統計・割合)を含むのに出典 URL がない場合は炎上チェックで WARN が出る
