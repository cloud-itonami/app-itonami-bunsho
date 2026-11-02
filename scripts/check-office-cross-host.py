#!/usr/bin/env python3
"""Cross-host, private-swarm candidate qualification; no public publication.

Usage: script AMU BUNSHO HYOKEISAN ZUHYO OUT CHROME HOST REMOTE_DIR LOCAL_IP REMOTE_IP
REMOTE_DIR must be a fresh, task-owned directory with a verified `ipfs` binary.
This test uses only one explicitly connected Tailscale peer; it does not establish
independent network/power failure domains, public availability, DNS or release.
"""
import hashlib,importlib.util,json,os,re,secrets,shlex,socket,subprocess,sys,time,urllib.request
from pathlib import Path
if len(sys.argv)!=11:raise SystemExit(__doc__)
amu,bunsho,hyokeisan,zuhyo,out,chrome=map(lambda s:Path(s).resolve(),sys.argv[1:7]);host,remote,local_ip,remote_ip=sys.argv[7:]
if not re.fullmatch(r'[a-zA-Z0-9.-]+',host) or not re.fullmatch(r'/Users/[A-Za-z0-9_-]+/github/workspaces/codex/[A-Za-z0-9_-]+',remote):raise ValueError('unsafe remote')
for ip in (local_ip,remote_ip):
 if not re.fullmatch(r'100(?:\.\d{1,3}){3}',ip) or any(int(x)>255 for x in ip.split('.')):raise ValueError('tailnet IP required')
out.mkdir(parents=True,exist_ok=False)
ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','StrictHostKeyChecking=yes',host]
def remote_call(*args,input=None):
 # This host's SSH reports zero even when the remote command fails. Require a
 # shell-emitted status marker as well as the SSH transport status.
 marker='__codex_remote_status__'
 command=' '.join(shlex.quote(str(x)) for x in args) + '''; _codex_rc=$?; printf '\n__codex_remote_status__=%s\n' "$_codex_rc" >&2'''
 result=subprocess.run(ssh+[command],input=input,text=True,capture_output=True,timeout=120)
 match=re.search(r'\n__codex_remote_status__=(\d+)\n$',result.stderr)
 if result.returncode or not match or int(match.group(1))!=0:
  raise RuntimeError(('remote',args[0],result.returncode,result.stderr[-1000:]))
 return result.stdout.strip()
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def sha(b):return hashlib.sha256(b).hexdigest()
ipfs=Path('/opt/homebrew/Cellar/kubo/0.41.0/bin/ipfs');binary_sha=sha(ipfs.read_bytes())
remote_sha=remote_call('shasum','-a','256',remote+'/ipfs').split()[0]
if remote_sha!=binary_sha:raise ValueError('remote executable mismatch')
env=dict(os.environ,IPFS_PATH=str(out/'provider'),IPFS_TELEMETRY='off',LIBP2P_FORCE_PNET='1',LIBP2P_TCP_MUX='false')
def local(*args):
 r=subprocess.run([str(ipfs),*map(str,args)],env=env,text=True,capture_output=True,timeout=120)
 if r.returncode:raise RuntimeError(('local',args,r.returncode,r.stderr[-1000:]))
 return r.stdout.strip()
def remote_ipfs(*args):return remote_call('env','IPFS_PATH='+remote+'/repo','IPFS_TELEMETRY=off','LIBP2P_FORCE_PNET=1','LIBP2P_TCP_MUX=false',remote+'/ipfs',*args)
provider=None;tunnel=None;remote_started=False;log=None
try:
 psk=secrets.token_hex(32);local('init','--profile=test');remote_ipfs('init','--profile=test')
 (out/'provider/swarm.key').write_text('/key/swarm/psk/1.0.0/\n/base16/\n'+psk+'\n');(out/'provider/swarm.key').chmod(0o600)
 keycode="import os,sys; p=sys.argv[1]+'/repo/swarm.key'; f=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.write(f,sys.stdin.buffer.read()); os.close(f)"
 remote_call('python3','-c',keycode,remote,input='/key/swarm/psk/1.0.0/\n/base16/\n'+psk+'\n');psk=None
 lp,la,lg=port(),port(),port()
 ports=remote_call('python3','-c',"import socket; s=[socket.socket() for _ in range(3)]; [x.bind(('127.0.0.1',0)) for x in s]; print(' '.join(str(x.getsockname()[1]) for x in s))")
 rp,ra,rg=map(int,ports.split())
 cfg=json.loads((out/'provider/config').read_text());cfg['Addresses']['Swarm']=[f'/ip4/{local_ip}/tcp/{lp}'];cfg['Addresses']['API']=f'/ip4/127.0.0.1/tcp/{la}';cfg['Addresses']['Gateway']=f'/ip4/127.0.0.1/tcp/{lg}';cfg['Bootstrap']=[];cfg['Discovery']['MDNS']['Enabled']=False;cfg['Routing']['Type']='none';cfg['Routing']['DelegatedRouters']=[];cfg['AutoConf']['Enabled']=False;cfg['Swarm']['DisableNatPortMap']=True;cfg['Gateway']['NoDNSLink']=True;(out/'provider/config').write_text(json.dumps(cfg))
 configcode="import json,sys; p=sys.argv[1]+'/repo/config'; c=json.load(open(p)); ip,sw,api,gw=sys.argv[2:]; c['Addresses'].update(Swarm=['/ip4/'+ip+'/tcp/'+sw],API='/ip4/127.0.0.1/tcp/'+api,Gateway='/ip4/127.0.0.1/tcp/'+gw); c['Bootstrap']=[];c['Discovery']['MDNS']['Enabled']=False;c['Routing']['Type']='none';c['Routing']['DelegatedRouters']=[];c['AutoConf']['Enabled']=False;c['Swarm']['DisableNatPortMap']=True;c['Gateway']['NoDNSLink']=True;c['Gateway']['NoFetch']=False;open(p,'w').write(json.dumps(c))"
 remote_call('python3','-c',configcode,remote,remote_ip,rp,ra,rg)
 builds={'bunsho':bunsho,'hyokeisan':hyokeisan,'zuhyo':zuhyo};results={}
 for name,build in builds.items():
  files=sorted(p for p in build.iterdir() if p.is_file())
  if len(files)!=10 or any(p.is_symlink() for p in files):raise ValueError(name+' unexpected files')
  receipt=json.loads((build/'build-receipt.json').read_text())
  if sha((build/'program.kotoba').read_bytes())!=receipt['sourceSha256'] or sha((build/'program.wasm').read_bytes())!=receipt['wasmSha256']:raise ValueError(name+' stale build')
  cid=local('add','-Qr','--cid-version=1','--raw-leaves=true','--chunker=size-262144','--hash=sha2-256','--pin=true',build).splitlines()[-1]
  results[name]={'cid':cid,'build':receipt,'files':{}}
 for _ in range(100):
  if not (out/'provider/repo.lock').exists():break
  time.sleep(.1)
 else:raise RuntimeError('provider repo still locked')
 log=(out/'provider.log').open('wb');provider=subprocess.Popen([str(ipfs),'daemon'],env=env,stdout=log,stderr=subprocess.STDOUT)
 launch="import os,subprocess,sys; d=sys.argv[1]; f=open(d+'/daemon.pid','x'); e=dict(os.environ,IPFS_PATH=d+'/repo',IPFS_TELEMETRY='off',LIBP2P_FORCE_PNET='1',LIBP2P_TCP_MUX='false'); log=open(d+'/daemon.log','ab'); p=subprocess.Popen([d+'/ipfs','daemon'],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env=e,start_new_session=True);f.write(str(p.pid));f.close()"
 remote_call('python3','-c',launch,remote);remote_started=True
 def local_ready():
  req=urllib.request.Request(f'http://127.0.0.1:{la}/api/v0/id',method='POST')
  with urllib.request.urlopen(req,timeout=1) as r:return json.load(r)['ID']
 ready="import json,sys,urllib.request; req=urllib.request.Request('http://127.0.0.1:'+sys.argv[1]+'/api/v0/id',method='POST'); print(json.load(urllib.request.urlopen(req,timeout=1))['ID'])"
 for _ in range(100):
  if provider.poll() is not None:raise RuntimeError('local provider stopped')
  try:pid=local_ready();rid=remote_call('python3','-c',ready,ra);break
  except Exception:time.sleep(.2)
 else:raise RuntimeError('daemon readiness')
 pins=set(x.split()[0] for x in local('pin','ls','--type=recursive').splitlines())
 if any(x['cid'] not in pins for x in results.values()):raise ValueError('provider pins absent')
 before=set(remote_ipfs('refs','local').splitlines());rawroots={name:remote_ipfs('cid','format','-v','1','--mc','raw','-b','base32',r['cid']) for name,r in results.items()}
 if any(c in before for c in rawroots.values()):raise ValueError('remote preloaded')
 remote_ipfs('swarm','connect',f'/ip4/{local_ip}/tcp/{lp}/p2p/{pid}')
 for value,expected,addr in [(local('swarm','peers'),rid,remote_ip),(remote_ipfs('swarm','peers'),pid,local_ip)]:
  peers=value.splitlines()
  if len(peers)!=1 or not peers[0].startswith('/ip4/'+addr+'/') or not peers[0].endswith('/p2p/'+expected):raise ValueError(('unexpected peers',peers))
 forward=port();tunnel=subprocess.Popen(ssh[:-1]+['-o','ExitOnForwardFailure=yes','-N','-L',f'127.0.0.1:{forward}:127.0.0.1:{rg}',host],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 for _ in range(100):
  if tunnel.poll() is not None:raise RuntimeError('ssh tunnel stopped')
  try:
   with urllib.request.urlopen(f'http://127.0.0.1:{forward}/ipfs/{results["bunsho"]["cid"]}/index.html',timeout=1) as r:r.read()
   break
  except Exception:time.sleep(.1)
 else:raise RuntimeError('gateway not ready')
 for name,build in builds.items():
  base=f'http://127.0.0.1:{forward}/ipfs/{results[name]["cid"]}/'
  for file in sorted(build.iterdir()):
   with urllib.request.urlopen(base+file.name,timeout=60) as r:data=r.read()
   if data!=file.read_bytes():raise ValueError(name+' remote gateway mismatch '+file.name)
   results[name]['files'][file.name]=sha(data)
  results[name]['base']=base
 after=set(remote_ipfs('refs','local').splitlines())
 if any(c not in after for c in rawroots.values()):raise ValueError('remote roots absent')
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
 for item in results.values():remote_ipfs('pin','add',item['cid'])
 provider.terminate();provider.wait(timeout=10)
 for _ in range(100):
  if not remote_ipfs('swarm','peers').strip():break
  time.sleep(.1)
 else:raise ValueError('provider connection persisted')
 pins=set(x.split()[0] for x in remote_ipfs('pin','ls','--type=recursive').splitlines())
 if any(x['cid'] not in pins for x in results.values()):raise ValueError('remote pin absent')
 for name,build in builds.items():
  for file in sorted(build.iterdir()):
   with urllib.request.urlopen(results[name]['base']+file.name,timeout=10) as r:data=r.read()
   if data!=file.read_bytes():raise ValueError(name+' failover mismatch')
 for item in results.values():item.pop('base',None)
 (out/'receipt.json').write_text(json.dumps({'status':'PASS_PRIVATE_CROSS_HOST_CANDIDATES','observerSha256':sha(Path(__file__).read_bytes()),'kuboBinarySha256':binary_sha,'scope':'two hosts, one tailnet path; private swarm only; not public routing, independent network/power, DNS/TLS, or release','isolation':{'privateSwarm':True,'bootstrap':[],'mdns':False,'routing':'none','telemetry':'off'},'replication':{'bothHostsPinned':True,'providerStopped':True,'allFilesVerifiedAfterStop':True},'apps':results},ensure_ascii=False,indent=2)+'\n')
 print('PASS_PRIVATE_CROSS_HOST_CANDIDATES',flush=True)
finally:
 if tunnel and tunnel.poll() is None:tunnel.terminate();tunnel.wait(timeout=10)
 if provider and provider.poll() is None:provider.terminate();provider.wait(timeout=10)
 if log:log.close()
 if remote_started:
  stop="import os,signal,subprocess,sys,time; d=sys.argv[1];p=int(open(d+'/daemon.pid').read());v=subprocess.run(['ps','-p',str(p),'-o','command='],capture_output=True,text=True).stdout; assert d+'/ipfs daemon' in v, 'unexpected process; refusing to stop';os.kill(p,signal.SIGTERM)"
  remote_call('python3','-c',stop,remote)
