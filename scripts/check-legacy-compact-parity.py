#!/usr/bin/env python3
"""Compare synthetic legacy imports and BS2 operations across browser builds.

Usage: script AMU OLD_BUILD NEW_BUILD COMPACT_BUILD NEW_OUTPUT CHROME
The compact build is experimental; this is not a real-data or QEMU test.
"""
import hashlib, importlib.util, json, re, sys
from pathlib import Path
if len(sys.argv) != 7: raise SystemExit(__doc__)
amu, old, new, compact, out = map(lambda x: Path(x).resolve(), sys.argv[1:6])
chrome = sys.argv[6]; out.mkdir(parents=True, exist_ok=False)
spec = importlib.util.spec_from_file_location('browser', amu / 'scripts/seed/check-js-browser.py')
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
def frame(s): return str(len(s.encode('utf-8'))) + ':' + s
def original(count, text):
    body = [{'elementId': 'e' + str(i), 'kind': 'paragraph', 'text': text} for i in range(count)]
    return json.dumps({'found': True, 'document': {'documentId': 'doc-1', 'title': '旧文書',
        'revisionId': 'r1', 'body': body}}, ensure_ascii=False, separators=(',', ':'))
def bs2(raw, count, text):
    fields = [raw, '旧文書', 'edit', str(count)] + sum((['p', text, 'e' + str(i)] for i in range(count)), [])
    wire = 'BS2|' + ''.join(map(frame, fields))
    if len(wire.encode()) > 35000: raise ValueError('fixture exceeds snapshot limit')
    return wire
cases = {}
for count in (2, 4, 8, 12, 16):
    raw = original(count, 'x' * 1000); wire = bs2(raw, count, 'x' * 1000)
    for op, args in [('view', ['view', wire]), ('protect', ['protect', wire]),
                     ('original', ['legacy-original', wire]), ('edit', ['step', wire, 'b0', 'input', '編集😀'])]:
        cases[f'{count}-{op}'] = (args, 0)
for name, text in [('plain', 'x' * 1000), ('unicode', '雪😀' * 140),
                   ('escapes', ('a\n"\\' * 180)), ('boundary-128', 'z' * 126),
                   ('boundary-129', 'z' * 127)]:
    cases['import-' + name] = (['legacy-import', original(1, text)], 0)
raw = original(1, 'x' * 150)
for name, malformed in [('bad-surrogate', raw.replace('x' * 150, 'x' * 140 + r'\uD800')),
                        ('bad-escape', raw.replace('x' * 150, 'x' * 140 + r'\q')),
                        ('raw-control', raw.replace('x' * 150, 'x' * 140 + '\x01')),
                        ('duplicate-key', raw.replace('"kind":"paragraph"', '"kind":"paragraph","kind":"paragraph"')),
                        ('overlong-text', original(1, 'x' * 1025))]:
    cases['refuse-' + name] = (['legacy-import', malformed], 3)
runs = []
for name, (args, _) in cases.items():
    for label, build in [('old', old), ('new', new), ('compact', compact)]:
        runs.append((name + '-' + label, build / 'program.wasm', {'allow': [37, 38], 'args': args, 'fuel': 100000000}))
version, results = h.run_js(chrome, out, runs, timeout=600)
for name, (_, expected) in cases.items():
    items = [results[name + '-' + label] for label in ('old', 'new', 'compact')]
    for item in items:
        if item.get('exit') != 0 or item.get('wasmTrap') is not None or not re.search(
            rf'\{{:status :ok :result {expected}(?:\s|\}})', item.get('report') or ''):
            raise ValueError((name, item.get('exit'), item.get('report'), item.get('stderr')))
        if expected and item.get('output') != '': raise ValueError(name + ': refusal wrote output')
    if len({item.get('output') for item in items}) != 1: raise ValueError(name + ': output differs')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
report = {'status': 'PASS_LEGACY_COMPACT_PARITY', 'cases': list(cases), 'browser': version,
          'wasmSha256': {label: sha(build / 'program.wasm') for label, build in
                         [('old', old), ('new', new), ('compact', compact)]},
          'scope': 'synthetic legacy browser parity; no real data, QEMU or release'}
(out / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(report['status'], len(cases))
