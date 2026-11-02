#!/usr/bin/env python3
"""Exercise the bounded Kotoba JSON validator using native and browser Wasm.

Usage: python3 scripts/check-json-parse.py AMU_DIR OUTPUT_DIR CHROME
Synthetic fixtures only; this does not import or migrate legacy documents.
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
string_source = (root / 'src/moji/json_string.kotoba').read_text(encoding='utf-8')
parse_source = (root / 'src/moji/json_parse.kotoba').read_text(encoding='utf-8')
fixture = (root / 'tests/json-parse-cases.kotoba').read_text(encoding='utf-8')
extract_fixture = (root / 'tests/json-extract-cases.kotoba').read_text(encoding='utf-8')
string_code, n1 = re.subn(r'^\(ns\s+moji\.json-string\s*\(:export \[json-unquote\]\)\)', '(ns json-test (:export [main]))', string_source, count=1)
parse_code, n2 = re.subn(r'^\(ns\s+moji\.json-parse\s*\(:export \[json-parse json-object-field json-array-item json-array-tokens\]\)\s*\(:require \[moji\.json-string :as js\]\)\)', '', parse_source, count=1)
parse_code = parse_code.replace('(js/json-unquote ', '(json-unquote ')
anchor = '(jp-contains-key keys key 0)'
if n1 != 1 or n2 != 1 or parse_code.count(anchor) != 1:
    raise SystemExit('unexpected module or mutation anchor')
spec = importlib.util.spec_from_file_location('mac', amu / 'scripts/seed/check-aiueos-user-macos-native.py')
mac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mac)
results = {}
for name, code, cases, expected in [('validator', parse_code, fixture, 39), ('mutant', parse_code.replace(anchor, '(= 0 1)'), fixture, 35), ('extract', parse_code, extract_fixture, 17), ('extract-mutant', parse_code.replace(anchor, '(= 0 1)'), extract_fixture, 16)]:
    path = out / (name + '.kotoba')
    path.write_text(string_code + '\n' + code + '\n' + cases, encoding='utf-8')
    native = subprocess.run([str(amu / 'bin/amu'), 'run', str(path)], cwd=out,
                            capture_output=True, text=True, timeout=120, check=True)
    if native.stdout.strip() != str(expected):
        raise SystemExit(name + ': native result ' + repr(native.stdout))
    mac.native_run(amu / 'seed/bootstrap/aarch64-macos/amu-full-root.macho', out,
                   'compile', path.name, '--target', 'wasm32-browser', '--output', name + '.wasm')
    dest = out / (name + '-browser')
    subprocess.run([sys.executable, str(amu / 'scripts/seed/check-wasm32-browser.py'),
                    '--browser', str(chrome), '--app', str(out / (name + '.wasm')),
                    '--output', str(dest)], check=True)
    report = json.loads((dest / 'app.json').read_text(encoding='utf-8'))['report']
    if not re.search(rf'\{{:status :ok :result {expected}(?:\s|\}})', report):
        raise SystemExit(name + ': browser report ' + report)
    results[name] = {'result': expected, 'wasmSha256': hashlib.sha256((out / (name + '.wasm')).read_bytes()).hexdigest()}
(out / 'receipt.json').write_text(json.dumps({'stringSourceSha256': hashlib.sha256(string_source.encode()).hexdigest(),
    'parseSourceSha256': hashlib.sha256(parse_source.encode()).hexdigest(),
    'fixtureSha256': hashlib.sha256(fixture.encode()).hexdigest(),
    'extractFixtureSha256': hashlib.sha256(extract_fixture.encode()).hexdigest(), 'results': results}, indent=2) + '\n')
print('PASS_JSON_PARSE native and synthetic browser, including duplicate-key mutant')
