#!/usr/bin/env python3
"""Exercise the experimental local IndexedDB primitive in real Chrome tabs.

Usage: script AMU_DIR NEW_OUTPUT_DIR CHROME
Synthetic loopback data only. This does not exercise app integration, legacy
migration, crash/power-loss, other browsers or a production release.
"""
import functools,hashlib,http.server,importlib.util,json,shutil,sys,threading,time
from pathlib import Path
if len(sys.argv)!=4:raise SystemExit(__doc__)
amu,out,chrome=map(lambda s:Path(s).resolve(),sys.argv[1:]);root=Path(__file__).resolve().parents[1]
out.mkdir(parents=True,exist_ok=False);site=out/'site';site.mkdir();(out/'profile').mkdir()
source=root/'browser/transactional-storage.js';shutil.copyfile(source,site/'transactional-storage.js')
(site/'index.html').write_text('<!doctype html><meta charset="utf-8"><script type="module">import {openTransactionalStore} from "./transactional-storage.js"; window.openStore=openTransactionalStore;window.ready=true;</script>')
spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py');browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(site)));threading.Thread(target=server.serve_forever,daemon=True).start();pipe=browser.Pipe(str(chrome),out/'profile');url=f'http://127.0.0.1:{server.server_port}/index.html'
try:
 def tab():
  target=pipe.call('Target.createTarget',{'url':'about:blank'})['targetId'];s=pipe.call('Target.attachToTarget',{'targetId':target,'flatten':True})['sessionId'];pipe.call('Page.enable',{},s);pipe.call('Page.navigate',{'url':url},s);return s
 a,b=tab(),tab()
 def ev(expression,s,awaited=False):
  result=pipe.call('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':awaited},s)
  if 'exceptionDetails' in result:raise ValueError(result['exceptionDetails'])
  return result.get('result',{}).get('value')
 def wait(expression,s,label):
  deadline=time.time()+60
  while time.time()<deadline:
   try:
    if ev(expression,s):return
   except RuntimeError as e:
    if not any(x in str(e) for x in ('Execution context was destroyed','Cannot find context with specified id')):raise
   time.sleep(.1)
  raise TimeoutError(label)
 for s in (a,b):wait('window.ready===true',s,'module load');assert ev('window.openStore("itonami.office.bunsho.v1",35000).then(x=>{window.store=x;return true})',s,True)
 ev('localStorage.setItem("legacy","legacy preserved")',a)
 initial=ev('store.read()',a,True);assert initial=={'revision':0,'value':None}
 first=ev('store.compareAndSwap({revision:0,value:null},"initial")',a,True);assert first=={'status':'committed','current':{'revision':1,'value':'initial'}}
 # Hold a real readwrite transaction open, queue both tabs behind it, then
 # release it. Both competing transactions therefore start from revision 1.
 ev('''new Promise((resolve,reject)=>{const r=indexedDB.open("itonami.office.bunsho.v1",1);r.onsuccess=()=>{const d=r.result,t=d.transaction("records","readwrite"),s=t.objectStore("records");window.__releaseLock=false;function hold(){if(window.__releaseLock)return;const g=s.get("current");g.onsuccess=()=>{if(!window.__heldLock){window.__heldLock=true;resolve(true)}hold()};g.onerror=()=>reject(Error("hold"))}t.oncomplete=()=>d.close();t.onabort=()=>reject(Error("hold aborted"));hold()};r.onerror=()=>reject(Error("open"))})''',a,True)
 ev('window.result=null;store.compareAndSwap({revision:1,value:"initial"},"writer A").then(x=>window.result=x,e=>window.result={error:String(e)})',a)
 ev('window.result=null;store.compareAndSwap({revision:1,value:"initial"},"writer B").then(x=>window.result=x,e=>window.result={error:String(e)})',b)
 assert ev('window.result===null',a) and ev('window.result===null',b)
 ev('window.__releaseLock=true',a)
 wait('window.result!==null',a,'writer A');wait('window.result!==null',b,'writer B')
 ar,br=ev('window.result',a),ev('window.result',b);assert sorted([ar['status'],br['status']])==['committed','conflict'],(ar,br)
 now=ev('store.read()',a,True);assert now['revision']==2 and now['value'] in ('writer A','writer B');assert ev('store.read()',b,True)==now
 # Revisions prevent ABA when bytes return to their former value.
 a1=ev('store.compareAndSwap('+json.dumps(now)+',"intermediate")',a,True);assert a1['status']=='committed'
 a2=ev('store.compareAndSwap('+json.dumps(a1['current'])+','+json.dumps(now['value'])+')',a,True);assert a2['status']=='committed'
 stale=ev('store.compareAndSwap('+json.dumps(now)+',"must not commit")',b,True);assert stale['status']=='conflict' and stale['current']==a2['current']
 current=a2['current']
 # Simulate a write exception after the backup add has been queued. The whole
 # readwrite transaction must abort: neither state nor backup may survive.
 ev('window.__put=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(){throw Error("injected failure")}',a)
 failed=ev('store.compareAndSwap('+json.dumps(current)+',"should abort",true).then(()=>false,()=>true)',a,True);assert failed
 ev('IDBObjectStore.prototype.put=window.__put',a)
 assert ev('store.read()',b,True)==current and ev('store.readBackup('+str(current['revision'])+')',b,True)=={'revision':0,'value':None}
 committed=ev('store.compareAndSwap('+json.dumps(current)+',"restored value",true)',a,True);assert committed['status']=='committed'
 assert ev('store.readBackup('+str(current['revision'])+')',b,True)==current
 # Invalid transport strings and bounds must not become replacement bytes.
 assert ev('store.compareAndSwap('+json.dumps(committed['current'])+',String.fromCharCode(0xd800)).then(()=>false,()=>true)',a,True)
 assert ev('store.compareAndSwap('+json.dumps(committed['current'])+',"a".repeat(35001)).then(()=>false,()=>true)',a,True)
 assert ev('store.read()',b,True)==committed['current']
 # A freshly opened third tab sees both state and the transactional backup.
 c=tab();wait('window.ready===true',c,'third tab');assert ev('window.openStore("itonami.office.bunsho.v1",35000).then(x=>{window.store=x;return true})',c,True)
 assert ev('store.read()',c,True)==committed['current'] and ev('store.readBackup('+str(current['revision'])+')',c,True)==current
 assert ev('localStorage.getItem("legacy")',c)=='legacy preserved'
 # A malformed database record is rejected and cannot be silently overwritten.
 ev('''new Promise((resolve,reject)=>{const r=indexedDB.open("itonami.office.bunsho.v1",1);r.onsuccess=()=>{const d=r.result,t=d.transaction("records","readwrite");t.objectStore("records").put({format:"bad",revision:5,value:"corrupt"},"current");t.oncomplete=()=>{d.close();resolve(true)};t.onabort=()=>reject(Error("inject"))};r.onerror=()=>reject(Error("open"))})''',a,True)
 assert ev('store.read().then(()=>false,()=>true)',c,True)
 assert ev('store.compareAndSwap('+json.dumps(committed['current'])+',"overwrite").then(()=>false,()=>true)',c,True)
 report={'status':'PASS_TRANSACTIONAL_STORAGE_SYNTHETIC','sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'checks':['two-tab-competing-writers','revision-aba-refusal','transaction-abort-preserves-state-and-backup','backup-and-state-atomic','invalid-unicode-and-oversize','third-tab-reopen','legacy-localstorage-untouched','corrupt-record-refusal'],'scope':'synthetic same-origin Chrome tabs; experimental adapter only, not integrated; no old-client coordination, app migration, crash/power-loss, QEMU or release'}
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'],flush=True)
finally:pipe.close();server.shutdown();server.server_close()
