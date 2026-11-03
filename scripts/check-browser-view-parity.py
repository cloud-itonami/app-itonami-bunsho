#!/usr/bin/env python3
"""Compare old and new browser view wires for BS1 and BS2 snapshots.

Usage: python3 scripts/check-browser-view-parity.py AMU_DIR OLD_BUILD NEW_BUILD BS2_FILE OUTPUT_DIR CHROME
Synthetic input only. This checks view parity, not production compatibility.
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

amu, old, new, sample, out, chrome = map(lambda x: Path(x).resolve(), sys.argv[1:])
out.mkdir(parents=True, exist_ok=False)
wire = sample.read_text(encoding='utf-8')
data = wire.encode('utf-8')
if not data.startswith(b'BS2|'): raise ValueError('not BS2')
pos, fields = 4, []
while pos < len(data):
    end = data.index(b':', pos)
    size = int(data[pos:end])
    pos = end + 1
    field = data[pos:pos + size]
    if len(field) != size: raise ValueError('truncated')
    fields.append(field.decode('utf-8', errors='strict'))
    pos += size
count = int(fields[3])
if len(fields) != 4 + 3 * count: raise ValueError('field count')
values = [fields[1], fields[2], fields[3]]
for i in range(count): values.extend(fields[4 + 3 * i:6 + 3 * i])
def frame(value): return str(len(value.encode('utf-8'))) + ':' + value
bs1 = 'BS1|' + ''.join(map(frame, values))
spec = importlib.util.spec_from_file_location('browser', amu / 'scripts/seed/check-js-browser.py')
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)
chrome_bin = browser.WASM.find_browser(str(chrome))
cases = [('old-bs1', old / 'program.wasm', {'allow': [37, 38], 'fuel': 25000000, 'args': ['view', bs1]}),
         ('new-bs1', new / 'program.wasm', {'allow': [37, 38], 'fuel': 25000000, 'args': ['view', bs1]}),
         ('old-bs2', old / 'program.wasm', {'allow': [37, 38], 'fuel': 100000000, 'args': ['view', wire]}),
         ('new-bs2', new / 'program.wasm', {'allow': [37, 38], 'fuel': 100000000, 'args': ['view', wire]})]
_, results = browser.run_js(chrome_bin, out, cases)
for name, _, _ in cases:
    item = results[name]
    if item.get('exit') != 0 or item.get('wasmTrap') is not None or not re.search(r'\{:status :ok :result 0(?:\s|\})', item.get('report') or ''):
        raise ValueError(name + ': ' + repr(item))
if results['old-bs1']['output'] != results['new-bs1']['output'] or results['old-bs2']['output'] != results['new-bs2']['output']:
    raise ValueError('view wires differ')
(out / 'result.json').write_text(json.dumps({'status': 'PASS', 'blocks': count,
    'reports': {name: results[name]['report'] for name, _, _ in cases},
    'limitations': ['synthetic data', 'does not prove accessibility or general performance']}, indent=2) + '\n')
print('PASS_VIEW_PARITY old/new BS1 and old/new BS2')
