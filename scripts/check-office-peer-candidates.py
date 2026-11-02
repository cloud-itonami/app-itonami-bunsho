#!/usr/bin/env python3
"""Fetch office candidates over a private two-node loopback swarm.

Usage: check-office-peer-candidates.py AMU BUNSHO_BUILD HYOKEISAN_BUILD ZUHYO_BUILD OUT CHROME
No external peers, public pin, DNS/TLS, independent host, production route or release.
"""
import hashlib, importlib.util, json, os, secrets, socket, subprocess, sys, time, urllib.request
from pathlib import Path
from office_candidate_integrity import validate, candidate_files
if len(sys.argv)!=7: raise SystemExit(__doc__)
amu,bunsho,hyokeisan,zuhyo,out,chrome=map(lambda s:Path(s).resolve(),sys.argv[1:])
out.mkdir(parents=True,exist_ok=False)
def port():
 with socket.socket() as s: s.bind(('127.0.0.1',0));return s.getsockname()[1]
def sha(b): return hashlib.sha256(b).hexdigest()
psk=secrets.token_hex(32); nodes={};procs=[]
def call(node,*args):
 result=subprocess.run(['ipfs',*map(str,args)],env=nodes[node]['env'],text=True,capture_output=True,timeout=60)
 if result.returncode: raise RuntimeError((node,args,result.returncode,result.stderr[-1000:]))
 return result.stdout.strip()
try:
 for node in ('provider','gateway'):
  root=out/node;env=dict(os.environ,IPFS_PATH=str(root),IPFS_TELEMETRY='off',LIBP2P_FORCE_PNET='1',LIBP2P_TCP_MUX='false')
  nodes[node]={'env':env,'root':root,'swarm':port(),'api':port(),'gateway':port()}
  call(node,'init','--profile=test')
  (root/'swarm.key').write_text('/key/swarm/psk/1.0.0/\n/base16/\n'+psk+'\n');(root/'swarm.key').chmod(0o600)
  cfg=json.loads((root/'config').read_text());n=nodes[node]
  cfg['Addresses']['Swarm']=[f"/ip4/127.0.0.1/tcp/{n['swarm']}"];cfg['Addresses']['API']=f"/ip4/127.0.0.1/tcp/{n['api']}";cfg['Addresses']['Gateway']=f"/ip4/127.0.0.1/tcp/{n['gateway']}"
  cfg['Bootstrap']=[];cfg['Discovery']['MDNS']['Enabled']=False;cfg['Routing']['Type']='none';cfg['Routing']['DelegatedRouters']=[]
  cfg['AutoConf']['Enabled']=False;cfg['Swarm']['DisableNatPortMap']=True;cfg['Gateway']['NoDNSLink']=True;cfg['Gateway']['NoFetch']=False
  (root/'config').write_text(json.dumps(cfg))
 builds={'bunsho':bunsho,'hyokeisan':hyokeisan,'zuhyo':zuhyo};results={}
 for name,build in builds.items():
  receipt=validate(build,name)
  cid=call('provider','add','-Qr','--hidden','--cid-version=1','--raw-leaves=true','--chunker=size-262144','--hash=sha2-256','--pin=true',build).splitlines()[-1]
  results[name]={'cid':cid,'build':receipt,'files':{}}
 # Wait for standalone commands to release their repo locks before starting.
 for node in nodes:
  for _ in range(100):
   if not (nodes[node]['root']/'repo.lock').exists():break
   time.sleep(.1)
  else:raise RuntimeError(node+' repo still locked')
  log=(out/(node+'.log')).open('wb');proc=subprocess.Popen(['ipfs','daemon'],env=nodes[node]['env'],stdout=log,stderr=subprocess.STDOUT);procs.append((proc,log));nodes[node]['proc']=proc
 for node,n in nodes.items():
  for _ in range(300):
   if n['proc'].poll() is not None:raise RuntimeError(node+' daemon exited')
   try:
    req=urllib.request.Request(f"http://127.0.0.1:{n['api']}/api/v0/id",method='POST')
    with urllib.request.urlopen(req,timeout=1) as r: n['id']=json.load(r)['ID']
    break
   except Exception:time.sleep(.1)
  else:raise RuntimeError(node+' API not ready')
 provider_pins=set(line.split()[0] for line in call('provider','pin','ls','--type=recursive').splitlines())
 if any(item['cid'] not in provider_pins for item in results.values()):raise ValueError('provider did not pin candidates')
 before=set(call('gateway','refs','local').splitlines())
 # refs local presents stored multihashes using raw CID wrappers.
 roots={name:call('gateway','cid','format','-v','1','--mc','raw','-b','base32',r['cid']) for name,r in results.items()}
 if any(cid in before for cid in roots.values()):raise ValueError('gateway already has candidate')
 addr=f"/ip4/127.0.0.1/tcp/{nodes['provider']['swarm']}/p2p/{nodes['provider']['id']}"
 call('gateway','swarm','connect',addr)
 for node,peer in [('gateway',nodes['provider']['id']),('provider',nodes['gateway']['id'])]:
  peers=call(node,'swarm','peers').splitlines()
  if len(peers)!=1 or not peers[0].startswith('/ip4/127.0.0.1/') or not peers[0].endswith('/p2p/'+peer):raise ValueError((node,peers))
 for name,build in builds.items():
  base=f"http://127.0.0.1:{nodes['gateway']['gateway']}/ipfs/{results[name]['cid']}/"
  for file in candidate_files(build):
   with urllib.request.urlopen(base+file.relative_to(build).as_posix(),timeout=60) as r:data=r.read()
   if data!=file.read_bytes():raise ValueError(name+' peer fetch mismatch '+file.name)
   results[name]['files'][file.relative_to(build).as_posix()]=sha(data)
  results[name]['base']=base
 after=set(call('gateway','refs','local').splitlines())
 if any(cid not in after for cid in roots.values()):raise ValueError('gateway did not retrieve roots')
 spec=importlib.util.spec_from_file_location('browser',amu/'scripts/seed/check-wasm32-browser.py');browser=importlib.util.module_from_spec(spec);spec.loader.exec_module(browser)
 for name in builds:
  profile=out/(name+'-profile');profile.mkdir();pipe=browser.Pipe(str(chrome),profile)
  try:
   target=pipe.call('Target.createTarget',{'url':'about:blank'})['targetId'];session=pipe.call('Target.attachToTarget',{'targetId':target,'flatten':True})['sessionId']
   pipe.call('Network.enable',{},session);pipe.call('Page.enable',{},session);pipe.call('Page.navigate',{'url':results[name]['base']+'index.html'},session);pipe.call('Page.bringToFront',{},session)
   def ev(expr):
    r=pipe.call('Runtime.evaluate',{'expression':expr,'returnByValue':True},session)
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
   field={'bunsho':'b0','hyokeisan':'c0','zuhyo':'body'}[name]
   value={'bunsho':'CID 一行\n二行😀','hyokeisan':'=3/2','zuhyo':'CID 一行\n二行😀'}[name]
   key={'bunsho':'itonami.bunsho.candidate.bs1','hyokeisan':'itonami.hyokeisan.candidate.hs1','zuhyo':'itonami.zuhyo.candidate.zs1'}[name]
   selector='[data-k='+field+']';wait('document.querySelector('+json.dumps(selector)+') !== null','initial')
   ev('(()=>{let e=document.querySelector('+json.dumps(selector)+');e.value='+json.dumps(value,ensure_ascii=False)+";e.dispatchEvent(new Event('input',{bubbles:true}))})()")
   wait('localStorage.getItem('+json.dumps(key)+')?.includes('+json.dumps(value,ensure_ascii=False)+") && document.getElementById('status').textContent==='保存しました'",'save')
   if name=='hyokeisan':wait("document.querySelector('[data-k=c0]')?.parentElement.querySelector('.value')?.textContent==='1.5'",'decimal result')
   if name=='bunsho' and not ev('localStorage.getItem('+json.dumps(key)+").startsWith('BS3|1')"):raise ValueError('Bunsho multiline version missing')
   if name=='zuhyo' and not ev('localStorage.getItem('+json.dumps(key)+").startsWith('ZS2|')"):raise ValueError('multiline version missing')
   saved=ev('localStorage.getItem('+json.dumps(key)+')');ev('window.__oldDocument=true');pipe.call('Page.reload',{},session)
   wait('window.__oldDocument !== true && document.querySelector('+json.dumps(selector)+')?.value === '+json.dumps(value,ensure_ascii=False),'reload')
   if ev('localStorage.getItem('+json.dumps(key)+')')!=saved:raise ValueError(name+' reload altered bytes')
   if name=='hyokeisan':wait("document.querySelector('[data-k=c0]')?.parentElement.querySelector('.value')?.textContent==='1.5'",'decimal reload')
   requests=[e['params']['request']['url'] for e in pipe.events if e.get('method')=='Network.requestWillBeSent']
   if not requests or any(not x.startswith(results[name]['base']) for x in requests):raise ValueError(name+' unexpected network request '+repr(requests))
   results[name]['browser']={'status':'PASS','checks':['edit','save','reload','decimal' if name=='hyokeisan' else 'multiline' if name=='zuhyo' else 'multiline'],'requestCount':len(requests)}
   print(name,'PASS',flush=True)
  finally:pipe.close()
 # Replicate into the second local repo, then stop the only provider.
 for item in results.values(): call('gateway','pin','add',item['cid'])
 provider=nodes['provider']['proc'];provider.terminate();provider.wait(timeout=10)
 for _ in range(100):
  if not call('gateway','swarm','peers').strip():break
  time.sleep(.1)
 else:raise ValueError('provider connection persisted after stop')
 pinned=set(line.split()[0] for line in call('gateway','pin','ls','--type=recursive').splitlines())
 if any(item['cid'] not in pinned for item in results.values()):raise ValueError('local replica is not pinned')
 for name,build in builds.items():
  for file in candidate_files(build):
   with urllib.request.urlopen(results[name]['base']+file.relative_to(build).as_posix(),timeout=10) as r:data=r.read()
   if data!=file.read_bytes():raise ValueError(name+' replica mismatch after provider stop')
 for result in results.values():result.pop('base',None)
 (out/'receipt.json').write_text(json.dumps({'status':'PASS_PRIVATE_LOOPBACK_PEER_CANDIDATES','observerSha256':sha(Path(__file__).read_bytes()),'scope':'two local peers and a private swarm; no independent host, public pin, DNS/TLS or release','ipfsVersion':call('gateway','version'),'isolation':{'swarm':'127.0.0.1','bootstrap':[],'mdns':False,'privateSwarm':True,'routing':'none','telemetry':'off'},'replication':{'bothReposPinned':True,'providerStopped':True,'allFilesVerifiedAfterStop':True,'independentHost':False},'apps':results},ensure_ascii=False,indent=2)+'\n')
 print('PASS_PRIVATE_LOOPBACK_PEER_CANDIDATES',flush=True)
finally:
 for proc,log in reversed(procs):
  if proc.poll() is None:proc.terminate()
  try:proc.wait(timeout=10)
  except subprocess.TimeoutExpired:proc.kill();proc.wait()
  log.close()
