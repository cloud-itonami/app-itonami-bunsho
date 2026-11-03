#!/usr/bin/env python3
"""Check provisional BS2 legacy snapshot in native and browser Wasm.

Usage: python3 scripts/check-legacy-snapshot.py AMU_DIR OUTPUT_DIR CHROME
Synthetic fixtures only. Not integrated into browser storage or migration UI.
"""
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

amu, out, chrome = map(lambda s: Path(s).resolve(), sys.argv[1:])
out.mkdir(parents=True, exist_ok=False)
root = Path(__file__).resolve().parents[1]
files = [root / 'src/moji/editor.kotoba', root / 'src/moji/json_string.kotoba',
         root / 'src/moji/json_parse.kotoba', root / 'src/moji/legacy_document.kotoba',
         root / 'src/moji/legacy_snapshot.kotoba', root / 'tests/legacy-snapshot-cases.kotoba']
editor, string, parser, legacy, snapshot, fixture = [p.read_text(encoding='utf-8') for p in files]
editor, a = re.subn(r'^\(ns\s+moji\.editor[\s\S]*?\(:export \[[^\]]*\]\)\)', '(ns legacy-test (:export [main]))', editor, count=1)
anchor = '(defn main [] :i64\n  (+ (test-index-core)'
if a != 1 or editor.count(anchor) != 1:
    raise SystemExit('editor namespace or entry changed')
editor = editor[:editor.index(anchor)]
string, a = re.subn(r'^\(ns\s+moji\.json-string\s*\(:export \[json-unquote\]\)\)', '', string, count=1)
parser, b = re.subn(r'^\(ns\s+moji\.json-parse\s*\(:export \[json-parse json-object-field json-array-item json-array-tokens\]\)\s*\(:require \[moji\.json-string :as js\]\)\)', '', parser, count=1)
legacy, c = re.subn(r'^\(ns\s+moji\.legacy-document\s*\(:export \[legacy-convert\]\)\s*\(:require \[moji\.json-string :as js\]\s*\[moji\.json-parse :as json\]\)\)', '', legacy, count=1)
snapshot, d = re.subn(r'^\(ns\s+moji\.legacy-snapshot\s*\(:export \[legacy-snapshot-encode legacy-snapshot-decode\]\)\s*\(:require \[moji\.legacy-document :as legacy\]\)\)', '', snapshot, count=1)
if (a, b, c, d) != (1, 1, 1, 1):
    raise SystemExit('unexpected migration module namespace')
parser = parser.replace('(js/json-unquote ', '(json-unquote ')
legacy = legacy.replace('(js/json-unquote ', '(json-unquote ').replace('(json/json-', '(json-')
snapshot = snapshot.replace('(legacy/legacy-convert ', '(legacy-convert ')
mutation = '(not (ls-has-id v ident 0 i))'
if snapshot.count(mutation) != 1:
    raise SystemExit('mutation anchor changed')
spec = importlib.util.spec_from_file_location('mac', amu / 'scripts/seed/check-aiueos-user-macos-native.py')
mac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mac)
results = {}
for name, code, expected in [('snapshot', snapshot, 12), ('duplicate-mutant', snapshot.replace(mutation, '(= 0 0)'), 11)]:
    source = out / (name + '.kotoba')
    source.write_text('\n'.join([editor, string, parser, legacy, code, fixture]), encoding='utf-8')
    native = subprocess.run([str(amu / 'bin/amu'), 'run', str(source)], cwd=out,
                            capture_output=True, text=True, timeout=120, check=True)
    if native.stdout.strip() != str(expected):
        raise SystemExit(name + ': native result ' + repr(native.stdout))
    mac.native_run(amu / 'seed/bootstrap/aarch64-macos/amu-full-root.macho', out,
                   'compile', source.name, '--target', 'wasm32-browser', '--output', name + '.wasm')
    dest = out / (name + '-browser')
    subprocess.run([sys.executable, str(amu / 'scripts/seed/check-wasm32-browser.py'),
                    '--browser', str(chrome), '--app', str(out / (name + '.wasm')),
                    '--output', str(dest)], check=True)
    report = json.loads((dest / 'app.json').read_text(encoding='utf-8'))['report']
    if not re.search(rf'\{{:status :ok :result {expected}(?:\s|\}})', report):
        raise SystemExit(name + ': browser report ' + report)
    results[name] = {'result': expected, 'wasmSha256': hashlib.sha256((out / (name + '.wasm')).read_bytes()).hexdigest()}
(out / 'receipt.json').write_text(json.dumps({'inputSha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    'results': results}, indent=2) + '\n')
print('PASS_LEGACY_SNAPSHOT native and synthetic browser, including duplicate-element mutant')
