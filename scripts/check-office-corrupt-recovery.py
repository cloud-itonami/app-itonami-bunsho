#!/usr/bin/env python3
"""Synthetic Chromium test of non-destructive recovery of damaged record metadata.

Usage: script AMU BUILD OUTPUT CHROME APP
APP is bunsho, hyokeisan, or zuhyo. This tests no real user data or release.
"""
import functools,http.server,importlib.util,json,sys,threading,time
from pathlib import Path
if len(sys.argv)!=6:raise SystemExit(__doc__)
amu,build,out,chrome=map(lambda s:Path(s).resolve(),sys.argv[1:5]);app=sys.argv[5]
field={'bunsho':'b0','hyokeisan':'c0','zuhyo':'body'}[app]
out.mkdir(parents=True,exist_ok=False);(out/'profile').mkdir();(out/'downloads').mkdir()
spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py');browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(build)));threading.Thread(target=server.serve_forever,daemon=True).start();pipe=browser.Pipe(str(chrome),out/'profile');s=None
try:
 t=pipe.call('Target.createTarget',{'url':'about:blank'})['targetId'];s=pipe.call('Target.attachToTarget',{'targetId':t,'flatten':True})['sessionId'];pipe.call('Page.enable',{},s);pipe.call('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':str(out/'downloads')});pipe.call('Page.navigate',{'url':f'http://127.0.0.1:{server.server_port}/index.html'},s)
 def ev(x,wait=False):
  r=pipe.call('Runtime.evaluate',{'expression':x,'returnByValue':True,'awaitPromise':wait},s)
  if 'exceptionDetails' in r:raise ValueError(r['exceptionDetails'])
  return r.get('result',{}).get('value')
 def wait(x,label):
  until=time.time()+60
  while time.time()<until:
   try:
    if ev(x):return
   except RuntimeError as e:
    if not any(y in str(e) for y in ('Execution context was destroyed','Cannot find context')):raise
   time.sleep(.1)
  raise TimeoutError(label+': '+str(ev('document.getElementById("status")?.textContent')))
 selector='[data-k='+field+']';wait('document.querySelector('+json.dumps(selector)+')!==null','initial')
 ev('(()=>{let e=document.querySelector('+json.dumps(selector)+');e.value="破損前の内容😀";e.dispatchEvent(new Event("input",{bubbles:true}))})()')
 wait('document.getElementById("status").textContent==="保存しました"','save')
 db=json.dumps('itonami.office.'+app+'.v2')
 mutation='''new Promise((resolve,reject)=>{const o=indexedDB.open(__DB_NAME__,1);o.onerror=()=>reject(Error('open'));o.onsuccess=()=>{let d=o.result,t=d.transaction('records','readwrite'),s=t.objectStore('records'),g=s.get('current');g.onsuccess=()=>{let x=g.result;x.format='damaged-format';s.put(x,'current')};t.oncomplete=()=>{d.close();resolve(true)};t.onabort=()=>reject(Error('abort'))}})'''.replace('__DB_NAME__',db)
 assert ev(mutation,True)
 ev('window.__old=true');pipe.call('Page.reload',{},s);wait('window.__old!==true && !document.getElementById("storage-conflict").hidden','corrupt refusal')
 assert ev('document.querySelector("#app [data-k]")===null')
 ev('document.getElementById("export-current-conflict").click()')
 expected=out/'downloads'/(app+'-current-recovery.txt');until=time.time()+8
 while time.time()<until and not expected.exists():time.sleep(.1)
 if not expected.exists():raise ValueError('surviving state could not be exported: '+str(ev('document.getElementById("status").textContent')))
 content=expected.read_text();assert '破損前の内容😀' in content
 # The export is read-only and leaves the damaged record untouched.
 read='''new Promise((resolve,reject)=>{let o=indexedDB.open(__DB_NAME__,1);o.onsuccess=()=>{let d=o.result,t=d.transaction('records'),g=t.objectStore('records').get('current');g.onsuccess=()=>resolve(g.result);t.oncomplete=()=>d.close()};o.onerror=()=>reject(Error('open'))})'''.replace('__DB_NAME__',db)
 record=ev(read,True);assert record['format']=='damaged-format' and record['value']==content
 # Preserve isolated UTF-16 surrogates via a JSON-string envelope instead of
 # letting Blob's UTF-8 encoder replace them with U+FFFD.
 bad=mutation.replace("x.format='damaged-format';", "x.format='damaged-format';x.value=String.fromCharCode(0xd800)+'X';")
 assert ev(bad,True)
 ev('document.getElementById("export-current-conflict").click()')
 encoded=out/'downloads'/(app+'-current-recovery.txt.json');until=time.time()+8
 while time.time()<until and not encoded.exists():time.sleep(.1)
 if not encoded.exists():raise ValueError('invalid Unicode recovery missing')
 payload=json.loads(encoded.read_text());assert payload['encoding']=='json-string-utf16' and payload['value']=='\ud800X'
 assert ev(read,True)['value']=='\ud800X'
 result={'status':'PASS_CORRUPT_METADATA_RECOVERY','app':app,'checks':['invalid-record-refused','surviving-text-exported','stored-record-unchanged','invalid-utf16-export-preserved'],'scope':'synthetic Chromium loopback, damaged record metadata only; no physical crash or real user data'};(out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(result['status'],app,flush=True)
finally:
 pipe.close();server.shutdown();server.server_close()
