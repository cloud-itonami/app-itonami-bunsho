#!/usr/bin/env python3
"""Test local legacy divergence guards around the experimental IDB adapter.

Usage: script AMU_DIR NEW_OUTPUT_DIR CHROME
Synthetic data only; no UI, implicit consent, real migration or crash proof.
"""
import functools,hashlib,http.server,importlib.util,json,shutil,sys,threading,time
from pathlib import Path
if len(sys.argv)!=4:raise SystemExit(__doc__)
amu,out,chrome=map(lambda s:Path(s).resolve(),sys.argv[1:]);root=Path(__file__).resolve().parents[1];out.mkdir(parents=True,exist_ok=False);site=out/'site';site.mkdir();(out/'profile').mkdir()
for name in ('transactional-storage.js','managed-storage.js'):shutil.copyfile(root/'browser'/name,site/name)
(site/'index.html').write_text('<!doctype html><script type="module">import {openManagedStore} from "./managed-storage.js";window.openStore=openManagedStore;window.ready=true</script>')
spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py');browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(site)));threading.Thread(target=server.serve_forever,daemon=True).start();pipe=browser.Pipe(str(chrome),out/'profile');url=f'http://127.0.0.1:{server.server_port}/index.html'
try:
 def tab():
  t=pipe.call('Target.createTarget',{'url':'about:blank'})['targetId'];s=pipe.call('Target.attachToTarget',{'targetId':t,'flatten':True})['sessionId'];pipe.call('Page.enable',{},s);pipe.call('Page.navigate',{'url':url},s);return s
 a,b=tab(),tab()
 def ev(x,s=a,awaited=False):
  r=pipe.call('Runtime.evaluate',{'expression':x,'returnByValue':True,'awaitPromise':awaited},s)
  if 'exceptionDetails' in r:raise ValueError(r['exceptionDetails'])
  return r.get('result',{}).get('value')
 def wait(x,s,label):
  until=time.time()+60
  while time.time()<until:
   try:
    if ev(x,s):return
   except RuntimeError as e:
    if not any(m in str(e) for m in ('Execution context was destroyed','Cannot find context with specified id')):raise
   time.sleep(.1)
  raise TimeoutError(label)
 for s in (a,b):wait('window.ready===true',s,'load')
 ev('localStorage.setItem("legacy","original")')
 for s in (a,b):assert ev('window.openStore("itonami.office.bunsho.v2",35000,()=>{if(window.__failLegacy)throw Error("read denied");return localStorage.getItem("legacy")}).then(x=>{window.store=x;return true})',s,True)
 initial=ev('store.inspect()',a,True);assert initial['current']=={'revision':0,'value':None,'legacyAnchor':None} and initial['legacy']=='original'
 refused=ev('store.commit('+json.dumps(initial['current'])+',"candidate",{initialLegacyAnchor:"wrong"})',a,True);assert refused['status']=='legacy-changed' and ev('store.inspect()',a,True)==initial
 imported=ev('store.commit('+json.dumps(initial['current'])+',"candidate",{initialLegacyAnchor:"original"})',a,True);assert imported['status']=='committed' and imported['current']['legacyAnchor']=='original'
 assert ev('localStorage.getItem("legacy")')=='original'
 ev('window.__failLegacy=true')
 assert ev('store.commit('+json.dumps(imported['current'])+',"must not write").then(()=>false,()=>true)',a,True)
 ev('window.__failLegacy=false');assert ev('store.inspect()',a,True)['current']==imported['current']
 ev('localStorage.setItem("legacy","old-tab edit")',b)
 assert not ev('store.inspect()',a,True)['legacyMatches']
 refused=ev('store.commit('+json.dumps(imported['current'])+',"new edit")',a,True);assert refused['status']=='legacy-changed'
 assert ev('store.inspect()',a,True)['current']==imported['current']
 ev('localStorage.setItem("legacy","original")',b)
 # Simulate a legacy writer after the precheck but before transaction complete.
 ev('window.__put=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(...args){const r=window.__put.apply(this,args);localStorage.setItem("legacy","during commit");return r}')
 outcome=ev('store.commit('+json.dumps(imported['current'])+',"new branch")',a,True);ev('IDBObjectStore.prototype.put=window.__put')
 assert outcome['status']=='legacy-changed-after-commit' and outcome['current']['value']=='new branch'
 assert ev('localStorage.getItem("legacy")')=='during commit' and ev('store.inspect()',a,True)['current']==outcome['current']
 ev('localStorage.setItem("legacy","original")',b)
 # A read failure after the IDB commit is reported as uncertain with its
 # committed revision, rather than being mistaken for a failed transaction.
 ev('IDBObjectStore.prototype.put=function(...args){const r=window.__put.apply(this,args);window.__failLegacy=true;return r}')
 uncertain=ev('store.commit('+json.dumps(outcome['current'])+',"second branch")',a,True)
 ev('IDBObjectStore.prototype.put=window.__put;window.__failLegacy=false')
 assert uncertain['status']=='legacy-unreadable-after-commit' and ev('store.inspect()',a,True)['current']==uncertain['current']
 assert ev('localStorage.getItem("legacy")')=='original'
 report={'status':'PASS_MANAGED_STORAGE_SYNTHETIC','checks':['explicit-caller-baseline','precommit-legacy-divergence-refusal','precommit-read-failure-refusal','postcommit-legacy-divergence-reported','postcommit-legacy-read-failure-reported','legacy-data-untouched'],'sourceSha256':{x:hashlib.sha256((root/'browser'/x).read_bytes()).hexdigest() for x in ('transactional-storage.js','managed-storage.js')},'scope':'synthetic same-origin Chrome; localStorage and IndexedDB are not atomically coupled; no UI, user consent, real migration, crash/power loss or release'}
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'],flush=True)
finally:pipe.close();server.shutdown();server.server_close()
