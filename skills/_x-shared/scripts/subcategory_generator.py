"""lean-canvas のサブカテゴリ生成のためのキャッシュ管理スクリプト。

役割:
- `.x-history/subcategories.json` に canvas_hash 単位でサブカテゴリ JSON を保存
- 取得 (`load`) / 保存 (`save`) / 削除 (`clear`) の 3 操作のみ
- サブカテゴリ自体の生成は Claude 側のプロンプト
  (`_x-shared/prompts/subcategory_generation.md`) が担当する

データ形式:
{
  "<canvas_hash>": {
    "generated_at": "ISO8601 JST",
    "canvas_hash": "<sha1>",
    "subcategories": [
      {
        "name": "ものづくり補助金",
        "axis": "隣接領域",
        "queries": ["ものづくり補助金 OR IT導入補助金"],
        "rationale": "..."
      },
      ...
    ]
  }
}

エラーは標準エラー出力に明示し、フォールバックしない。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from .utils import ensure_history_dir, now_jst_iso
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from utils import ensure_history_dir, now_jst_iso  # type: ignore

CACHE_FILE = "subcategories.json"


def _cache_path(history_dir: str = "./.x-history") -> Path:
    return ensure_history_dir(history_dir) / CACHE_FILE


def _read_all(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise RuntimeError(f"サブカテゴリキャッシュの読み込みに失敗: {e}") from e
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"サブカテゴリキャッシュ {path} が壊れています (JSON エラー: {e})。"
            f"手動で削除するか修正してください。"
        ) from e
    if not isinstance(data, dict):
        raise RuntimeError(
            f"サブカテゴリキャッシュ {path} のトップレベルが dict ではありません。"
        )
    return data


def _write_all(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load(canvas_hash: str, history_dir: str = "./.x-history") -> dict[str, Any] | None:
    """canvas_hash に紐づくキャッシュエントリを返す。無ければ None。"""
    if not canvas_hash:
        raise ValueError("canvas_hash が空です")
    path = _cache_path(history_dir)
    data = _read_all(path)
    entry = data.get(canvas_hash)
    if entry is None:
        return None
    if not isinstance(entry, dict):
        raise RuntimeError(
            f"canvas_hash={canvas_hash} のキャッシュエントリが dict ではありません"
        )
    return entry


def _validate_subcategories(subcategories: list[Any]) -> None:
    if not isinstance(subcategories, list) or not subcategories:
        raise ValueError("subcategories は非空のリストである必要があります")
    for i, sc in enumerate(subcategories):
        if not isinstance(sc, dict):
            raise ValueError(f"subcategories[{i}] が dict ではありません")
        for required in ("name", "axis", "queries"):
            if required not in sc:
                raise ValueError(
                    f"subcategories[{i}] に必須フィールド '{required}' がありません"
                )
        queries = sc.get("queries")
        if not isinstance(queries, list) or not queries:
            raise ValueError(
                f"subcategories[{i}].queries は非空のリストである必要があります"
            )


def save(
    canvas_hash: str,
    subcategories: list[dict[str, Any]],
    history_dir: str = "./.x-history",
) -> dict[str, Any]:
    """サブカテゴリを保存する。同じ canvas_hash のエントリは上書き。"""
    if not canvas_hash:
        raise ValueError("canvas_hash が空です")
    _validate_subcategories(subcategories)

    path = _cache_path(history_dir)
    data = _read_all(path)
    entry = {
        "generated_at": now_jst_iso(),
        "canvas_hash": canvas_hash,
        "subcategories": subcategories,
    }
    data[canvas_hash] = entry
    _write_all(path, data)
    return entry


def append(
    canvas_hash: str,
    subcategories: list[dict[str, Any]],
    history_dir: str = "./.x-history",
) -> dict[str, Any]:
    """既存エントリにサブカテゴリを追加する。重複 name はスキップ。

    第 2 段階フォールバックで「既存 3 個 + 追加 3 個 = 計 6 個」にするための操作。
    既存エントリが無い場合は新規作成と同じ動作。
    """
    if not canvas_hash:
        raise ValueError("canvas_hash が空です")
    _validate_subcategories(subcategories)

    path = _cache_path(history_dir)
    data = _read_all(path)
    existing = data.get(canvas_hash)

    if existing is None:
        merged = list(subcategories)
    else:
        if not isinstance(existing, dict):
            raise RuntimeError(
                f"canvas_hash={canvas_hash} の既存エントリが dict ではありません"
            )
        existing_subs = existing.get("subcategories")
        if not isinstance(existing_subs, list):
            existing_subs = []
        seen_names = {sc.get("name") for sc in existing_subs if isinstance(sc, dict)}
        merged = list(existing_subs)
        for sc in subcategories:
            if sc.get("name") in seen_names:
                continue
            merged.append(sc)
            seen_names.add(sc.get("name"))

    entry = {
        "generated_at": now_jst_iso(),
        "canvas_hash": canvas_hash,
        "subcategories": merged,
    }
    data[canvas_hash] = entry
    _write_all(path, data)
    return entry


def clear(canvas_hash: str | None, history_dir: str = "./.x-history") -> int:
    """canvas_hash 指定なら 1 件削除、None なら全削除。削除件数を返す。"""
    path = _cache_path(history_dir)
    if not path.exists():
        return 0
    data = _read_all(path)
    if canvas_hash is None:
        n = len(data)
        _write_all(path, {})
        return n
    if canvas_hash in data:
        del data[canvas_hash]
        _write_all(path, data)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="lean-canvas サブカテゴリのキャッシュ管理"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_load = sub.add_parser("load", help="canvas_hash に紐づくキャッシュを取得")
    p_load.add_argument("--canvas-hash", required=True)
    p_load.add_argument("--history-dir", default="./.x-history")

    p_save = sub.add_parser("save", help="サブカテゴリを保存 (上書き)")
    p_save.add_argument("--canvas-hash", required=True)
    p_save.add_argument(
        "--subcategories-json",
        required=True,
        help='[{"name":"...","axis":"...","queries":["..."],"rationale":"..."}, ...]',
    )
    p_save.add_argument("--history-dir", default="./.x-history")

    p_append = sub.add_parser(
        "append",
        help="既存エントリにサブカテゴリを追加 (第 2 段階フォールバック用)",
    )
    p_append.add_argument("--canvas-hash", required=True)
    p_append.add_argument(
        "--subcategories-json",
        required=True,
        help='追加する 3 個のサブカテゴリ JSON 配列',
    )
    p_append.add_argument("--history-dir", default="./.x-history")

    p_clear = sub.add_parser("clear", help="キャッシュを削除")
    p_clear.add_argument("--canvas-hash", help="省略すると全削除")
    p_clear.add_argument("--history-dir", default="./.x-history")

    args = parser.parse_args()

    try:
        if args.cmd == "load":
            entry = load(args.canvas_hash, args.history_dir)
            if entry is None:
                print(json.dumps({"hit": False}, ensure_ascii=False))
                return 0
            print(
                json.dumps(
                    {"hit": True, "entry": entry},
                    ensure_ascii=False,
                )
            )
            return 0

        if args.cmd == "save":
            try:
                subcategories = json.loads(args.subcategories_json)
            except json.JSONDecodeError as e:
                print(
                    f"ERROR: --subcategories-json が JSON ではない: {e}",
                    file=sys.stderr,
                )
                return 2
            entry = save(args.canvas_hash, subcategories, args.history_dir)
            print(
                json.dumps(
                    {"ok": True, "saved_count": len(entry["subcategories"])},
                    ensure_ascii=False,
                )
            )
            return 0

        if args.cmd == "append":
            try:
                subcategories = json.loads(args.subcategories_json)
            except json.JSONDecodeError as e:
                print(
                    f"ERROR: --subcategories-json が JSON ではない: {e}",
                    file=sys.stderr,
                )
                return 2
            entry = append(args.canvas_hash, subcategories, args.history_dir)
            print(
                json.dumps(
                    {"ok": True, "total_count": len(entry["subcategories"])},
                    ensure_ascii=False,
                )
            )
            return 0

        if args.cmd == "clear":
            removed = clear(args.canvas_hash, args.history_dir)
            print(
                json.dumps({"ok": True, "removed": removed}, ensure_ascii=False)
            )
            return 0
    except (ValueError, RuntimeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    return 2


if __name__ == "__main__":
    sys.exit(main())
