#!/usr/bin/env python3
"""Check Bunsho model snapshot codec with a selfhost compiler and Chrome.

Usage: python3 scripts/check-snapshot-wasm.py AMU_DIR OUTPUT_DIR CHROME
The existing editor's document exports are narrowed to main for this test:
this does not test the product UI, durable storage or OS integration.
"""
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

if len(sys.argv) != 4:
    raise SystemExit(__doc__)
amu, out, chrome = [Path(v).resolve() for v in sys.argv[1:]]
out.mkdir(parents=True, exist_ok=False)
root = Path(__file__).resolve().parents[1]
compiler = amu / 'seed/bootstrap/aarch64-macos/amu-full-root.macho'
source = (root / 'src/moji/editor.kotoba').read_text(encoding='utf-8')
staged, count = re.subn(r'\A\(ns\s+moji\.editor[\s\S]*?\(:export \[[^\]]*\]\)\)',
                         '(ns moji.editor (:export [main]))', source, count=1)
if count != 1:
    raise SystemExit('unexpected editor namespace')
anchor = '(if (> i 32) -1'
if staged.count(anchor) != 1:
    raise SystemExit('mutation anchor changed')
spec = importlib.util.spec_from_file_location('mac', amu / 'scripts/seed/check-aiueos-user-macos-native.py')
mac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mac)
results = {}
for name, text, expected in [('snapshot', staged, 17), ('mutant', staged.replace(anchor, '(if (> i 31) -1'), 16)]:
    src = out / (name + '.kotoba')
    src.write_text(text, encoding='utf-8')
    native = subprocess.run([str(amu / 'bin/amu'), 'run', str(src)], cwd=out,
                            check=True, capture_output=True, text=True, timeout=120)
    if native.stdout.strip() != str(expected):
        raise SystemExit(f'{name}: unexpected native result {native.stdout!r}')
    mac.native_run(compiler, out, 'compile', src.name, '--target', 'wasm32-browser', '--output', name + '.wasm')
    run = out / (name + '-browser')
    subprocess.run([sys.executable, str(amu / 'scripts/seed/check-wasm32-browser.py'),
                    '--browser', str(chrome), '--app', str(out / (name + '.wasm')),
                    '--output', str(run)], check=True)
    report = json.loads((run / 'app.json').read_text(encoding='utf-8')).get('report', '')
    if not re.search(rf'\{{:status :ok :result {expected}(?:\s|\}})', report):
        raise SystemExit(f'{name}: unexpected browser report {report}')
    results[name] = {'result': expected, 'report': report,
                     'wasmSha256': hashlib.sha256((out / (name + '.wasm')).read_bytes()).hexdigest()}
receipt = {'sourceSha256': hashlib.sha256(source.encode()).hexdigest(),
           'compilerSha256': hashlib.sha256(compiler.read_bytes()).hexdigest(), 'results': results}
(out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print('PASS_BUNSHO_SNAPSHOT_MODEL native and browser, including mutant')
