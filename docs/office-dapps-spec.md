# Itonami office dapps: common design

Status: **design proposal, 2026-11-02**. This document specifies the intended
shape and acceptance evidence for Bunsho, Hyokeisan and Zuhyo; it is not a
claim that the apps, OS integration, storage migration or release are ready.
Tracking: [JUN-702](https://linear.app/kotobalabs/issue/JUN-702),
[JUN-763](https://linear.app/kotobalabs/issue/JUN-763).

| App | Job | Source repository | Target human-readable entry |
| --- | --- | --- | --- |
| Bunsho | Documents | [app-itonami-bunsho](https://github.com/cloud-itonami/app-itonami-bunsho) | `bunsho.itonami.app` |
| Hyokeisan | Spreadsheets | [app-itonami-hyokeisan](https://github.com/cloud-itonami/app-itonami-hyokeisan) | `hyokeisan.itonami.app` |
| Zuhyo | Presentations | [app-itonami-zuhyo](https://github.com/cloud-itonami/app-itonami-zuhyo) | `zuhyo.itonami.app` |

The URLs above are targets, not evidence of availability. The primary app
identity is content-addressed; the HTTPS name is an auxiliary entry. Static
hosting distributes verified artifacts only. It does not execute per-user app
logic, inference, state, transformation, queues or request-time handlers.

## Shared application and host boundary

1. Each app owns a Kotoba model, editing operations, validation and declarative
   UI state/interaction logic. Use the corresponding `kotoba-lang/docs`,
   `sheets` and `slides` data semantics where implemented. The model decides
   transitions; adapters render UI, deliver user input and provide persistence.
2. Amu selfhost compiles the same app source for the selected execution host.
   The browser target is Wasm running in a user-side Worker; the browser host
   supplies input, rendering and storage adapters. Browser integration glue is
   a host boundary, not an alternate implementation of application decisions.
   JVM, nbb and kbb are not build, packaging, CI or fallback paths.
3. Itonami OS installs verified app artifacts locally and provides the same
   application semantics through its own UI, storage and capability host.
   QEMU is a way to test that OS, not a separate application platform. The
   current OS user target and browser Wasm target have different ABIs: using
   the **same Kotoba source** may require separate artifacts. Running identical
   Wasm bytes on both requires a compatible OS Wasm runtime and host ABI;
   neither byte identity nor such support is established here.
4. Define a versioned event/state/UI boundary with explicit bounds and error
   results before binding each host. The same fixture trace must produce the
   same model, visible UI state and save payload in both hosts. No host may
   silently substitute remote execution when a local capability is missing.

## App slices

- **Bunsho:** local document creation, paragraph/heading/list editing,
  preview, save and reopen. Index semantics and Unicode units must be explicit;
  the current core counts UTF-8 bytes, which is not Google Docs' UTF-16 index.
- **Hyokeisan:** a local workbook with cell entry, explicit formula subset,
  recalculation, save and reopen. The current 4×4 integer grid and experimental
  snapshot value are bounded prototypes, not a workbook or durable format.
- **Zuhyo:** create a deck, edit slide text and shapes, reorder, present, save
  and reopen. Existing CLJS appview is a placeholder, not the presentation UI.

Each slice must state its bounds, unsupported operations and data format.
OOXML and Google/Microsoft interoperability are later work; do not claim
compatibility until import/export and independent fixtures have been tested.

## Local storage and migration

The model produces a validated, versioned state payload; each host implements
local storage through its declared local-state adapter. The durable byte
encoding, schema IDs, maximum sizes, transaction semantics and upgrade rules
are **not yet settled**. The experimental grid snapshot is not that contract.
A save must either commit a complete valid new version or preserve the previous
valid version; report failures instead of claiming success. Test reopen after
normal restart, interruption at each write boundary, corruption, unsupported
versions and full storage. Do not overwrite an existing document on a failed
or ambiguous import.

Browser storage is scoped by origin. An old origin's local data cannot be read
silently by the new origin. First establish whether old state exists and its
actual format. If it does, provide an explicit user-initiated export at the old
origin and validated import at the new one, with a preview/confirmation and a
recoverable copy; never infer a migration format from a schema label alone.
For OS, verify the equivalent migration and cold/crash restore using the actual
installed volume. Browser data and OS data are not assumed to synchronize.

## External operations and consent

Initial offline slices declare zero external operations. For a later external
identity, storage, federation, import/export, payment, artifact or inference
operation, use the shared `kotoba.app.client-runtime.v1` descriptor and the
canonical `kotoba-lang/wasm-webcomponent/src/kotoba-client-runtime.js`
validator and operation broker. The app must declare the service, endpoint,
method/path or bounded routes, allowed query parameters, data categories and
`each-operation` consent; the host starts with no approvals and rejects
undeclared operations and app-origin APIs. Show the concrete operation and
endpoint immediately before a trusted user choice; denial sends no request.
Redirects are rejected by default and only the shared broker's narrowly
bounded GET/HEAD rules may permit them. Browser operations with hidden effects
also need explicit declarations and fresh consent. No product-local copy may
replace the shared validation or approval semantics.

Verify the canonical module and its exact builder integration, pin immutable
source revisions and verify available artifact digests before execution.
If a digest or reviewed integration is missing, mark qualification open.
Itonami OS needs an equivalent host capability boundary and differential tests
against the canonical semantics; an app, bot or native permission prompt must
not manufacture or reuse approval for another operation.

## Release and evidence gates

1. Native selfhost build and meaningful positive and negative tests for each
   model and UI slice; no prohibited hosted fallback.
2. Browser: exact artifact and digest, Worker startup with no network,
   create/edit/save/reload, invalid and interrupted-save cases, accessibility
   and real browser interaction; test declared operation denial separately.
3. Itonami OS under QEMU: install/admit the verified artifact, launch from the
   app catalog, execute the same fixture trace, save, cold restart and recover
   after interrupted writes. Qualify physical hardware separately. The QEMU
   result is not evidence of real-device behavior.
4. Test old-origin export/new-origin import only after the actual old data and
   available route are established; include refusal and rollback evidence.
5. Verify fleet signer trust, scoped record reconciliation and signed-head
   admission. Do not absorb unrelated fleet drift or treat a valid signature as
   proof that its signer is trusted.
6. Build immutable artifacts, record source/toolchain revisions and digests,
   verify the content-addressed distribution path and auxiliary DNS/TLS route,
   and prepare rollback. Account for the owner's Cloudflare-independent
   delivery direction; [JUN-324](https://linear.app/kotobalabs/issue/JUN-324)
   remains relevant. No production route cutover until compatibility and
   release evidence are complete and separately approved.

## Observed status and open work

As of the local checks on 2026-11-02, Bunsho's scalar index tests ran in Chrome
Wasm; its document-valued editor did not compile for the browser target.
Hyokeisan's experimental grid/snapshot tests ran in Chrome Wasm; the same
source was refused by the `x86_64-aiueos-user-v1` compiler. Zuhyo has a
placeholder rather than a qualified editor. These experiments are in open draft
PRs and are not released behavior. The six old/new HTTPS host probes returned
522 at that observation time; the cause was not established by that probe.

Open work includes the browser app ABI/document runtime
([JUN-353](https://linear.app/kotobalabs/issue/JUN-353),
[JUN-706](https://linear.app/kotobalabs/issue/JUN-706)), the three app slices
([JUN-703](https://linear.app/kotobalabs/issue/JUN-703),
[JUN-704](https://linear.app/kotobalabs/issue/JUN-704),
[JUN-705](https://linear.app/kotobalabs/issue/JUN-705)), OS app lifecycle and
persistence ([AWAI-120](https://linear.app/kotobalabs/issue/AWAI-120)), and
fleet trust rotation ([JUN-351](https://linear.app/kotobalabs/issue/JUN-351)).
The previously stated claim that Amu had no wasm32-browser target is stale:
scalar programs compile, while the full editor's ABI/runtime remains blocked.
