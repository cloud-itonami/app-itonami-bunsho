#!/usr/bin/env python3
"""Exercise the Kotoba migration JSON string decoder on native and browser Wasm.

Usage: python3 scripts/check-json-string.py AMU_DIR OUTPUT_DIR CHROME
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
source = (root / 'src/moji/json_string.kotoba').read_text(encoding='utf-8')
test = (root / 'tests/json-string-cases.kotoba').read_text(encoding='utf-8')
staged, count = re.subn(r'\(:export \[json-unquote\]\)', '(:export [main])', source, count=1)
if count != 1:
    raise SystemExit('decoder namespace changed')
anchor = '(< c 32) (option-none-of [:option :string])'
if staged.count(anchor) != 1:
    raise SystemExit('mutation anchor changed')
spec = importlib.util.spec_from_file_location('mac', amu / 'scripts/seed/check-aiueos-user-macos-native.py')
mac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mac)
results = {}
for name, code, expected in [('decoder', staged, 23), ('mutant', staged.replace(anchor, '(< c 0) (option-none-of [:option :string])'), 22)]:
    path = out / (name + '.kotoba')
    path.write_text(code + '\n' + test, encoding='utf-8')
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
(out / 'receipt.json').write_text(json.dumps({'sourceSha256': hashlib.sha256(source.encode()).hexdigest(),
    'fixtureSha256': hashlib.sha256(test.encode()).hexdigest(), 'results': results}, indent=2) + '\n')
print('PASS_JSON_STRING native and synthetic browser, including unescaped-control mutant')
