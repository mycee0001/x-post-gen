# API コスト試算

## 前提

- `/x-post` を月 6 回実行(1 回 5 候補 × 6 回 = 月 30 ポスト相当)
- `/x-quote` を月 6 回実行(1 回 5 候補 × 6 回 = 月 30 引用相当)
- `/x-reply` を月 10 回実行(1 回 5 候補 × 10 回 = 月 50 リプライ候補相当)
- **Tavily は月 1,000 リクエストまで無料枠**(2026-04 時点)

## 1 回あたりのコスト内訳

### `/x-post` 1 回

| 項目 | リクエスト数 | 単価 | 金額 |
|---|---:|---:|---:|
| Tavily (Advanced search) | 1 | 無料枠内 | $0.00 |
| Claude Code (原稿生成) | - | - | $0 (セッション内) |
| **合計** | | | **$0.00** |

### `/x-quote` 1 回

| 項目 | リクエスト数 | 単価 | 金額 |
|---|---:|---:|---:|
| TwitterAPI.io (3 クエリ × 30 件 = 90 ツイート) | - | $0.15/1000 | $0.014 |
| Tavily (Advanced search 背景調査) | 1 | 無料枠内 | $0.00 |
| Claude Code (スコアリング + コメント生成) | - | - | $0 |
| **合計** | | | **$0.014** |

### `/x-reply` 1 回

| 項目 | リクエスト数 | 単価 | 金額 |
|---|---:|---:|---:|
| TwitterAPI.io (3 クエリ × 20 件 = 60 ツイート) | - | $0.15/1000 | $0.009 |
| Tavily | 0 (原則スキップ) | - | $0.00 |
| Claude Code (スコアリング + リプライ生成) | - | - | $0 |
| **合計** | | | **$0.009** |

## 月間コスト(無料枠内運用時)

| 用途 | 回数 | 単価 | 月額 |
|---|---:|---:|---:|
| `/x-post` | 6 | $0.00 | $0.00 |
| `/x-quote` | 6 | $0.014 | $0.08 |
| `/x-reply` | 10 | $0.009 | $0.09 |
| **合計** | | | **約 $0.17** |

月 12 リクエスト程度なら Tavily の無料枠(1,000 req/月)に余裕で収まり、
実質的に TwitterAPI.io の料金($0.17/月)のみとなります。

## 有料枠に突入した場合

Tavily の課金プラン(2026-04 時点):
- Researcher プラン: $30/月 で 4,000 credits
- 1 credit あたり約 $0.0075
- Advanced search = 2 credits/req = 約 $0.016/req
- Basic search = 1 credit/req = 約 $0.008/req

仮に月 100 実行(Advanced search)に増やしても $1.6 程度。

## Tavily の料金体系メモ

| プラン | 月額 | credits | コメント |
|---|---:|---:|---|
| Free | $0 | 1,000 req/月 | 本ツールの想定利用には十分 |
| Researcher | $30 | 4,000 credits | 月 2,000 回 Advanced 検索相当 |
| Pro | $100 | 15,000 credits | 大規模運用向け |

参考: https://www.tavily.com/#pricing

## コストを左右する変数

- **Tavily の `search_depth`** — `basic`(1 credit) vs `advanced`(2 credits)
- **Tavily の `include_answer`** — 有効時は追加 credit 消費の可能性(プランによる)
- **Tavily の `max_results`** — デフォルト 8。増やしても credit は変わらないが、レスポンスが長くなる
- **TwitterAPI.io の取得ツイート数** — `--max-results` と `--min-likes`
- **リトライ回数** — レート制限・5xx で Tavily を叩き直すと credit が倍消費される
- **バリエーション数を増やす** — `X_POST_VARIANTS=10` にしても検索 API 呼び出しは 1 回のまま(Claude Code の推論時間は増える)

## 節約のコツ

- `time_range=month` で直近 1 ヶ月に絞る(無駄な広範囲検索を避ける)
- `--mfg-preset` 等のドメインフィルタで信頼できる情報源だけ検索
- 履歴で同じトピックを 30 日連続でリサーチしない(自動でトピック変更される)
- 生成失敗を減らすため、`flame_rules.yaml` の BLOCK ルールは厳しくしすぎない
- 必要なら `search_depth=basic` で credit 消費を半減

## 参考ドキュメント

- Tavily docs: https://docs.tavily.com
- Tavily pricing: https://www.tavily.com/#pricing
- TwitterAPI.io pricing: https://docs.twitterapi.io/pricing
