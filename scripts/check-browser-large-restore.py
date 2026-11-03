#!/usr/bin/env python3
"""Test a 32-block valid Bunsho restore with synthetic Chrome input.

Usage: script AMU BUILD OUT CHROME expect-success|expect-refusal [BLOCK_BYTES [bs2]]
The test only covers a bounded synthetic fixture, not production data.
"""
import functools,http.server,importlib.util,json,sys,threading,time
from pathlib import Path
if len(sys.argv) not in (6,7,8):raise SystemExit(__doc__)
amu,build,out,chrome=map(lambda s:Path(s).resolve(),sys.argv[1:5]);mode=sys.argv[5]
if mode not in ('expect-success','expect-refusal'):raise ValueError('mode')
block_bytes=int(sys.argv[6]) if len(sys.argv)>=7 else 1024
legacy=len(sys.argv)==8 and sys.argv[7]=='bs2'
if len(sys.argv)==8 and not legacy:raise SystemExit(__doc__)
if not 1<=block_bytes<=1024:raise ValueError('block bytes')
out.mkdir(parents=True,exist_ok=False);(out/'profile').mkdir()
def frame(x):return str(len(x.encode()))+':'+x
title='旧文書' if legacy else '題'*341+'x'
count=16 if legacy else 32
if legacy:
 body=[{'elementId':'e'+str(i),'kind':'paragraph','text':'x'*block_bytes} for i in range(count)]
 raw=json.dumps({'found':True,'document':{'documentId':'doc-1','title':title,'revisionId':'r1','body':body}},ensure_ascii=False,separators=(',',':'))
 state='BS2|'+''.join(map(frame,[raw,title,'edit',str(count)]+sum((['p','x'*block_bytes,'e'+str(i)] for i in range(count)),[])))
else:
 state='BS3|1'+''.join(map(frame,[title,'edit',str(count)]+sum((['p','x'*block_bytes] for _ in range(count)),[])))
if len(state.encode())>35000:raise ValueError('fixture too large')
fixture=out/'large.bs3';fixture.write_text(state,encoding='utf8')
spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py');browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(build)));threading.Thread(target=server.serve_forever,daemon=True).start();pipe=browser.Pipe(str(chrome),out/'profile')
try:
 t=pipe.call('Target.createTarget',{'url':'about:blank'})['targetId'];s=pipe.call('Target.attachToTarget',{'targetId':t,'flatten':True})['sessionId'];pipe.call('Page.enable',{},s);pipe.call('Page.navigate',{'url':f'http://127.0.0.1:{server.server_port}/index.html'},s)
 def ev(x,awaited=False):
  r=pipe.call('Runtime.evaluate',{'expression':x,'returnByValue':True,'awaitPromise':awaited},s)
  if 'exceptionDetails' in r:raise ValueError(r['exceptionDetails'])
  return r.get('result',{}).get('value')
 def wait(x,label):
  end=time.time()+90
  while time.time()<end:
   try:
    if ev(x):return
   except RuntimeError as e:
    if not any(y in str(e) for y in ('Execution context was destroyed','Cannot find context')):raise
   time.sleep(.1)
  raise TimeoutError(label+': '+str(ev('document.getElementById("status")?.textContent')))
 def stored(key='current'):return ev('''new Promise((resolve,reject)=>{let o=indexedDB.open('itonami.office.bunsho.v2',1);o.onsuccess=()=>{let d=o.result,t=d.transaction('records'),g=t.objectStore('records').get(KEY);g.onsuccess=()=>resolve(g.result||null);t.oncomplete=()=>d.close()};o.onerror=()=>reject(Error('open'))})'''.replace('KEY',json.dumps(key)),True)
 wait('document.querySelector("[data-k=b0]")!==null','initial');ev('(()=>{let e=document.querySelector("[data-k=b0]");e.value="先に保存";e.dispatchEvent(new Event("input",{bubbles:true}))})()');wait('document.getElementById("status").textContent==="保存しました"','baseline');baseline=stored()
 pipe.call('DOM.enable',{},s);root=pipe.call('DOM.getDocument',{},s)['root']['nodeId'];node=pipe.call('DOM.querySelector',{'nodeId':root,'selector':'#backup-file'},s)['nodeId'];pipe.call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(fixture)]},s)
 wait('document.getElementById("backup-dialog").open || document.getElementById("status").textContent.includes("読み込めません")','preview')
 if mode=='expect-refusal':
  assert not ev('document.getElementById("backup-dialog").open') and stored()==baseline
  report={'status':'PASS_LARGE_PREVIOUS_REFUSAL','snapshotBytes':len(state.encode()),'previousStatePreserved':True}
 else:
  assert ev('document.getElementById("backup-dialog").open') and stored()==baseline
  assert ev('document.querySelector("#backup-preview [data-k=b'+str(count-1)+']")?.value.length')==block_bytes
  ev('document.getElementById("backup-confirm").click()');wait('document.getElementById("status").textContent.includes("復元しました")','restore');restored=stored();assert restored['revision']==baseline['revision']+1 and len(restored['value'].encode())<=35000
  assert stored('backup:'+str(baseline['revision']).zfill(16))==baseline
  assert ev('document.querySelector("[data-k=b'+str(count-1)+']")?.value.length')==block_bytes
  ev('document.getElementById("status").textContent="待機";(()=>{let e=document.querySelector("[data-k=b'+str(count-1)+']");e.value="最後の編集";e.dispatchEvent(new Event("input",{bubbles:true}))})()');wait('document.getElementById("status").textContent==="保存しました"','edit last block');saved=stored();assert '最後の編集' in saved['value']
  if legacy and raw not in saved['value']:raise ValueError('legacy source changed after edit')
  ev('window.__old=true');pipe.call('Page.reload',{},s);wait('window.__old!==true && document.querySelector("[data-k=b'+str(count-1)+']")?.value==="最後の編集"','reload');assert stored()==saved
  report={'status':'PASS_LARGE_RESTORE_EDIT_RELOAD','snapshotBytes':len(state.encode()),'blocks':count,'blockBytes':block_bytes,'format':'BS2' if legacy else 'BS3','previousStateBackedUp':True}
 (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(report['status'],flush=True)
finally:pipe.close();server.shutdown();server.server_close()
