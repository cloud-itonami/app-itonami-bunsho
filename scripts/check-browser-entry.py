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
from browser_source import stage
source = stage(root)
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
preview = 'BS1|' + ''.join(map(frame, ['議事😀', 'preview', '2', 'h1', 'itonami Bunsho', 'p', 'Write here.']))
multiline_text = '最初😀\n続き'
multiline = 'BS3|1' + ''.join(map(frame, ['無題の文書', 'edit', '2', 'h1', 'itonami Bunsho', 'p', multiline_text]))
legacy_raw = json.dumps({'found':True,'document':{'documentId':'doc-1','title':'旧文書',
    'revisionId':'r1','body':[{'elementId':'e1','kind':'paragraph','text':multiline_text}]}},ensure_ascii=False,separators=(',',':'))
legacy_multiline = 'BS3|2' + ''.join(map(frame, [legacy_raw, '旧文書', 'edit', '1', 'p', multiline_text, 'e1']))
allowed = [37, 38]
a = call('init', [('init', {'allow': allowed, 'args': ['init']})])
expect(a['init'], 0, initial + '\n')
batch = call('trace', [
    ('multiline', {'allow': allowed, 'args': ['step', initial, 'b1', 'input', multiline_text]}),
    ('multiline-reload', {'allow': allowed, 'args': ['step', multiline, 'unused', 'click', '']}),
    ('legacy-multiline', {'allow': allowed, 'fuel': 100000000, 'args': ['legacy-import', legacy_raw]}),
    ('legacy-multiline-reload', {'allow': allowed, 'fuel': 100000000, 'args': ['step', legacy_multiline, 'unused', 'click', '']}),
    ('bad-multiline-version', {'allow': allowed, 'args': ['view', 'BS3|3']}),
    ('edit', {'allow': allowed, 'args': ['step', initial, 'title', 'input', '議事😀']}),
    ('view', {'allow': allowed, 'fuel': 10000000, 'args': ['view', changed]}),
    ('preview', {'allow': allowed, 'fuel': 10000000, 'args': ['view', preview]}),
    ('view-corrupt', {'allow': allowed, 'args': ['view', initial + 'x']}),
    ('reload', {'allow': allowed, 'args': ['step', changed, 'unused', 'click', '']}),
    ('corrupt', {'allow': allowed, 'args': ['step', initial + 'x', 'title', 'input', 'loss']}),
    ('oversized', {'allow': allowed, 'args': ['step', initial, 'title', 'input', 'x' * 1025]}),
    ('oversized-state', {'allow': allowed, 'args': ['step', 'x' * 35001, 'title', 'input', 'loss']}),
    ('badargc', {'allow': allowed, 'args': ['init', 'extra']}),
    ('badkind', {'allow': allowed, 'args': ['step', initial, 'title', 'submit', 'loss']}),
    ('no-write', {'allow': [38], 'args': ['init']}),
    ('no-args', {'allow': [37], 'args': ['init']}),
])
expect(batch['multiline'], 0, multiline + '\n')
expect(batch['multiline-reload'], 0, multiline + '\n')
expect(batch['legacy-multiline'], 0, legacy_multiline + '\n')
expect(batch['legacy-multiline-reload'], 0, legacy_multiline + '\n')
expect(batch['bad-multiline-version'], 3, '')
expect(batch['edit'], 0, changed + '\n')
expect(batch['reload'], 0, changed + '\n')
view = batch['view']
if view.get('exit') != 0 or view.get('wasmTrap') is not None or not re.search(r'\{:status :ok :result 0(?:\s|\})', view.get('report') or ''):
    raise ValueError(repr(view))
wire = (view.get('output') or '').encode('utf-8')
if not wire.startswith(b'BV2|') or not wire.endswith(b'\n'):
    raise ValueError('invalid view wire')
pos, nodes = 4, []
def field():
    global pos
    end = wire.index(b':', pos)
    count = int(wire[pos:end])
    pos = end + 1
    value = wire[pos:pos + count].decode('utf-8', errors='strict')
    pos += count
    return value
def node():
    fields = [field() for _ in range(8)]
    nodes.append(fields)
    for _ in range(int(fields[7])):
        node()
node()
if pos != len(wire) - 1 or nodes[0][0] != 'div' or not any(n[3] == 'title' and n[4] == '議事😀' and n[6] == '文書タイトル' for n in nodes):
    raise ValueError('view does not match edited state')
if batch['preview'].get('exit') != 0 or 'page preview' not in (batch['preview'].get('output') or '') or '3:k10' in (batch['preview'].get('output') or ''):
    raise ValueError('preview view missing or still contains editing controls')
for name, result in [('view-corrupt', 3), ('corrupt', 3), ('oversized', 3), ('oversized-state', 3), ('badargc', 4), ('badkind', 3)]:
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
