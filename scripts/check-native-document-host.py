#!/usr/bin/env python3
"""Link the browser-staged Bunsho model into a native Kotoba host.

Usage: script AMU_DIR KOTOBA_DIR BROWSER_BUILD OUTPUT_DIR
Synthetic macOS Arm only. This does not qualify OS GUI, QEMU or persistence.
"""
import hashlib,importlib.util,json,sys,types
from pathlib import Path
from browser_source import stage as browser_stage
from native_document_source import stage as host_stage
if len(sys.argv)!=5:raise SystemExit(__doc__)
amu,kotoba,build,out=map(lambda x:Path(x).resolve(),sys.argv[1:]);root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('native_gate',kotoba/'lib/kotoba.hata/scripts/native_gate.py');ng=importlib.util.module_from_spec(spec);spec.loader.exec_module(ng)
args=types.SimpleNamespace(compiler=amu/'seed/bootstrap/aarch64-macos/amu-full-root.macho',compiler_sha256='2c551579c06a0228029bb06bae177e93126ecbbc37d636d693c471dbac8d1536',packager=amu/'seed/bootstrap/aarch64-macos/kotoba-packager-root.macho',packager_sha256='e95284408f091c8979ef74ece57116a4df2250e61e42074da5dc95ca30264142',output=out)
gate=ng.NativeGate(args)
if not gate.darwin:raise ValueError('test qualifies macOS Arm only')
browser=browser_stage(root);host=host_stage(root);driver=(root/'tests/native_document_host.kotoba').read_bytes();sha=lambda b:hashlib.sha256(b).hexdigest()
receipt=json.loads((build/'build-receipt.json').read_text())
if browser.encode()!=(build/'program.kotoba').read_bytes() or sha(browser.encode())!=receipt['sourceSha256'] or (root/'browser/app.js').read_bytes()!=(build/'app.js').read_bytes():raise ValueError('stale browser candidate')
if host.split('\n',1)[1]!=browser.split('\n',1)[1]:raise ValueError('model body changed')
files={'moji/editor.kotoba':host.encode(),'moji/native_document_host.kotoba':driver}
image=gate.build('host','moji/native_document_host.kotoba',files);gate.run('linked-model',image)
needle=b'(string=? kind "input") (on-input state target value)'
if files['moji/editor.kotoba'].count(needle)!=1:raise ValueError('mutation anchor')
mutant=dict(files);mutant['moji/editor.kotoba']=mutant['moji/editor.kotoba'].replace(needle,b'(string=? kind "never") (on-input state target value)')
broken=gate.build('mutant','moji/native_document_host.kotoba',mutant);gate.run('mutation-detected',broken,expected=1)
gate.finish('PASS_BUNSHO_LINKED_HOST',observerSHA256=sha(Path(__file__).read_bytes()),stagerSHA256=sha((root/'scripts/native_document_source.py').read_bytes()),browserStagerSHA256=sha((root/'scripts/browser_source.py').read_bytes()),nativeGateSHA256=sha((kotoba/'lib/kotoba.hata/scripts/native_gate.py').read_bytes()),browserBuild=receipt,hostSourceSha256=sha(host.encode()),scope='macOS Arm native synthetic data; no Itonami OS GUI, QEMU, durable storage or release')
