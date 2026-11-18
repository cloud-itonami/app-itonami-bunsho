#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 4 ]]; then
  echo "Usage: $0 OFFICE_REPO BROWSER_BUILD KOTOBA_REPO NEW_OUTPUT" >&2
  exit 2
fi

root=$(cd -- "$(dirname -- "$0")/.." && pwd)
pin=$(cat "$root/android/office-host.rev")
mkdir -p "$root/.agent-output"
host=$(mktemp -d "$root/.agent-output/office-host.XXXXXX")
git -C "$1" archive "$pin" android-host | tar -xf - -C "$host"

tooling="$host/android-host"
node "$tooling/check-ui.mjs"
npm --prefix "$tooling/vendor/awai-ui" ci
npm --prefix "$tooling/vendor/awai-ui" run build
node "$tooling/prepare.mjs" bunsho "$2" "$3" "$4"
