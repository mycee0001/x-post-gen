#!/usr/bin/env bash
#
# x-post-gen インストーラ
#
# 使い方:
#   cd /path/to/your-project
#   curl -fsSL https://raw.githubusercontent.com/mycee0001/x-post-gen/main/install.sh | bash
#
# オプション:
#   --global        ~/.claude/skills/ に配置(デフォルトはプロジェクトローカル)
#   --uninstall     アンインストール
#   --repo <url>    取得元リポジトリ(デフォルト https://github.com/mycee0001/x-post-gen.git)
#   --branch <name> 取得元ブランチ(デフォルト main)
#
set -euo pipefail

# ---- デフォルト設定 -------------------------------------------------------

REPO_URL_DEFAULT="https://github.com/mycee0001/x-post-gen.git"
BRANCH_DEFAULT="main"

MODE_GLOBAL=0
MODE_UNINSTALL=0
REPO_URL="${X_POST_GEN_REPO:-$REPO_URL_DEFAULT}"
BRANCH="${X_POST_GEN_BRANCH:-$BRANCH_DEFAULT}"

# ---- 引数パース -----------------------------------------------------------

while [[ $# -gt 0 ]]; do
  case "$1" in
    --global)
      MODE_GLOBAL=1
      shift
      ;;
    --uninstall)
      MODE_UNINSTALL=1
      shift
      ;;
    --repo)
      REPO_URL="$2"
      shift 2
      ;;
    --branch)
      BRANCH="$2"
      shift 2
      ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

# ---- インストール先の決定 --------------------------------------------------

if [[ "$MODE_GLOBAL" -eq 1 ]]; then
  TARGET_DIR="$HOME/.claude/skills"
else
  TARGET_DIR="$(pwd)/.claude/skills"
fi

INFO()  { printf "\033[1;34m[INFO]\033[0m %s\n" "$*"; }
WARN()  { printf "\033[1;33m[WARN]\033[0m %s\n" "$*"; }
ERROR() { printf "\033[1;31m[ERROR]\033[0m %s\n" "$*" >&2; }
OK()    { printf "\033[1;32m[OK]\033[0m %s\n" "$*"; }

# ---- アンインストール ----------------------------------------------------

if [[ "$MODE_UNINSTALL" -eq 1 ]]; then
  INFO "アンインストール: $TARGET_DIR 配下の x-post / x-quote / x-reply / _x-shared を削除します"
  rm -rf "$TARGET_DIR/x-post" "$TARGET_DIR/x-quote" "$TARGET_DIR/x-reply" "$TARGET_DIR/_x-shared"
  OK "アンインストール完了"
  WARN ".env と .x-history/ はそのままです。必要なら手動で削除してください"
  exit 0
fi

# ---- 依存コマンドチェック -------------------------------------------------

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    ERROR "'$1' コマンドが見つかりません。先にインストールしてください。"
    exit 1
  fi
}
need_cmd git

PYTHON_BIN=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    PYTHON_BIN="$cand"
    break
  fi
done
if [[ -z "$PYTHON_BIN" ]]; then
  ERROR "python3 が見つかりません。Python 3.10+ をインストールしてください。"
  exit 1
fi

# ---- Git リポジトリ警告(ローカルインストールのみ) ----------------------

if [[ "$MODE_GLOBAL" -eq 0 ]]; then
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    WARN "カレントディレクトリは Git リポジトリではありません(処理は続行します)"
  fi
fi

# ---- リポジトリのクローン ------------------------------------------------

TMP_DIR="$(mktemp -d -t x-post-gen-XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

INFO "リポジトリを取得: $REPO_URL ($BRANCH)"
if ! git clone --depth=1 --branch "$BRANCH" "$REPO_URL" "$TMP_DIR" >/dev/null 2>&1; then
  ERROR "git clone に失敗しました: $REPO_URL"
  exit 2
fi

# ---- ファイル配置 --------------------------------------------------------

INFO "スキルを配置: $TARGET_DIR"
mkdir -p "$TARGET_DIR"

for sub in x-post x-quote x-reply _x-shared; do
  src="$TMP_DIR/skills/$sub"
  dst="$TARGET_DIR/$sub"
  if [[ ! -d "$src" ]]; then
    ERROR "ソースに $src が無い。リポジトリ構成を確認してください"
    exit 3
  fi
  rm -rf "$dst"
  cp -R "$src" "$dst"
done
OK "スキル配置完了"

# ---- サンプル lean-canvas も _x-shared 配下に置く -----------------------

if [[ -f "$TMP_DIR/examples/lean-canvas-sample.md" ]]; then
  mkdir -p "$TARGET_DIR/_x-shared/examples"
  cp "$TMP_DIR/examples/lean-canvas-sample.md" "$TARGET_DIR/_x-shared/examples/"
fi

# ---- .env / .gitignore セットアップ(ローカルインストールのみ) ----------

if [[ "$MODE_GLOBAL" -eq 0 ]]; then
  if [[ ! -f "./.env" ]]; then
    cp "$TMP_DIR/.env.example" "./.env"
    OK ".env を作成しました。API キーを記入してください"
  else
    WARN ".env は既存。上書きしません"
  fi

  GITIGNORE_PATH="./.gitignore"
  if [[ ! -f "$GITIGNORE_PATH" ]]; then
    touch "$GITIGNORE_PATH"
  fi
  for entry in ".env" ".x-history/"; do
    if ! grep -Fxq "$entry" "$GITIGNORE_PATH"; then
      echo "$entry" >> "$GITIGNORE_PATH"
      OK ".gitignore に追加: $entry"
    fi
  done
fi

# ---- Python 依存関係のインストール ---------------------------------------

REQ_FILE="$TARGET_DIR/_x-shared/requirements.txt"
INFO "Python 依存関係をインストール: $REQ_FILE"

PIP_OK=0
if "$PYTHON_BIN" -m pip install --user -r "$REQ_FILE" >/dev/null 2>&1; then
  PIP_OK=1
fi

if [[ $PIP_OK -eq 0 ]]; then
  WARN "pip --user での標準インストールに失敗。別の方法を試します。"
  # PEP 668 (Externally Managed Environment) 対策
  if "$PYTHON_BIN" -m pip install --user --break-system-packages -r "$REQ_FILE" >/dev/null 2>&1; then
    PIP_OK=1
    WARN "--break-system-packages でインストールしました"
  fi
fi

if [[ $PIP_OK -eq 1 ]]; then
  OK "Python 依存関係インストール完了"
else
  WARN "Python 依存関係の自動インストールに失敗しました。"
  WARN "手動で以下を実行してください:"
  WARN "  $PYTHON_BIN -m pip install -r $REQ_FILE"
fi

# ---- lean-canvas.md の存在確認(ローカルインストールのみ) ---------------

if [[ "$MODE_GLOBAL" -eq 0 ]]; then
  if [[ ! -f "./lean-canvas.md" ]]; then
    WARN "lean-canvas.md が見つかりません"
    INFO "サンプルを参考に作成してください:"
    INFO "  cp $TARGET_DIR/_x-shared/examples/lean-canvas-sample.md ./lean-canvas.md"
  else
    OK "lean-canvas.md が存在します"
  fi
fi

# ---- 完了メッセージ ------------------------------------------------------

cat <<EOF

============================================================
✅ x-post-gen インストール完了
============================================================

次のステップ:

1) API キーを設定
   \$EDITOR .env
   - TWITTERAPI_IO_KEY  … https://twitterapi.io/dashboard
   - TAVILY_API_KEY     … https://app.tavily.com/home

2) lean-canvas.md を配置(まだなら)
   cp $TARGET_DIR/_x-shared/examples/lean-canvas-sample.md ./lean-canvas.md

3) Claude Code を起動し、以下のスラッシュコマンドを実行
   /x-post    — 新規ポスト 5 候補を生成
   /x-quote   — 引用ツイート 5 候補を生成
   /x-reply   — リアルタイム関連ポストへのリプライ 5 候補を生成

インストール先: $TARGET_DIR

EOF
