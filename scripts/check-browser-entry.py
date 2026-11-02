#!/usr/bin/env python3
"""Compile and exercise the Bunsho browser program entry in Chrome.

Usage: python3 scripts/check-browser-entry.py AMU_DIR OUTPUT_DIR CHROME
Tests the program protocol only; it does not provide a UI or durable storage.
"""
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

if len(sys.argv) != 4:
    raise SystemExit(__doc__)
amu, out, chrome = [Path(v).resolve() for v in sys.argv[1:]]
out.mkdir(parents=True, exist_ok=False)
root = Path(__file__).resolve().parents[1]
editor = (root / 'src/moji/editor.kotoba').read_text(encoding='utf-8')
entry = (root / 'src/moji/browser-entry.kotoba').read_text(encoding='utf-8')
editor, count = re.subn(r'\A\(ns\s+moji\.editor[\s\S]*?\(:export \[[^\]]*\]\)\)',
                         '(ns moji.editor (:export [main]))', editor, count=1)
if count != 1:
    raise SystemExit('unexpected editor namespace')
anchor = '(defn main [] :i64\n  (+ (test-index-core)'
if editor.count(anchor) != 1:
    raise SystemExit('unexpected editor test entry')
source = editor[:editor.index(anchor)] + entry
(out / 'program.kotoba').write_text(source, encoding='utf-8')
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
mac = load('mac', amu / 'scripts/seed/check-aiueos-user-macos-native.py')
browser = load('browser', amu / 'scripts/seed/check-js-browser.py')
compiler = amu / 'seed/bootstrap/aarch64-macos/amu-full-root.macho'
mac.native_run(compiler, out, 'compile', 'program.kotoba', '--target', 'wasm32-browser', '--output', 'program.wasm')
b = browser.WASM.find_browser(str(chrome))
wasm = out / 'program.wasm'

def call(name, cases):
    target = out / name
    target.mkdir()
    _, results = browser.run_js(b, target, [(n, wasm, args) for n, args in cases])
    return results

def expect(item, result, output):
    report = item.get('report') or ''
    if (item.get('exit') != 0 or item.get('wasmTrap') is not None or item.get('output') != output
            or not re.search(rf'\{{:status :ok :result {result}(?:\s|\}})', report)):
        raise ValueError(repr(item))

def frame(s):
    return str(len(s.encode('utf-8'))) + ':' + s
initial = 'BS1|' + ''.join(map(frame, ['無題の文書', 'edit', '2', 'h1', 'itonami Bunsho', 'p', 'Write here.']))
changed = 'BS1|' + ''.join(map(frame, ['議事😀', 'edit', '2', 'h1', 'itonami Bunsho', 'p', 'Write here.']))
allowed = [37, 38]
a = call('init', [('init', {'allow': allowed, 'args': ['init']})])
expect(a['init'], 0, initial + '\n')
batch = call('trace', [
    ('edit', {'allow': allowed, 'args': ['step', initial, 'title', 'input', '議事😀']}),
    ('reload', {'allow': allowed, 'args': ['step', changed, 'unused', 'click', '']}),
    ('corrupt', {'allow': allowed, 'args': ['step', initial + 'x', 'title', 'input', 'loss']}),
    ('oversized', {'allow': allowed, 'args': ['step', initial, 'title', 'input', 'x' * 1025]}),
    ('oversized-state', {'allow': allowed, 'args': ['step', 'x' * 35001, 'title', 'input', 'loss']}),
    ('badargc', {'allow': allowed, 'args': ['init', 'extra']}),
    ('badkind', {'allow': allowed, 'args': ['step', initial, 'title', 'submit', 'loss']}),
    ('no-write', {'allow': [38], 'args': ['init']}),
    ('no-args', {'allow': [37], 'args': ['init']}),
])
expect(batch['edit'], 0, changed + '\n')
expect(batch['reload'], 0, changed + '\n')
for name, result in [('corrupt', 3), ('oversized', 3), ('oversized-state', 3), ('badargc', 4), ('badkind', 3)]:
    expect(batch[name], result, '')
for name, wire in [('no-write', 37), ('no-args', 38)]:
    item = batch[name]
    if item.get('exit') != 120 or item.get('output') != '' or f':wire {wire} :refused' not in item.get('stderr', ''):
        raise ValueError(repr(item))
receipt = {'compilerSha256': hashlib.sha256(compiler.read_bytes()).hexdigest(),
           'sourceSha256': hashlib.sha256(source.encode()).hexdigest(),
           'wasmSha256': hashlib.sha256(wasm.read_bytes()).hexdigest(),
           'cases': ['init', *batch.keys()]}
(out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print('PASS_BUNSHO_BROWSER_ENTRY: init, edit, fresh-worker restore and refusals')
