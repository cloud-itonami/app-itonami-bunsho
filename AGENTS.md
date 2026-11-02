# itonami Bunsho（文書） — 旧 etzhayyim-project-docs — Google Docs v1 + Microsoft Graph (Word) compatible document API

> 2026-10-31（JUN-700）: Cloudflare Worker の edge facade は退役した。ブラウザ側は静的配信（`appview/README.md`）。
> 下の edge 構成図とホストは旧構成の記録で、itonami.app 上には存在しない。

**moji.itonami.app** — a documents API whose external surface is shaped like **both** Google Docs v1
(structural) and Microsoft Graph Word access (content-based), over **one** canonical store on
**kotoba datomic** (graph `docs-v1`). Fourth/final build vertical of the workspace-compat program.

SSoT: `90-docs/adr/2606010500-workspace-compat-datomic-schema.md`

## 一行定義

Docs ≝ CanonicalDocument[:doc/*, bodyJson] × KotobaDatomic[docs-v1] × {GoogleSkin[/v1/documents, structural], MicrosoftSkin[/v1.0/me/drive/.../content, plaintext]}

## アーキテクチャ

```
Google SDK  → moji.itonami.app/v1/documents/{id}:batchUpdate (structural)  ┐
MS Graph SDK→ moji.itonami.app/v1.0/me/drive/items/{id}/content (plaintext) ┘
  CF Worker docs-compat (50-infra/cloudflare/workers/docs-compat)
   ├─ /xrpc/app.itonami.moji.*  → pod (actor-worker passthrough)
   └─ provider REST → canonical XRPC → pod → reshape to provider JSON
  lg-docs pod (lg, FastAPI server.py)
   → kotoba datomic transact/q/pull on graph docs-v1 (:doc/* namespace)
```

## Canonical XRPC methods (app.itonami.moji.*)

| method | Google Docs v1 | Microsoft Graph (Word) |
|---|---|---|
| `documentsGet` | documents.get | GET …/items/{id} + …/content |
| `documentsCreate` | documents.create | POST /me/drive/root/children |
| `documentsBatchUpdate` | documents.batchUpdate | PUT …/content (plaintext replace) |

**Asymmetry (honest):** Microsoft has **no GA structural Docs API** — Word docs are accessed as
DriveItems + file content. So the **Google skin is structural** (`batchUpdate` over a
structural-element body); the **MS skin is content-based** (flattened plaintext GET, plaintext PUT
replaces the body). One canonical store bridges them: a doc authored via Google structural ops is
downloadable as plaintext via MS `/content`, and a plaintext PUT is readable structurally via Google.

## Storage model (ADR D5)
One document = one datomic entity (`:doc/*`); body = ordered structural elements in `:doc/bodyJson`
(`{elementId, kind, headingLevel?, text}`). `lg_docs/docbody.py` is the **batchUpdate index engine**:
global character indices (text + 1 newline per element), ops insertText/deleteRange (cross-element
merge)/replaceText/insertHeading/appendParagraph; `startIndex/endIndex` computed on read.
`:doc/revisionId` (`rev-N`) is the writeControl/ETag token.

## ファイル構成
```
lg-clj/  (canonical — langgraph-clj port, ADR-2606280030)
└── src/lg_docs/{server,handlers,store,mapping,docbody,kotoba_datomic,edn,ids,graph}.cljc
tests/lg_docs/*_test.cljc     # clojure.test (23 tests / 54 assertions)
(edge) 50-infra/cloudflare/workers/docs-compat/  # Google + MS skins (10 tests)
(infra) 50-infra/vultr/lg-docs-pool/             # Helm (mirror lg-sheets-pool)
```

The DEV-stage Python appview (`lg/`: Dockerfile + pyproject.toml + langgraph.json +
`lg_docs/*.py`) was **deleted** once the `lg-clj/` twin was verified (ADR-2606280030,
founder directive "twin の py を削除", 2026-06-28); `lg-clj/` is now the canonical code.

## Test
```bash
cd lg-clj && kbb run_tests.cljk
cd 50-infra/cloudflare/workers/docs-compat && node --test test/*.test.ts
```
