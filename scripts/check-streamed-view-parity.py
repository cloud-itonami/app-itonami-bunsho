#!/usr/bin/env python3
"""Compare bounded BS1/BS3 views with a pre-change browser Wasm.

Usage: script AMU OLD_BUILD NEW_BUILD COMPACT_BUILD NEW_OUTPUT CHROME
Synthetic wire parity only; the compact build is not an OS runtime.
"""
import hashlib, importlib.util, json, re, sys
from pathlib import Path

if len(sys.argv) != 7: raise SystemExit(__doc__)
amu, old, new, compact, out = map(lambda x: Path(x).resolve(), sys.argv[1:6])
chrome = sys.argv[6]
out.mkdir(parents=True, exist_ok=False)
spec = importlib.util.spec_from_file_location('browser', amu / 'scripts/seed/check-js-browser.py')
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
def frame(s): return str(len(s.encode('utf-8'))) + ':' + s
cases = {}
# The BS2 source includes the legacy-export tool; compare it against the
# old BS2 renderer, not against the deliberately different BS1 view.
legacy = json.dumps({'found': True, 'document': {'documentId': 'doc-1', 'title': '旧文書', 'revisionId': 'r1', 'body': [{'elementId': 'e1', 'kind': 'paragraph', 'text': '雪'}]}}, ensure_ascii=False, separators=(',', ':'))
cases['legacy-bs2'] = ('BS2|' + ''.join(map(frame, [legacy, '旧文書', 'edit', '1', 'p', '雪', 'e1'])), 0)
for mode in ('edit', 'preview'):
    for count in (0, 1, 8, 32):
        fields = ['題😀\n', mode, str(count)]
        for i in range(count):
            fields += [['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li'][i % 8],
                       ('雪😀\n<&' if i % 3 == 0 else 'x') * (102 if count == 32 else 1)]
        for prefix in ('BS1|', 'BS3|1'):
            cases[f'{mode}-{count}-{prefix}'] = (prefix + ''.join(map(frame, fields)), 0)
    fields = ['t' * 1024, mode, '32'] + sum((['p', 'x' * 1024] for _ in range(32)), [])
    cases[mode + '-maximum'] = ('BS3|1' + ''.join(map(frame, fields)), 0)
for name, wire in {
    'bad-kind': 'BS1|' + ''.join(map(frame, ['t', 'edit', '1', 'evil', 'x'])),
    'trailing': 'BS1|' + ''.join(map(frame, ['t', 'edit', '0'])) + 'x',
    'truncated': 'BS1|' + ''.join(map(frame, ['t', 'edit', '1', 'p'])) + '4:abc',
    'bad-count': 'BS1|' + ''.join(map(frame, ['t', 'edit', '33'])),
    'bad-utf8-end': 'BS1|1:雪4:edit1:0',
    'bad-mode': 'BS1|' + ''.join(map(frame, ['t', 'other', '0'])),
}.items(): cases[name] = (wire, 3)
runs = []
for name, (wire, _) in cases.items():
    for label, build in [('old', old), ('new', new), ('compact', compact)]:
        runs.append((name + '-' + label, build / 'program.wasm',
                     {'allow': [37, 38], 'args': ['view', wire], 'fuel': 100000000}))
for mode in ('edit', 'preview'):
    wire = cases[mode + '-maximum'][0]
    for operation, args in [('protect', ['protect', wire]),
                            ('edit', ['step', wire, 'b31', 'input', '最後😀'])]:
        for label, build in [('old', old), ('new', new), ('compact', compact)]:
            runs.append((mode + '-' + operation + '-' + label, build / 'program.wasm',
                         {'allow': [37, 38], 'args': args, 'fuel': 100000000}))
version, results = h.run_js(chrome, out, runs, timeout=600)
for name, (_, expected) in cases.items():
    items = [results[name + '-' + label] for label in ('old', 'new', 'compact')]
    for item in items:
        if (item.get('exit') != 0 or item.get('wasmTrap') is not None or
            not re.search(rf'\{{:status :ok :result {expected}(?:\s|\}})', item.get('report') or '')):
            raise ValueError((name, item.get('exit'), item.get('report'), item.get('stderr')))
        if expected and item.get('output') != '': raise ValueError(name + ': refusal wrote output')
    if len({item.get('output') for item in items}) != 1: raise ValueError(name + ': view differs')
for mode in ('edit', 'preview'):
    for operation in ('protect', 'edit'):
        items = [results[mode + '-' + operation + '-' + label] for label in ('old', 'new', 'compact')]
        if any(item.get('exit') != 0 or item.get('wasmTrap') is not None or
               not re.search(r'\{:status :ok :result 0(?:\s|\})', item.get('report') or '')
               for item in items): raise ValueError(mode + ': ' + operation + ' refused')
        if len({item.get('output') for item in items}) != 1:
            raise ValueError(mode + ': ' + operation + ' output differs')
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
report = {'status': 'PASS_STREAMED_VIEW_PARITY', 'cases': list(cases), 'browser': version,
          'wasmSha256': {label: sha(build / 'program.wasm') for label, build in
                         [('old', old), ('new', new), ('compact', compact)]},
          'scope': 'synthetic browser wire parity; compact Wasm is not QEMU'}
(out / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(report['status'], len(cases))
