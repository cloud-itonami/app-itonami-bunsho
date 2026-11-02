#!/usr/bin/env python3
"""Check three built office candidates through an offline loopback Kubo gateway.

Usage: check-office-cid-candidates.py AMU BUNSHO_BUILD HYOKEISAN_BUILD ZUHYO_BUILD OUT CHROME
This isolated candidate test does not pin publicly, exercise DNS/TLS or qualify release.
"""
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from office_candidate_integrity import validate, candidate_files

if len(sys.argv) != 7: raise SystemExit(__doc__)
amu,bunsho,hyokeisan,zuhyo,out,chrome = map(lambda s:Path(s).resolve(),sys.argv[1:])
out.mkdir(parents=True,exist_ok=False)
env=os.environ.copy();env['IPFS_PATH']=str(out/'ipfs')
def run(*args):
 return subprocess.run(['ipfs',*map(str,args)],env=env,text=True,check=True,capture_output=True).stdout.strip()
def port():
 with socket.socket() as s:
  s.bind(('127.0.0.1',0));return s.getsockname()[1]
def sha(data):return hashlib.sha256(data).hexdigest()
run('init','--profile=test')
gateway,api=port(),port()
config_file=out/'ipfs/config';cfg=json.loads(config_file.read_text())
cfg['Addresses']['Swarm']=[];cfg['Addresses']['Gateway']=f'/ip4/127.0.0.1/tcp/{gateway}';cfg['Addresses']['API']=f'/ip4/127.0.0.1/tcp/{api}'
cfg['Bootstrap']=[];cfg['Discovery']['MDNS']['Enabled']=False;cfg['Routing']['Type']='none';cfg['Gateway']['NoFetch']=True;cfg['Gateway']['NoDNSLink']=True
config_file.write_text(json.dumps(cfg))
builds={'bunsho':bunsho,'hyokeisan':hyokeisan,'zuhyo':zuhyo};results={}
for name,build in builds.items():
 receipt=validate(build,name)
 cid=run('add','-Qr','--hidden','--cid-version=1','--raw-leaves=true','--chunker=size-262144','--hash=sha2-256','--pin=false',build).splitlines()[-1]
 results[name]={'cid':cid,'build':receipt,'files':{}}
log=(out/'daemon.log').open('wb');proc=subprocess.Popen(['ipfs','daemon','--offline'],env=env,stdout=log,stderr=subprocess.STDOUT)
try:
 for _ in range(200):
  try:
   with urllib.request.urlopen(f'http://127.0.0.1:{gateway}/ipfs/{results["bunsho"]["cid"]}/index.html',timeout=1) as r:r.read()
   break
  except Exception:
   if proc.poll() is not None:raise RuntimeError('offline Kubo exited')
   time.sleep(.1)
 else:raise RuntimeError('gateway not ready')
 for name,build in builds.items():
  base=f'http://127.0.0.1:{gateway}/ipfs/{results[name]["cid"]}/'
  for file in candidate_files(build):
   with urllib.request.urlopen(base+file.relative_to(build).as_posix(),timeout=10) as response:data=response.read()
   if data!=file.read_bytes():raise ValueError(name+' gateway mismatch '+file.name)
   results[name]['files'][file.relative_to(build).as_posix()]=sha(data)
  results[name]['base']=base
 spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py');browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
 for name in builds:
  profile=out/(name+'-profile');profile.mkdir();pipe=browser.Pipe(str(chrome),profile)
  try:
   target=pipe.call('Target.createTarget',{'url':'about:blank'})['targetId'];session=pipe.call('Target.attachToTarget',{'targetId':target,'flatten':True})['sessionId']
   pipe.call('Network.enable',{},session);pipe.call('Page.enable',{},session);pipe.call('Page.navigate',{'url':results[name]['base']+'index.html'},session);pipe.call('Page.bringToFront',{},session)
   def ev(expr,awaited=False):
    r=pipe.call('Runtime.evaluate',{'expression':expr,'returnByValue':True,'awaitPromise':awaited},session)
    if 'exceptionDetails' in r:raise ValueError(r['exceptionDetails'])
    return r.get('result',{}).get('value')
   def wait(expr,label):
    until=time.time()+90
    while time.time()<until:
     try:
      if ev(expr):return
     except RuntimeError as e:
      if not any(x in str(e) for x in ('Execution context was destroyed','Cannot find context with specified id','Inspected target navigated or closed')):raise
     time.sleep(.2)
    raise TimeoutError(name+' '+label+': '+str(ev("document.getElementById('status')?.textContent")))
   field={'bunsho':'title','hyokeisan':'c0','zuhyo':'body'}[name]
   value={'bunsho':'CID 文書😀','hyokeisan':'=3/2','zuhyo':'CID 一行\n二行😀'}[name]
   key={'bunsho':'itonami.bunsho.candidate.bs1','hyokeisan':'itonami.hyokeisan.candidate.hs1','zuhyo':'itonami.zuhyo.candidate.zs1'}[name]
   selector='[data-k='+field+']';wait('document.querySelector('+json.dumps(selector)+') !== null','initial')
   ev('(()=>{let e=document.querySelector('+json.dumps(selector)+');e.value='+json.dumps(value,ensure_ascii=False)+";e.dispatchEvent(new Event('input',{bubbles:true}))})()")
   idb=json.loads((builds[name]/'client-runtime.json').read_text())['local-state']['adapter']=='indexeddb'
   def read_saved():
    if not idb:return ev('localStorage.getItem('+json.dumps(key)+')')
    return ev('new Promise((resolve,reject)=>{const r=indexedDB.open('+json.dumps('itonami.office.'+name+'.v2')+',1);r.onsuccess=()=>{const d=r.result,t=d.transaction("records","readonly"),g=t.objectStore("records").get("current");g.onsuccess=()=>resolve(g.result?.value??null);g.onerror=()=>reject(Error("read"));t.oncomplete=()=>d.close()};r.onerror=()=>reject(Error("open"))})',True)
   wait("document.getElementById('status').textContent==='保存しました'",'save')
   saved=read_saved()
   if not isinstance(saved,str) or value not in saved:raise ValueError(name+' saved value missing')
   if name=='hyokeisan':wait("document.querySelector('[data-k=c0]')?.parentElement.querySelector('.value')?.textContent==='1.5'",'decimal result')
   if name=='zuhyo' and not saved.startswith('ZS2|'):raise ValueError('multiline version missing')
   ev('window.__oldDocument=true');pipe.call('Page.reload',{},session)
   wait('window.__oldDocument !== true && document.querySelector('+json.dumps(selector)+')?.value === '+json.dumps(value,ensure_ascii=False),'reload')
   if read_saved()!=saved:raise ValueError(name+' reload altered bytes')
   if name=='hyokeisan':wait("document.querySelector('[data-k=c0]')?.parentElement.querySelector('.value')?.textContent==='1.5'",'decimal reload')
   requests=[e['params']['request']['url'] for e in pipe.events if e.get('method')=='Network.requestWillBeSent']
   if not requests or any(not x.startswith(results[name]['base']) for x in requests):raise ValueError(name+' unexpected network request '+repr(requests))
   results[name]['browser']={'status':'PASS','checks':['edit','save','reload','decimal' if name=='hyokeisan' else 'multiline' if name=='zuhyo' else 'unicode title'],'requestCount':len(requests)}
   print(name,'PASS',flush=True)
  finally:pipe.close()
 for result in results.values():result.pop('base',None)
 (out/'receipt.json').write_text(json.dumps({'status':'PASS_OFFLINE_CID_CANDIDATES','scope':'isolated loopback offline Kubo; no public pin, DNS, TLS, migration or release','ipfsVersion':run('version'),'gatewayConfig':{'swarm':[],'bootstrap':[],'routing':'none','noFetch':True,'noDNSLink':True},'apps':results},ensure_ascii=False,indent=2)+'\n')
 print('PASS_OFFLINE_OFFICE_CID_CANDIDATES',flush=True)
finally:
 proc.terminate()
 try:proc.wait(timeout=10)
 except subprocess.TimeoutExpired:proc.kill();proc.wait()
 log.close()
