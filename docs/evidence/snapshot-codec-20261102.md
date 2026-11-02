# Bunsho snapshot codec candidate — 2026-11-02

This is a model-level codec experiment, not durable storage or a migration.
The proposed `BS1|` value is followed by length-prefixed UTF-8 netstrings:
title, mode, decimal block count, then kind and text for each block. It accepts
up to 32 blocks and 1024 UTF-8 bytes per title or block text; mode is `edit`
or `preview`, and kinds are `h1`, `h2`, `p` and `li`. Decode requires canonical
decimal lengths, complete UTF-8 character boundaries and consumption of the
entire input. Invalid input returns none; `snap-restore` retains the existing
state. Encoding refuses invalid model shape and out-of-bounds fields.

The codec does not interpret arbitrary EDN, does not read or write browser or
OS storage, and does not establish the format of any old-origin data. The
format is a candidate pending host integration and compatibility review.

Local experiment on macOS ARM64 with Chrome 156.0.8078.74 used the Amu
selfhost candidate in kotoba-lang/amu PR #1779, head `da321093e9557b811cce5129dacd453e300f63a3`,
compiler image SHA-256 `2c551579c06a0228029bb06bae177e93126ecbbc37d636d693c471dbac8d1536`.
Editor source SHA-256 was
`68821c04bfc2687ba6075d6c05c5264d6880cf4ffaaa98c841b64449a86b4ceb`.
Its namespace exports were narrowed to `main` for this experiment. Native
Amu and Chrome Wasm returned 17, covering the original 13 editor checks plus
four codec checks for Unicode, empty state, malformed/version/trailing input,
unchanged state on failure, 32 blocks and a 1024-byte field. A mutation that
refuses 32 blocks returned 16 on both targets. The candidate Wasm SHA-256 was
`8c9d735bc91bdba1693e81177b06f2da31c2832f4ae4799ea5297e167c65ca8f`.

Run `python3 scripts/check-snapshot-wasm.py /path/to/amu /new/output /path/to/Chrome`.
The Amu candidate is not merged at this writing. This experiment does not
qualify the original document-valued UI exports, persistence on restart,
interrupted writes, maximum aggregate payload, QEMU, migration or a release.

After combining block validation and encoding into one traversal, the same
staged native and browser checks and mutation passed again. A separate
32 × 1024-byte prebuilt fixture plus encode still exceeded the native CLI
program limit of 5 seconds. The fixture alone returned successfully; this
does not isolate codec-only execution time. Maximum-size performance remains
open.

A separate browser-program entry stages the existing editor definitions with a
`main` that accepts `init` or a state plus one click/input event, and returns
one new snapshot on the granted local output wire. `scripts/check-browser-entry.py`
compiled it with the same Amu candidate and exercised Chrome Wasm initialization,
a Unicode title edit, state handoff to a fresh Worker, corrupt or oversized
input, invalid arity/kind, and missing local-wire refusals. The staged program
SHA-256 was `9a9a3c209028835c35afd09880d72a625ec322eaf518017200312132069cb8ce`;
Wasm SHA-256 was `e23ace0b850d628bebf80924971c1c1820cb0da31fc15c0580e6c10cd53e6156`.
No durable host storage, browser DOM, external service or QEMU was involved.

A follow-up adds a `view` request: the same Kotoba editor builds the tree and
serializes nodes as length-prefixed tag, attributes, text and child-count fields.
Chrome Wasm verified the edited Unicode title in the resulting tree, preview
mode, and corrupt-state refusal. The test grants 10 million fuel for view; a
separate initial-view probe used about 840,000 of a 1 million budget. The staged
source SHA-256 was `e5890ad06534141c6a4f401edb1a66d05752621b6e5663c5b38e18fba562be8e`
and Wasm SHA-256 was `bbcb9043d7f35e47b2a5e36ef2e3636fe39b1300dc11060fb608ba0272d9e774`.
This validates the serialized tree, not a rendered browser UI or storage.

## Local browser UI candidate

A local-only build stages the program with Amu selfhost, the existing browser
Worker and the exact `kotoba-lang/wasm-webcomponent` broker revision
`e00ae75e1c589f76b4f53a88a5e3256c98c9e162` (SHA-256
`7f760128c3a58098123c31ec3dd34b9c871932e3933f2c952facc4ab0e647212`).
The product-specific adapter validates the descriptor, checks the generated
Wasm digest, decodes the Kotoba-produced view into allowlisted DOM nodes, and
stores one candidate BS1 state in origin-local localStorage. It uses Web Locks
and a stored-value check to refuse a concurrent tab's stale write; it refuses
writes when Web Locks is unavailable. This is a candidate schema, not an old
origin migration format. No server-side application logic is used.

On macOS ARM64 / Chrome 156, the loopback browser test passed initial render,
Unicode and queued input, add paragraph, preview, reload, two-tab stale-write
refusal, injected storage failure, corrupt-state refusal and mutated Wasm digest
refusal. Main-page network observations contained loopback URLs only. The
candidate Wasm and compiler hashes are recorded above; Worker SHA-256 was
`58d606d0b3f22766a1b7288fe911c106aea9606fecfe59a2adb66a4bac8923ab`.

Reproduce with `python3 scripts/build-browser.py AMU_DIR BROKER_REPO NEW_BUILD`
and `python3 scripts/check-browser-ui.py AMU_DIR NEW_BUILD NEW_OUTPUT CHROME`.
The broker is copied from the named local Git revision, not a product-local
reimplementation. The digest in the generated bundle is produced alongside
its Wasm, not an independent release attestation. Cross-browser, accessibility,
maximum-size performance, crash and interrupted-write recovery, real old data,
OS/QEMU and deployment remain unqualified. No publication is implied.
