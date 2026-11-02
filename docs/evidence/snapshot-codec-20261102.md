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
`e8c1b03ea391f42a2006f8a45b923e8a0861545c8b13257bcd72b3e2b99175c0`.
Its namespace exports were narrowed to `main` for this experiment. Native
Amu and Chrome Wasm returned 17, covering the original 13 editor checks plus
four codec checks for Unicode, empty state, malformed/version/trailing input,
unchanged state on failure, 32 blocks and a 1024-byte field. A mutation that
refuses 32 blocks returned 16 on both targets. The candidate Wasm SHA-256 was
`943cac0bf73d0c04fa6584d3b3d3190d0e67b1e0cbe1b65d10f99317e8195a82`.

Run `python3 scripts/check-snapshot-wasm.py /path/to/amu /new/output /path/to/Chrome`.
The Amu candidate is not merged at this writing. This experiment does not
qualify the original document-valued UI exports, persistence on restart,
interrupted writes, maximum aggregate payload, QEMU, migration or a release.
