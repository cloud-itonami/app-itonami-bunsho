#!/usr/bin/env python3
"""Compare old and current Bunsho BV2 output on synthetic document boundaries.

Usage: script AMU BASELINE_BUILD CURRENT_BUILD OUTPUT CHROME
Requires the baseline and current candidates built from their respective source.
This checks bytes and refusals, not real user data, QEMU, or publication.
"""
import hashlib,importlib.util,json,re,sys
from pathlib import Path
if len(sys.argv)!=6:raise SystemExit(__doc__)
amu,baseline,current,out,chrome=map(lambda s:Path(s).resolve(),sys.argv[1:]);out.mkdir(parents=True,exist_ok=False)
spec=importlib.util.spec_from_file_location('harness',amu/'scripts/seed/check-js-browser.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def sha(data):return hashlib.sha256(data).hexdigest()
for build in (baseline,current):
 receipt=json.loads((build/'build-receipt.json').read_text())
 if sha((build/'program.wasm').read_bytes())!=receipt['wasmSha256'] or sha((build/'program.kotoba').read_bytes())!=receipt['sourceSha256']:raise ValueError('candidate digest mismatch')
def frame(value):return str(len(value.encode('utf8')))+':'+value
fixtures={}
for count in (2,4,8,16,24,32):
 fixtures['blocks-'+str(count)]='BS3|1'+''.join(map(frame,['境界😀','edit',str(count)]+sum((['p','x'*1024] for _ in range(count)),[])))
fixtures['unicode']='BS3|1'+''.join(map(frame,['日本語😀','preview','2','h2','雪\n海','li','é']))
fixtures['invalid']='BS3|1not-a-frame'
for value in fixtures.values():
 if len(value.encode('utf8'))>35000:raise ValueError('fixture bounds')
runs=[]
for name,state in fixtures.items():
 for label,build in [('baseline',baseline),('current',current)]:
  runs.append((name+'-'+label,build/'program.wasm',{'allow':[37,38],'args':['view',state],'fuel':100000000}))
version,results=h.run_js(str(chrome),out,runs,timeout=600)
cases={}
for name in fixtures:
 old,new=(results[name+'-'+key] for key in ('baseline','current'))
 expected=3 if name=='invalid' else 0
 for item in (old,new):
  if item['exit']!=0 or item['wasmTrap'] is not None or not re.match(r'^\{:status :ok :result '+str(expected)+r'(?:\s|\})',item.get('report') or ''):raise ValueError(name+' unexpected outcome '+repr(item))
 if old['output']!=new['output']:raise ValueError(name+' output differs')
 cases[name]={'inputBytes':len(fixtures[name].encode()),'outputSha256':sha(old['output'].encode()),'outputBytes':len(old['output'].encode()),'result':expected}
report={'status':'PASS_BUNSHO_VIEW_STREAM_PARITY','browser':version,'cases':cases,'baselineWasmSha256':sha((baseline/'program.wasm').read_bytes()),'currentWasmSha256':sha((current/'program.wasm').read_bytes()),'scope':'synthetic Wasm browser protocol; no real user data, QEMU or deployment'}
(out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(report['status'],flush=True)
