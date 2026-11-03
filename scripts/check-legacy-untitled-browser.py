#!/usr/bin/env python3
"""Import a synthetic untitled documentsGet response in the browser UI.

Usage: AMU BUILD NEW_OUTPUT CHROME. No real data or old origin is accessed.
"""
import functools,hashlib,http.server,importlib.util,json,sys,threading,time
from pathlib import Path
if len(sys.argv)!=5: raise SystemExit(__doc__)
amu,build,out,chrome=(Path(p).resolve() for p in sys.argv[1:])
out.mkdir(parents=True,mode=0o700,exist_ok=False);(out/'profile').mkdir(mode=0o700);(out/'downloads').mkdir(mode=0o700)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(build)))
threading.Thread(target=server.serve_forever,daemon=True).start()
spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py');browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
pipe=browser.Pipe(str(chrome),out/'profile')
legacy={'found':True,'document':{'documentId':'synthetic-d1','revisionId':'rev-0','body':[{'elementId':'e1','kind':'paragraph','text':'本文😀'}]}}
raw=json.dumps(legacy,ensure_ascii=False,separators=(',',':'));(out/'legacy.json').write_text(raw)
bad=json.loads(raw);bad['document']['title']=None;(out/'invalid.json').write_text(json.dumps(bad,ensure_ascii=False))
try:
 t=pipe.call('Target.createTarget',{'url':'about:blank'})['targetId'];s=pipe.call('Target.attachToTarget',{'targetId':t,'flatten':True})['sessionId'];pipe.call('Page.enable',{},s);pipe.call('Page.navigate',{'url':f'http://127.0.0.1:{server.server_port}/index.html'},s)
 def ev(expr,awaited=False):
  r=pipe.call('Runtime.evaluate',{'expression':expr,'returnByValue':True,'awaitPromise':awaited},s)
  if 'exceptionDetails' in r:raise ValueError(r['exceptionDetails'])
  return r.get('result',{}).get('value')
 def wait(expr,label):
  end=time.monotonic()+90
  while time.monotonic()<end:
   try:
    if ev(expr):return
   except RuntimeError as error:
    if not any(x in str(error) for x in ('Execution context was destroyed','Cannot find context with specified id')):raise
   time.sleep(.1)
  raise TimeoutError(label+': '+str(ev('document.getElementById("status")?.textContent')))
 def state(key='current'):
  return ev('''new Promise((resolve,reject)=>{let r=indexedDB.open("itonami.office.bunsho.v2",1);r.onsuccess=()=>{let d=r.result,t=d.transaction("records","readonly"),g=t.objectStore("records").get('''+json.dumps(key)+''');g.onsuccess=()=>resolve(g.result||null);g.onerror=()=>reject(Error("get"));t.oncomplete=()=>d.close()};r.onerror=()=>reject(Error("open"))})''',True)
 def click(selector):
  r=ev('(()=>{let r=document.querySelector('+json.dumps(selector)+').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()')
  for typ in ('mousePressed','mouseReleased'):pipe.call('Input.dispatchMouseEvent',{'type':typ,'x':r['x'],'y':r['y'],'button':'left','clickCount':1},s)
 def select(path):
  ev('document.getElementById("backup-file").value=""');pipe.call('DOM.enable',{},s);root=pipe.call('DOM.getDocument',{},s)['root']['nodeId'];node=pipe.call('DOM.querySelector',{'nodeId':root,'selector':'#backup-file'},s)['nodeId'];pipe.call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(path)]},s)
 wait('document.querySelector("[data-k=title]") !== null','initial')
 ev('(()=>{let e=document.querySelector("[data-k=title]");e.value="以前";e.dispatchEvent(new Event("input",{bubbles:true}))})()');wait('document.getElementById("status").textContent === "保存しました"','baseline');before=state()
 select(out/'invalid.json');wait('document.getElementById("status").textContent.includes("読み込めません")','invalid title refusal')
 if state()!=before:raise ValueError('invalid import changed state')
 select(out/'legacy.json');wait('document.getElementById("backup-dialog").open','preview')
 if ev('document.querySelector("#backup-preview [data-k=title]")?.value')!='' or state()!=before:raise ValueError('preview changed state')
 click('#backup-cancel');wait('!document.getElementById("backup-dialog").open','cancel')
 if state()!=before:raise ValueError('cancel changed state')
 select(out/'legacy.json');wait('document.getElementById("backup-dialog").open','confirm preview');click('#backup-confirm');wait('document.getElementById("status").textContent.includes("復元しました")','commit')
 current=state();backup=state('backup:'+str(before['revision']).zfill(16))
 if current['revision']!=before['revision']+1 or raw not in current['value'] or backup!=before:raise ValueError('missing provenance or backup')
 ev('window.__beforeReload=true');pipe.call('Page.reload',{},s);wait('window.__beforeReload!==true && document.querySelector("[data-k=b0]")?.value === "本文😀"','reload')
 if ev('document.querySelector("[data-k=title]").value')!='':raise ValueError('missing title not preserved as empty')
 pipe.call('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':str(out/'downloads')});click('[data-k="backup-original"]')
 dest=out/'downloads/bunsho-legacy-original.json';end=time.monotonic()+60
 while time.monotonic()<end and not dest.exists():time.sleep(.1)
 if not dest.exists() or dest.read_text()!=raw:raise ValueError('original export mismatch')
 report={'status':'PASS_UNTITLED_LEGACY_UI_SYNTHETIC','buildReceiptSha256':sha(build/'build-receipt.json'),'observerSha256':sha(Path(__file__)),'inputSha256':sha(out/'legacy.json'),'checks':['null-title-refused','preview-cancel','explicit-import','prior-backup','reload','exact-original-export'],'scope':'Synthetic documentsGet response only; no real data, actual old-origin fetch, QEMU or release.'}
 (out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'],flush=True)
finally:
 pipe.close();server.shutdown();server.server_close()
