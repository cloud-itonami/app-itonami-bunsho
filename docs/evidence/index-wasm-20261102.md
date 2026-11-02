# Bunsho index: selfhost Wasm experiment, 2026-11-02

The existing `aiueos/docs_index.kotoba` index rules and six tests were staged
without changing their definitions. The staging changes the namespace header
and replaces `main` with a test aggregator because the current browser program
ABI exports `main [] :i64`. The source SHA-256 was
`45929366ea0159439431b02f06861bbcb27477d132dbe3c124f6c1f4321f2550`.

Amu commit `d4d6841f129d846db13393a469645e1ca91fb568`, macOS ARM64
`seed/bootstrap/aarch64-macos/amu-full-root.macho` SHA-256
`f5d36c21efff28c8fdc1125832c99607ee0f09d0ec1db1290213d72f77d43b5b`
compiled the staged source to wasm32-browser. Chrome 156.0.8078.74 ran it in
the Amu Worker harness with no granted wires and returned `:status :ok :result 0`
(all six tests passed). The Wasm SHA-256 was
`ff104380d247b28fa6f851641acd7a73d75961a7039175492fe55c5f3c8ec5f5`.
The negative control changed the newline increment from 1 to 2; the compiled
module returned `:result 1`, so the test aggregator detected the mutation.
No network service or user data was used.

Reproduce on macOS ARM64 using a clean checkout of the pinned Amu revision:

```sh
python3 scripts/check-index-wasm.py /path/to/amu /new/output/directory /path/to/Chrome
```

This is a test of the scalar index core, not the editor, UI, local persistence,
compatibility migration, a release artifact, or production readiness. The
browser host is Amu's existing Worker harness. The document-valued editor's
`init`/`view`/`step` exports are not compiled by this experiment.
