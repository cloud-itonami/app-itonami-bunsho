#!/usr/bin/env python3
"""Test explicit file transfer between two synthetic browser origins.

Usage: APP AMU SOURCE_BUILD DEST_BUILD NEW_OUTPUT CHROME
No real origin, user data, vault, remote endpoint or release is touched.
"""
import hashlib, http.server, importlib.util, json, sys, threading, time
from pathlib import Path
if len(sys.argv) != 7 or sys.argv[1] not in ('bunsho', 'hyokeisan', 'zuhyo'):
    raise SystemExit(__doc__)
app = sys.argv[1]
amu, source, dest, out, chrome = (Path(p).resolve() for p in sys.argv[2:])
out.mkdir(parents=True, mode=0o700, exist_ok=False)
(out/'profile').mkdir(mode=0o700)
(out/'downloads').mkdir(mode=0o700)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
field = {'bunsho':'b0', 'hyokeisan':'c0', 'zuhyo':'body'}[app]
dbname = f'itonami.office.{app}.v2'
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
def server(directory):
    import functools
    s = http.server.ThreadingHTTPServer(('127.0.0.1',0), functools.partial(Quiet,directory=str(directory)))
    threading.Thread(target=s.serve_forever,daemon=True).start()
    return s
old_server, new_server = server(source), server(dest)
spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py')
browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
pipe=browser.Pipe(str(chrome),out/'profile')
try:
    def tab(port):
        t=pipe.call('Target.createTarget',{'url':'about:blank'})['targetId']
        s=pipe.call('Target.attachToTarget',{'targetId':t,'flatten':True})['sessionId']
        pipe.call('Page.enable',{},s)
        pipe.call('Page.navigate',{'url':f'http://127.0.0.1:{port}/index.html'},s)
        return s
    def ev(s,expr,awaited=False):
        r=pipe.call('Runtime.evaluate',{'expression':expr,'returnByValue':True,'awaitPromise':awaited},s)
        if 'exceptionDetails' in r: raise ValueError(r['exceptionDetails'])
        return r.get('result',{}).get('value')
    def wait(s,expr,label):
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            try:
                if ev(s,expr): return
            except RuntimeError as error:
                if not any(x in str(error) for x in ('Execution context was destroyed','Cannot find context with specified id')): raise
            time.sleep(.1)
        raise TimeoutError(label+': '+str(ev(s,'document.getElementById("status")?.textContent')))
    def state(s,key='current'):
        return ev(s,'''new Promise((resolve,reject)=>{const r=indexedDB.open('''+json.dumps(dbname)+''',1);r.onsuccess=()=>{const d=r.result,t=d.transaction("records","readonly"),g=t.objectStore("records").get('''+json.dumps(key)+''');g.onsuccess=()=>resolve(g.result||null);g.onerror=()=>reject(Error("get"));t.oncomplete=()=>d.close()};r.onerror=()=>reject(Error("open"))})''',True)
    selector='[data-k="'+field+'"]'
    def enter(s,value):
        ev(s,'(()=>{let e=document.querySelector('+json.dumps(selector)+');e.value='+json.dumps(value,ensure_ascii=False)+';e.dispatchEvent(new Event("input",{bubbles:true}))})()')
    def click(s,selector):
        rect=ev(s,'(()=>{let r=document.querySelector('+json.dumps(selector)+').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()')
        for typ in ('mousePressed','mouseReleased'):
            pipe.call('Input.dispatchMouseEvent',{'type':typ,'x':rect['x'],'y':rect['y'],'button':'left','clickCount':1},s)
    def select_file(s,path):
        pipe.call('DOM.enable',{},s)
        doc=pipe.call('DOM.getDocument',{},s)['root']['nodeId']
        node=pipe.call('DOM.querySelector',{'nodeId':doc,'selector':'#backup-file'},s)['nodeId']
        pipe.call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(path)]},s)
    a=tab(old_server.server_port);b=tab(new_server.server_port)
    for s in (a,b): wait(s,'document.querySelector('+json.dumps(selector)+') !== null','initial app')
    enter(a,'旧場所😀');wait(a,'document.getElementById("status").textContent === "保存しました"','source save')
    old_state=state(a)
    enter(b,'移行前😀');wait(b,'document.getElementById("status").textContent === "保存しました"','destination save')
    prior=state(b)
    if old_state['revision']!=1 or prior['revision']!=1: raise ValueError('fixture not saved')
    pipe.call('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':str(out/'downloads')})
    click(a,'[data-k="backup-export"]')
    end=time.monotonic()+90;files=[]
    while time.monotonic()<end:
        files=[p for p in (out/'downloads').iterdir() if p.is_file() and not p.name.endswith('.crdownload')]
        if len(files)==1 and files[0].stat().st_size: break
        time.sleep(.1)
    if len(files)!=1 or files[0].read_text()!=old_state['value']: raise ValueError('export differs from source snapshot')
    exported=files[0]
    select_file(b,exported);wait(b,'document.getElementById("backup-dialog").open','preview')
    if state(b)!=prior or state(a)!=old_state: raise ValueError('preview modified storage')
    click(b,'#backup-cancel');wait(b,'!document.getElementById("backup-dialog").open','cancel')
    if state(b)!=prior or state(a)!=old_state: raise ValueError('cancel modified storage')
    ev(b,'document.getElementById("backup-file").value=""')
    select_file(b,exported);wait(b,'document.getElementById("backup-dialog").open','second preview')
    click(b,'#backup-confirm');wait(b,'document.getElementById("status").textContent.includes("復元しました")','restore')
    restored=state(b);backup=state(b,'backup:'+str(prior['revision']).zfill(16))
    if restored['revision']!=2 or restored['value']!=old_state['value'] or backup!=prior or state(a)!=old_state:
        raise ValueError('transfer or backup mismatch')
    ev(b,'window.__beforeReload=true');pipe.call('Page.reload',{},b)
    wait(b,'window.__beforeReload!==true && document.querySelector('+json.dumps(selector)+')?.value === "旧場所😀"','destination reload')
    report={'status':'PASS_SYNTHETIC_ORIGIN_TRANSFER','app':app,'sourceBuildReceiptSha256':sha(source/'build-receipt.json'),
            'destinationBuildReceiptSha256':sha(dest/'build-receipt.json'),'observerSha256':sha(Path(__file__)),
            'exportSha256':sha(exported),'checks':['source-export-exact','separate-origin','preview-and-cancel-preserve-both',
            'explicit-import','destination-backup','source-preserved','destination-reload'],
            'scope':'Synthetic loopback origins and data only; not actual legacy formats, production, crash/power-loss, QEMU or release.'}
    (out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['status'],app,flush=True)
finally:
    pipe.close()
    for s in (old_server,new_server): s.shutdown();s.server_close()
