# API コスト試算

## 前提

- `/x-post` を月 6 回実行(1 回 5 候補 × 6 回 = 月 30 ポスト相当)
- `/x-quote` を月 6 回実行(1 回 5 候補 × 6 回 = 月 30 引用相当)

## 1 回あたりのコスト内訳

### `/x-post` 1 回

| 項目 | リクエスト数 | 単価 | 金額 |
|---|---:|---:|---:|
| Perplexity Sonar Pro (調査) | 1 | ~$0.03 | $0.03 |
| Claude Code (原稿生成) | - | - | $0 (セッション内) |
| **合計** | | | **~$0.03** |

### `/x-quote` 1 回

| 項目 | リクエスト数 | 単価 | 金額 |
|---|---:|---:|---:|
| TwitterAPI.io (3 クエリ × 30 件 = 90 ツイート) | - | $0.15/1000 | $0.014 |
| Perplexity Sonar Pro (背景調査) | 1 | ~$0.03 | $0.03 |
| Claude Code (スコアリング + コメント生成) | - | - | $0 |
| **合計** | | | **~$0.044** |

## 月間コスト

| 用途 | 回数 | 単価 | 月額 |
|---|---:|---:|---:|
| `/x-post` | 6 | $0.03 | $0.18 |
| `/x-quote` | 6 | $0.044 | $0.26 |
| 予備(再生成等) | - | - | $0.20 |
| **合計** | | | **約 $0.64** |

## コストを左右する変数

- **Perplexity の `max_tokens`** — デフォルト 800。長い回答ほど料金が高い
- **TwitterAPI.io の取得ツイート数** — `--max-results` と `--min-likes`
- **リトライ回数** — レート制限・5xx で Perplexity を叩き直すと倍に
- **バリエーション数を増やす** — `X_POST_VARIANTS=10` にしても Perplexity は 1 回なので増えない(Claude Code の推論時間が増える)

## 節約のコツ

- `--recency month` で直近 1 ヶ月に絞る(不要な広範囲検索を避ける)
- `--mfg-preset` 等のドメインフィルタで信頼できる情報源だけ検索
- 履歴で同じトピックを 30 日連続でリサーチしない(自動でトピック変更される)
- 生成失敗を減らすため、`flame_rules.yaml` の BLOCK ルールは厳しくしすぎない

## 参考ドキュメント

- Perplexity Sonar pricing: https://docs.perplexity.ai/guides/pricing
- TwitterAPI.io pricing: https://docs.twitterapi.io/pricing
