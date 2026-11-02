#!/usr/bin/env python3
"""Verify BS3 downgrade refusal and BS1 multiline preservation on loopback.

Usage: python3 scripts/check-multiline-compat.py AMU_DIR NEW_BUILD OLD_BUILD OUTPUT_DIR CHROME
Synthetic data only; old candidate and current candidate share one isolated origin.
"""
import functools, http.server, importlib.util, json, shutil, sys, threading, time
from pathlib import Path

if len(sys.argv) != 6: raise SystemExit(__doc__)
amu,new,old,out,chrome = map(lambda s:Path(s).resolve(),sys.argv[1:])
out.mkdir(parents=True,exist_ok=False); (out/'profile').mkdir()
shutil.copytree(new,out/'new'); shutil.copytree(old,out/'old')
spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py')
browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*args): pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(out)))
threading.Thread(target=server.serve_forever,daemon=True).start();pipe=browser.Pipe(str(chrome),out/'profile')
key='itonami.bunsho.candidate.bs1'; base=f'http://127.0.0.1:{server.server_port}/'
try:
 target=pipe.call('Target.createTarget',{'url':'about:blank'})['targetId'];session=pipe.call('Target.attachToTarget',{'targetId':target,'flatten':True})['sessionId']
 pipe.call('Network.enable',{},session);pipe.call('Page.enable',{},session)
 def ev(expr):
  r=pipe.call('Runtime.evaluate',{'expression':expr,'returnByValue':True},session)
  if 'exceptionDetails' in r: raise ValueError(r['exceptionDetails'])
  return r.get('result',{}).get('value')
 def wait(expr,label):
  until=time.time()+90
  while time.time()<until:
   try:
    if ev(expr): return
   except RuntimeError as e:
    if not any(x in str(e) for x in ('Execution context was destroyed','Cannot find context with specified id','Inspected target navigated or closed')): raise
   time.sleep(.2)
  raise TimeoutError(label+': '+str(ev("document.getElementById('status')?.textContent")))
 def navigate(path):
  pipe.call('Page.navigate',{'url':base+path+'/index.html'},session)
 def input_(key_,text):
  ev("(()=>{const x=document.querySelector('[data-k="+key_+"]');x.value="+json.dumps(text,ensure_ascii=False)+";x.dispatchEvent(new Event('input',{bubbles:true}));})()")
 navigate('new');wait("document.querySelector('[data-k=b0]')?.tagName==='TEXTAREA'",'new initial')
 text='最初😀\n第二行';input_('b0',text)
 wait("localStorage.getItem("+json.dumps(key)+")?.startsWith('BS3|1') && document.getElementById('status').textContent==='保存しました'",'multiline saved')
 saved=ev('localStorage.getItem('+json.dumps(key)+')')
 navigate('old');wait("document.getElementById('status')?.textContent.includes('開けません')",'old rejects BS3')
 if ev('localStorage.getItem('+json.dumps(key)+')') != saved or ev("document.querySelector('[data-k=b0]') !== null"): raise ValueError('old editor accepted or modified BS3')
 navigate('new');wait("document.querySelector('[data-k=b0]')?.value === "+json.dumps(text,ensure_ascii=False),'new reopens')
 if ev('localStorage.getItem('+json.dumps(key)+')') != saved: raise ValueError('new reopen changed bytes')
 # Legacy snapshots are protected before editing, without clobbering a
 # concurrent change or a failed localStorage write.
 legacy='BS1|'+saved[5:];ev('localStorage.setItem('+json.dumps(key)+','+json.dumps(legacy,ensure_ascii=False)+')')
 foreign=saved
 race_script="window.originalGet=Storage.prototype.getItem;window.originalSet=Storage.prototype.setItem;window.readCount=0;Storage.prototype.getItem=function(k){if(this===localStorage && k==="+json.dumps(key)+" && ++window.readCount===2)window.originalSet.call(this,k,"+json.dumps(foreign,ensure_ascii=False)+");return window.originalGet.call(this,k)}"
 racing=pipe.call('Page.addScriptToEvaluateOnNewDocument',{'source':race_script},session)['identifier']
 navigate('new');wait("document.getElementById('status')?.textContent.includes('開けません')",'protection conflict refusal')
 if ev('localStorage.getItem('+json.dumps(key)+')')!=foreign or ev("document.querySelector('[data-k=b0]') !== null"):raise ValueError('concurrent value changed')
 pipe.call('Page.removeScriptToEvaluateOnNewDocument',{'identifier':racing},session);ev('localStorage.setItem('+json.dumps(key)+','+json.dumps(legacy,ensure_ascii=False)+')')
 quota=pipe.call('Page.addScriptToEvaluateOnNewDocument',{'source':"window.originalSet=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(this===localStorage && k==="+json.dumps(key)+")throw Error('quota');return window.originalSet.call(this,k,v)}"},session)['identifier']
 navigate('new');wait("document.getElementById('status')?.textContent.includes('開けません')",'protection write refusal')
 if ev('localStorage.getItem('+json.dumps(key)+')')!=legacy or ev("document.querySelector('[data-k=b0]') !== null"):raise ValueError('failed protection altered data')
 pipe.call('Page.removeScriptToEvaluateOnNewDocument',{'identifier':quota},session);navigate('new')
 wait("document.querySelector('[data-k=b0]')?.value === "+json.dumps(text,ensure_ascii=False)+" && localStorage.getItem("+json.dumps(key)+")?.startsWith('BS3|1')",'legacy multiline protected')
 protected=ev('localStorage.getItem('+json.dumps(key)+')');navigate('old');wait("document.getElementById('status')?.textContent.includes('開けません')",'old refuses protected')
 if ev('localStorage.getItem('+json.dumps(key)+')')!=protected:raise ValueError('old changed protected state')
 navigate('new');wait("document.querySelector('[data-k=b0]')?.value === "+json.dumps(text,ensure_ascii=False),'protected reopens')
 input_('title','編集後');wait("localStorage.getItem("+json.dumps(key)+")?.startsWith('BS3|1') && document.getElementById('status').textContent==='保存しました'",'legacy upgrade')
 if ev("document.querySelector('[data-k=b0]')?.value") != text: raise ValueError('legacy line breaks lost')
 # Textarea/input normalization must not silently alter persisted CR bytes.
 current=ev('localStorage.getItem('+json.dumps(key)+')');assert text in current
 cr=current.replace(text,text.replace('\n','\r'),1);ev('localStorage.setItem('+json.dumps(key)+','+json.dumps(cr,ensure_ascii=False)+')');navigate('new')
 wait("document.getElementById('status')?.textContent.includes('開けません')",'CR refusal')
 if ev('localStorage.getItem('+json.dumps(key)+')')!=cr: raise ValueError('CR snapshot overwritten')
 # A legacy JSON paragraph with LF is imported as provenance-preserving BS3|2.
 legacy_json=json.dumps({'found':True,'document':{'documentId':'old','title':'旧','revisionId':'r1','body':[{'elementId':'e1','kind':'paragraph','text':'一行\n二行'}]}},ensure_ascii=True,separators=(',',':'))
 legacy_file=out/'legacy.json';legacy_file.write_text(legacy_json,encoding='utf-8')
 ev('localStorage.removeItem('+json.dumps(key)+')');navigate('new');wait("document.querySelector('[data-k=b0]') !== null",'blank after CR')
 pipe.call('DOM.enable',{},session);doc=pipe.call('DOM.getDocument',{},session)['root']['nodeId'];node=pipe.call('DOM.querySelector',{'nodeId':doc,'selector':'#backup-file'},session)['nodeId']
 pipe.call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(legacy_file)]},session);wait("document.getElementById('backup-dialog').open",'legacy preview')
 ev("document.getElementById('status').textContent='確認待ち';document.getElementById('backup-confirm').click()");wait("document.getElementById('status').textContent === 'バックアップから復元しました。'",'legacy import')
 imported=ev('localStorage.getItem('+json.dumps(key)+')')
 if not imported.startswith('BS3|2') or ev("document.querySelector('[data-k=b0]')?.value")!='一行\n二行':raise ValueError('multiline legacy import')
 data=imported.encode('utf-8');pos=5;fields=[]
 while pos<len(data):
  end=data.index(b':',pos);size=int(data[pos:end]);pos=end+1;fields.append(data[pos:pos+size].decode('utf-8'));pos+=size
 if fields != [legacy_json,'旧','edit','1','p','一行\n二行','e1']:raise ValueError('legacy provenance or identity changed')
 navigate('old');wait("document.getElementById('status')?.textContent.includes('開けません')",'old rejects BS3 legacy')
 if ev('localStorage.getItem('+json.dumps(key)+')')!=imported:raise ValueError('old editor modified legacy')
 navigate('new');wait("document.querySelector('[data-k=b0]')?.value === "+json.dumps("一行\n二行",ensure_ascii=False),'legacy reopens')
 # Existing BS2 state and explicitly imported BS2 backup are both protected.
 bs2='BS2|'+imported[5:];ev('localStorage.setItem('+json.dumps(key)+','+json.dumps(bs2,ensure_ascii=False)+')');navigate('new')
 wait("document.querySelector('[data-k=b0]')?.value === "+json.dumps("一行\n二行",ensure_ascii=False)+" && localStorage.getItem("+json.dumps(key)+")?.startsWith('BS3|2')",'BS2 auto-protected')
 if ev('localStorage.getItem('+json.dumps(key)+')')!=imported:raise ValueError('BS2 provenance changed')
 backup=out/'old.bs2';backup.write_text(bs2);doc=pipe.call('DOM.getDocument',{},session)['root']['nodeId'];node=pipe.call('DOM.querySelector',{'nodeId':doc,'selector':'#backup-file'},session)['nodeId']
 pipe.call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(backup)]},session);wait("document.getElementById('backup-dialog').open",'BS2 backup preview')
 ev("document.getElementById('status').textContent='確認待ち';document.getElementById('backup-confirm').click()");wait("document.getElementById('status').textContent === 'バックアップから復元しました。'",'BS2 backup import')
 if ev('localStorage.getItem('+json.dumps(key)+')')!=imported:raise ValueError('BS2 backup not protected')
 # Newlines only in the original JSON provenance must not force a rewrite.
 pretty=json.dumps({'found':True,'document':{'documentId':'old','title':'旧','revisionId':'r1','body':[{'elementId':'e1','kind':'paragraph','text':'一行'}]}},ensure_ascii=False,indent=2)
 pretty_file=out/'pretty.json';pretty_file.write_text(pretty)
 ev("document.getElementById('backup-file').value=''");doc=pipe.call('DOM.getDocument',{},session)['root']['nodeId'];node=pipe.call('DOM.querySelector',{'nodeId':doc,'selector':'#backup-file'},session)['nodeId']
 pipe.call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(pretty_file)]},session);wait("document.getElementById('backup-dialog').open",'pretty JSON preview')
 ev("document.getElementById('status').textContent='確認待ち';document.getElementById('backup-confirm').click()");wait("document.getElementById('status').textContent === 'バックアップから復元しました。'",'pretty JSON import')
 pretty_saved=ev('localStorage.getItem('+json.dumps(key)+')')
 if not pretty_saved.startswith('BS2|') or pretty not in pretty_saved:raise ValueError('pretty provenance missing')
 quota=pipe.call('Page.addScriptToEvaluateOnNewDocument',{'source':"window.originalSet=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(this===localStorage && k==="+json.dumps(key)+")throw Error('quota');return window.originalSet.call(this,k,v)}"},session)['identifier']
 navigate('new');wait("document.querySelector('[data-k=b0]')?.value === '一行'",'provenance-only newline reopen')
 if ev('localStorage.getItem('+json.dumps(key)+')')!=pretty_saved:raise ValueError('provenance-only state rewritten')
 pipe.call('Page.removeScriptToEvaluateOnNewDocument',{'identifier':quota},session)
 requests=[e['params']['request']['url'] for e in pipe.events if e.get('method')=='Network.requestWillBeSent']
 if not requests or any(not x.startswith(base) for x in requests):raise ValueError('unexpected request')
 (out/'result.json').write_text(json.dumps({'status':'PASS','checks':['BS3 old editor refuses without write','new editor reopens exact text','BS1 auto-protection, conflict and failed write','CR normalization refusal','legacy provenance, BS2 auto-protection and backup','provenance-only newline no rewrite','loopback only'],'scope':'synthetic candidate, no real-user migration or release'},ensure_ascii=False,indent=2)+'\n')
 print('PASS_BUNSHO_MULTILINE_COMPAT')
finally:
 pipe.close();server.shutdown();server.server_close()
