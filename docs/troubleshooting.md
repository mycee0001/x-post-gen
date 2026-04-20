# トラブルシューティング

## インストール

### `git clone に失敗しました`

- ネットワーク接続を確認
- `git` が入っているか: `git --version`
- プライベートリポジトリの場合は `--repo git@github.com:...` で SSH 経由を指定

### `pip install` が失敗する

PEP 668 (Externally Managed Environment) の影響です。以下を試してください:

```bash
# 方法 1: venv で隔離
python3 -m venv .venv
source .venv/bin/activate
pip install -r .claude/skills/_x-shared/requirements.txt

# 方法 2: pipx でインストール対象を増やす
pipx install simhash pyyaml requests python-dotenv openai

# 方法 3: --break-system-packages (installer が自動で試行)
python3 -m pip install --user --break-system-packages \
  -r .claude/skills/_x-shared/requirements.txt
```

## 実行時

### `lean-canvas.md が見つかりません`

```bash
cp .claude/skills/_x-shared/examples/lean-canvas-sample.md ./lean-canvas.md
$EDITOR ./lean-canvas.md
```

### `PERPLEXITY_API_KEY が設定されていません`

```bash
echo 'PERPLEXITY_API_KEY=pplx-xxxx' >> .env
# .env が .gitignore 済みであることを確認
grep -q '^\.env$' .gitignore || echo '.env' >> .gitignore
```

### `TWITTERAPI_IO_KEY が設定されていません`

Perplexity と同様、`.env` に追記してください。
`/x-post` のみ使う場合は TwitterAPI.io キーは不要です。

### Perplexity API が `401` で失敗

- キーが空 or 誤り
- キーの前後の空白を含めていないか確認
- `https://www.perplexity.ai/settings/api` でキーを再発行

### TwitterAPI.io が `429 Rate Limit`

- スクリプト内で 3 秒待機 + 1 回リトライ
- それでも失敗する場合は `--max-results` を減らすか時間をおいて再実行

### 候補がすべて BLOCK になる

炎上ルールが厳しすぎる可能性:

```bash
# ルールファイルを編集
$EDITOR .claude/skills/_x-shared/rules/flame_rules.yaml
```

- BLOCK の keyword で過剰に広い語(例: `老害` のような語)が、無関係な議論文脈で発火している場合、文脈条件を足すか WARN に格下げ
- `customer_names` ルールはフィクション例でも発火しやすい

### 履歴が重複扱いされる

`X_HISTORY_SIMHASH_THRESHOLD` を上げる(例: 4 → 8)と重複判定が緩くなります。

```bash
echo 'X_HISTORY_SIMHASH_THRESHOLD=8' >> .env
```

逆に、似た内容が量産されて困る場合は 2〜3 に下げてください。

## Claude Code

### `/x-post` / `/x-quote` が発火しない

- `.claude/skills/x-post/SKILL.md` が存在するか確認
- Claude Code を再起動
- グローバルインストールなら `~/.claude/skills/` に配置されているはず

### スクリプトの標準出力がおかしい

Claude Code の bash ツールは標準出力を UTF-8 で受け取ります。
日本語が化ける場合は環境変数を設定:

```bash
export LANG=ja_JP.UTF-8
export LC_ALL=ja_JP.UTF-8
```

## 履歴ファイル

### `.x-history/` を別の場所に置きたい

`history.py` / `deduplicator.py` は `--history-dir` 引数をサポートしています。
SKILL.md を編集して渡す引数を変えてください。

### 履歴をリセットしたい

```bash
# バックアップを取ってから
mv .x-history .x-history.bak
```

次回実行時に自動で作り直されます。

## その他

### コストが想定より高い

`docs/api-costs.md` の「コストを左右する変数」セクションを参照。
Perplexity の `max_tokens` や TwitterAPI.io の `--max-results` を見直すと減ります。

### 投稿後の効果測定をしたい

本ツールはスコープ外です。X Analytics を別途ご利用ください。
将来的に連携を検討していますが、現状は手動運用前提です。
