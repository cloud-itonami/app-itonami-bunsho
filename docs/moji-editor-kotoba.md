# itonami Bunsho（文書）— Kotoba 製の文書エディタ

状態: 最初のスライス（2026-10-31、Linear JUN-703、親 JUN-702）。正本はこの文書。

## 何があるか

| 層 | 実体 | 状態 |
|---|---|---|
| エディタ本体 | `src/moji/editor.kotoba`。`init` / `view` / `step` の app 契約（`kotoba-lang/amu` の `runtime/dom-driver.mjs` が動かす形、`examples/todo-app.kotoba` と同じ） | **実装済み** |
| 判定コア | `aiueos/docs_index.kotoba`（`.cljk` から改名。中身は 1 バイトも変えていないので、`docs_index.wasm` の provenance の source-sha256 はそのまま一致する） | 既存 |
| 自己チェック | エディタ内の `test-*` 13 本と、その合計を返す `main` | **実装済み・実測** |
| ネイティブ実行 | `scripts/check-editor-native.sh` | **実測: 13/13** |
| ブラウザ用ビルド | — | **blocker**（下記） |

## 文書モデルと操作

- 文書はブロックの並び。ブロックの種類は `"h1"`（見出し1）、`"h2"`（見出し2）、`"p"`（本文）、`"li"`（箇条書き）。`kotoba-lang/docs` の見出し・段落・リストに当たる。
- 操作: タイトル入力、ブロックの追加（4 種）・本文入力・種類の変更・上下移動・削除、編集とプレビューの切り替え。
- 各ブロックに Google Docs の body index（`[startIndex–endIndex]`）を表示する。計算は判定コアの `span-end` / `next-start` と同じ定義で、body は 1 から始まり、ブロック間に改行 1 つぶんを数える。
- 状態は pure な `:document`。保存（localStorage など）はホストの仕事で、client-runtime の local-state `itonami.moji.state.v1` に置く。エディタ自身は何の capability も使わない。

## 実測（2026-10-31）

```sh
scripts/check-editor-native.sh <kotoba-lang/amu>/bin/amu
# ok: 13/13 checks pass
```

- ネイティブの公開 CLI は、export が `main [] :i64` 1 つだけのソースしか受け付けない。そのためスクリプトは、`(:export [...])` を `[main]` に絞った写しを実行する。定義のバイトは変えない。
- 負の対照: `next-start` を `(+ start len 2)` に壊すと `FAIL: 10/13`。
- full-root コンパイラ（`seed/bootstrap/aarch64-macos/amu-full-root.macho check`）でも `ok`。

## 未実装境界・既知の制約

- **ブラウザ用ビルドがない（blocker）。** app 契約の module を出力できるのは今、nbb の `--target js-browser` だけで、nbb はビルド経路に置けない。ネイティブの `wasm32-browser` は `:document` を E7101 で拒否し、export も `:i64` しか許さない。ネイティブの ES モジュール経路と app entry の設計は、amu の ADR 0397（Linear JUN-706）。
- **ブロックは 32 個まで**（`:document` の vector は 32 要素が上限）。
- **index はバイト数。** 長さは UTF-8 のバイト数（`string-byte-length`）で数える。Google Docs は UTF-16 のコード単位で数えるので、一致するのは ASCII のときだけ。
- **種類とモードは keyword ではなく文字列。** ネイティブ CLI では、`:document` から keyword を取り出す `document-keyword-value` でプログラムがセグフォルトする（exit 139、JUN-706 に最小の再現を記録）。
- 未着手: インライン書式・表・コメント・提案、.docx の import / export（`kotoba-lang/office` の意味論）、Google Docs / Microsoft Graph との連携（broker 経由・操作ごとの同意）、kotoba datomic への同期。
- `appview/docs-performers-r5ycqp6x/cljs/` の仮画面は、ブラウザ用ビルドができるまで残す。
