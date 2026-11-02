#!/usr/bin/env python3
"""Run the existing index tests in selfhost Wasm, including a mutant.

Usage: python3 scripts/check-index-wasm.py AMU_DIR OUTPUT_DIR CHROME
The output directory must not already exist. macOS ARM64 full-root only.
The application source is never edited; the compiler and browser do the work.
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
amu, out, chrome = map(Path, sys.argv[1:])
amu, out, chrome = amu.resolve(), out.resolve(), chrome.resolve()
out.mkdir(parents=True, exist_ok=False)
compiler = amu / 'seed/bootstrap/aarch64-macos/amu-full-root.macho'
native = amu / 'scripts/seed/check-aiueos-user-macos-native.py'
browser = amu / 'scripts/seed/check-wasm32-browser.py'
source = Path(__file__).resolve().parents[1] / 'aiueos/docs_index.kotoba'
s = source.read_text(encoding='utf-8')
s, n = re.subn(r'\A\(ns\s+docs\.index[\s\S]*?\(:export \[[^\]]*\]\)\)',
               '(ns docs.index (:export [main]))', s, count=1)
if n != 1:
    raise SystemExit('unexpected source namespace')
s, n = re.subn(r'\(defn main \[\] :i64\s+0\)',
               '(defn main [] :i64 (if (= (+ (test-span) (test-next) (test-clamp) (test-in-span) (test-merge) (test-fail-closed)) 6) 0 1))', s, count=1)
if n != 1:
    raise SystemExit('unexpected source entry')
old = '(defn next-start [start :i64 len :i64] :i64\n  (+ start len 1))'
if s.count(old) != 1:
    raise SystemExit('negative control does not match source')
spec = importlib.util.spec_from_file_location('amu_mac_native', native)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
for name, text, expected in [('index', s, 0), ('mutant', s.replace(old, old.replace('len 1', 'len 2')), 1)]:
    (out / f'{name}.kotoba').write_text(text, encoding='utf-8')
    mod.native_run(compiler, out, 'compile', f'{name}.kotoba', '--target', 'wasm32-browser', '--output', f'{name}.wasm')
    run = out / f'{name}-browser'
    subprocess.run([sys.executable, str(browser), '--browser', str(chrome), '--app', str(out / f'{name}.wasm'), '--output', str(run)], check=True)
    result = json.loads((run / 'app.json').read_text(encoding='utf-8'))
    if not re.search(rf'\{{:status :ok :result {expected}(?:\s|\}})', result.get('report', '')):
        raise SystemExit(f'{name}: unexpected guest result: {result.get("report")}')
    print(f'{name}: expected result {expected}; wasm sha256 {hashlib.sha256((out / f"{name}.wasm").read_bytes()).hexdigest()}')
