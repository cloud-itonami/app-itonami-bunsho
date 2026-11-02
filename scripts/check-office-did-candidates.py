#!/usr/bin/env python3
"""Verify static DID candidates, including Kubo's hidden-path behavior.

Usage: script BUNSHO_BUILD HYOKEISAN_BUILD ZUHYO_BUILD NEW_OUTPUT
Synthetic local content only; a DID document here proves no key control.
"""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
from office_candidate_integrity import validate, candidate_files
if len(sys.argv)!=5:raise SystemExit(__doc__)
builds=dict(zip(('bunsho','hyokeisan','zuhyo'),map(lambda s:Path(s).resolve(),sys.argv[1:4])))
out=Path(sys.argv[4]).resolve();out.mkdir(parents=True,exist_ok=False)
for name,build in builds.items():
 receipt=validate(build,name);assert len(candidate_files(build))==(15 if name=='bunsho' and 'managedStorageSha256' in receipt else 13)
 assert hashlib.sha256((build/'.well-known/did.json').read_bytes()).hexdigest()==receipt['didSha256']
# Alterations are isolated copies. A receipt edited along with the wrong ID
# must not bypass the independent app/hostname binding.
controls={}
cases = ['missing','wrong-id','symlink-dir','extra-hidden','did-bytes']
if (builds['bunsho']/'managed-storage.js').exists(): cases.append('storage-adapter')
for case in cases:
 target=out/case;shutil.copytree(builds['bunsho'],target)
 did=target/'.well-known/did.json'
 if case=='missing':did.unlink()
 elif case=='wrong-id':
  d=json.loads(did.read_text());d['id']='did:web:zuhyo.itonami.app';did.write_text(json.dumps(d))
  r=target/'build-receipt.json';receipt=json.loads(r.read_text());receipt['didSha256']=hashlib.sha256(did.read_bytes()).hexdigest();r.write_text(json.dumps(receipt))
 elif case=='symlink-dir':
  shutil.rmtree(target/'.well-known');(target/'.well-known').symlink_to(builds['bunsho']/'.well-known',target_is_directory=True)
 elif case=='extra-hidden':(target/'.well-known/extra').write_text('unexpected')
 elif case=='storage-adapter':
  adapter=target/'managed-storage.js';adapter.write_bytes(adapter.read_bytes()+b'\n')
 else:did.write_bytes(did.read_bytes()+b'\n')
 try:validate(target,'bunsho')
 except (ValueError,KeyError):controls[case]='refused'
 else:raise ValueError('undetected mutation: '+case)
# Both CIDs are local, unpinned, and isolated; default Kubo traversal must
# omit the hidden DID while --hidden must make its exact bytes retrievable.
env=dict(os.environ,IPFS_PATH=str(out/'ipfs'),IPFS_TELEMETRY='off')
def run(*args):return subprocess.run(['ipfs',*args],env=env,text=True,capture_output=True,timeout=60)
def good(*args):
 r=run(*args)
 if r.returncode:raise RuntimeError((args,r.stderr[-500:]))
 return r.stdout.strip()
good('init','--profile=test')
base=str(builds['bunsho']);common=['--cid-version=1','--raw-leaves=true','--chunker=size-262144','--pin=false',base]
without=good('add','-Qr',*common).splitlines()[-1]
with_hidden=good('add','-Qr','--hidden',*common).splitlines()[-1]
if without==with_hidden:raise ValueError('hidden control failed to change CID')
missing=run('cat',without+'/.well-known/did.json');found=run('cat',with_hidden+'/.well-known/did.json')
if missing.returncode==0 or found.returncode or found.stdout.encode()!=(builds['bunsho']/'.well-known/did.json').read_bytes():raise ValueError('hidden DID retrieval control failed')
report={'status':'PASS_DID_CANDIDATE_INTEGRITY','apps':list(builds),'fileCounts':{name:len(candidate_files(build)) for name,build in builds.items()},'controls':controls,'defaultRecursiveAddOmitsDid':True,'hiddenAddRetrievesExactDid':True,'scope':'local isolated Kubo and static candidate bytes; no DID key control, public DNS/TLS, permanent pins or release'}
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(report['status'],flush=True)
