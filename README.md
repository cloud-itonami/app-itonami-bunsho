# Itonami Bunsho（文書）

Bunsho is the planned Itonami document dapp. Its model and UI are intended to
be written in Kotoba, built with Amu selfhost and run locally in the user's
browser or Itonami OS. The browser target is Wasm; QEMU is used to qualify the
OS host. Neither a complete browser editor nor OS execution is released yet.

The [shared office dapps design](docs/office-dapps-spec.md) covers Bunsho,
Hyokeisan and Zuhyo, their host boundaries, local state, migration, consent and
release gates. [JUN-703](https://linear.app/kotobalabs/issue/JUN-703) tracks the
Bunsho implementation; [JUN-763](https://linear.app/kotobalabs/issue/JUN-763)
tracks the rename and release preparation.

The existing index Wasm experiment is documented in
[its evidence](docs/evidence/index-wasm-20261102.md); it is not an editor or
persistence qualification. The candidate `bunsho.itonami.app` is not a claim
of an available or deployed service.
