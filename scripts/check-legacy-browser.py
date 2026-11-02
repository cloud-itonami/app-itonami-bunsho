#!/usr/bin/env python3
"""Synthetic legacy import, rollback and BS2 persistence in Chrome.

Usage: python3 scripts/check-legacy-browser.py AMU_DIR BUILD_DIR OUTPUT_DIR CHROME
No old-origin fetch, actual user data, public delivery or crash qualification.
"""
import functools
import http.server
import importlib.util
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

amu, build, out, chrome = map(lambda s: Path(s).resolve(), sys.argv[1:])
out.mkdir(parents=True, exist_ok=False)
profile = out / 'profile'
profile.mkdir()
download = out / 'downloads'
download.mkdir()
spec = importlib.util.spec_from_file_location('browser', amu / 'scripts/seed/check-wasm32-browser.py')
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(build)))
threading.Thread(target=server.serve_forever, daemon=True).start()
# Optional isolated CID gateway. Never let a test option direct synthetic user
# input or localStorage to a remote host, and allow requests only under this CID.
base = os.environ.get('BUNSHO_TEST_CID_BASE')
if base:
    parsed = urlsplit(base)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.port is None
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or not re.fullmatch(r'/ipfs/b[a-z2-7]+/', parsed.path)):
        raise ValueError('CID test base must be a loopback HTTP CID directory')
else:
    base = f'http://127.0.0.1:{server.server_port}/'
pipe = browser.Pipe(str(chrome), profile)
key = 'itonami.bunsho.candidate.bs1'
legacy = {'found': True, 'document': {'documentId': 'old-doc', 'title': '旧文書😀', 'revisionId': 'rev-8',
          'ownerDid': 'did:key:fixture', 'createdAtMs': 1700000000000, 'unknown': {'keep': True},
          'body': [{'elementId': 'e-one', 'kind': 'heading', 'headingLevel': 2, 'text': '見出し😀'},
                   {'elementId': 'e-two', 'kind': 'paragraph', 'text': '本文'},
                   {'elementId': 'e-list', 'kind': 'listItem', 'text': '項目😀'}]}}
if os.environ.get('BUNSHO_MAX_TEST') == '1':
    wide = os.environ.get('BUNSHO_WIDE_TEST') == '1'
    legacy['document']['body'].extend({'elementId': 'e-' + str(i), 'kind': 'paragraph', 'text': ('x' * 540 if wide else '行' + str(i))} for i in range(3, 32))
raw = json.dumps(legacy, ensure_ascii=True, separators=(',', ':'))
valid = out / 'legacy.json'
valid.write_text(raw, encoding='utf-8')
invalid = out / 'unsupported.json'
bad = json.loads(raw)
bad['document']['body'][0]['headingLevel'] = 3
invalid.write_text(json.dumps(bad), encoding='utf-8')
try:
    target = pipe.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    session = pipe.call('Target.attachToTarget', {'targetId': target, 'flatten': True})['sessionId']
    pipe.call('Network.enable', {}, session)
    pipe.call('Page.navigate', {'url': base + 'index.html'}, session)
    pipe.call('Browser.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': str(download)})
    def evaluate(expr):
        r = pipe.call('Runtime.evaluate', {'expression': expr, 'returnByValue': True}, session)
        if 'exceptionDetails' in r: raise ValueError(r['exceptionDetails'])
        return r.get('result', {}).get('value')
    def wait(expr, label, seconds=120):
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                if evaluate(expr): return
            except RuntimeError as e:
                if not any(x in str(e) for x in ('Inspected target navigated or closed', 'Execution context was destroyed', 'Cannot find context with specified id')): raise
            time.sleep(.2)
        raise TimeoutError(label + ': ' + str(evaluate("document.getElementById('status')?.textContent")))
    def choose(path):
        evaluate("document.getElementById('backup-file').value=''")
        pipe.call('DOM.enable', {}, session)
        doc = pipe.call('DOM.getDocument', {}, session)['root']['nodeId']
        node = pipe.call('DOM.querySelector', {'nodeId': doc, 'selector': '#backup-file'}, session)['nodeId']
        pipe.call('DOM.setFileInputFiles', {'nodeId': node, 'files': [str(path)]}, session)
    def stored(): return evaluate('localStorage.getItem(' + json.dumps(key) + ')')
    def frames(wire):
        data = wire.encode('utf-8')
        if not data.startswith(b'BS2|'): raise ValueError('not BS2')
        pos, fields = 4, []
        while pos < len(data):
            end = data.index(b':', pos)
            length = int(data[pos:end])
            pos = end + 1
            value = data[pos:pos + length]
            if len(value) != length: raise ValueError('truncated frame')
            fields.append(value.decode('utf-8', errors='strict'))
            pos += length
        return fields
    wait("document.querySelector('[data-k=title]') !== null", 'initial')
    evaluate("(()=>{let e=document.querySelector('[data-k=title]');e.value='既存';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("localStorage.getItem('" + key + "')?.includes('既存') && document.getElementById('status').textContent === '保存しました'", 'BS1 baseline')
    baseline = stored()
    if not baseline.startswith('BS1|'): raise ValueError('missing BS1 baseline')
    choose(invalid)
    wait("document.getElementById('status').textContent.includes('読み込めません')", 'unsupported refusal')
    if stored() != baseline or evaluate("document.getElementById('backup-dialog').open"): raise ValueError('unsupported import altered state')
    choose(valid)
    wait("document.getElementById('backup-dialog').open", 'legacy preview')
    if stored() != baseline or evaluate("document.querySelector('#backup-preview [data-k=title]')?.value") != '旧文書😀': raise ValueError('preview altered state or title')
    if not evaluate("document.getElementById('backup-label').textContent.includes('未対応の属性')"): raise ValueError('missing metadata notice')
    evaluate("document.getElementById('backup-cancel').click()")
    if stored() != baseline: raise ValueError('cancel modified state')
    choose(valid)
    wait("document.getElementById('backup-dialog').open", 'legacy preview for backup failure')
    evaluate("window.savedSetter=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(this===localStorage && k.startsWith(" + json.dumps(key + '.preimport.') + "))throw Error('quota');return window.savedSetter.call(this,k,v)}")
    evaluate("document.getElementById('status').textContent='確認待ち';document.getElementById('backup-confirm').click()")
    wait("document.getElementById('status').textContent.includes('復元できませんでした')", 'pre-import backup failure')
    if stored() != baseline: raise ValueError('failed backup changed original')
    evaluate("Storage.prototype.setItem=window.savedSetter")
    choose(valid)
    wait("document.getElementById('backup-dialog').open", 'legacy preview for failure')
    evaluate("window.savedSetter=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(this===localStorage && k===" + json.dumps(key) + ")throw Error('quota');return window.savedSetter.call(this,k,v)}")
    evaluate("document.getElementById('status').textContent='確認待ち';document.getElementById('backup-confirm').click()")
    wait("document.getElementById('status').textContent.includes('復元できませんでした')", 'import write failure')
    if stored() != baseline: raise ValueError('failed write changed original')
    if not evaluate("Object.keys(localStorage).some(k=>k.startsWith(" + json.dumps(key + '.preimport.') + ") && localStorage.getItem(k)===" + json.dumps(baseline, ensure_ascii=False) + ")"): raise ValueError('missing pre-import copy after failure')
    evaluate("Storage.prototype.setItem=window.savedSetter")
    choose(valid)
    wait("document.getElementById('backup-dialog').open", 'legacy preview for commit')
    evaluate("document.getElementById('backup-confirm').click()")
    wait("document.getElementById('status').textContent === 'バックアップから復元しました。'", 'import commit')
    imported = stored()
    f = frames(imported)
    extras = [part for item in legacy['document']['body'][2:] for part in ('li' if item['kind'] == 'listItem' else 'p', item['text'], item['elementId'])]
    if f[:4] != [raw, '旧文書😀', 'edit', str(len(legacy['document']['body']))] or f[4:] != ['h2', '見出し😀', 'e-one', 'p', '本文', 'e-two'] + extras: raise ValueError('import did not preserve origin and identities')
    if evaluate("document.querySelector('[data-k=kl2]')?.classList.contains('on')") is not True or evaluate("document.querySelector('[data-k=b2]')?.value") != '項目😀': raise ValueError('list item did not render as a list item')
    evaluate("(()=>{let e=document.querySelector('[data-k=b0]');e.value='編集😀';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("document.getElementById('status').textContent === '保存しました' && localStorage.getItem('" + key + "')?.includes('編集😀')", 'BS2 edit')
    evaluate("document.querySelector('[data-k=dn0]').click()")
    wait("document.getElementById('status').textContent === '保存しました' && document.querySelector('[data-k=b1]')?.value === '編集😀'", 'BS2 reorder')
    edited = stored()
    f = frames(edited)
    if f[0] != raw or f[4:] != ['p', '本文', 'e-two', 'h2', '編集😀', 'e-one'] + extras: raise ValueError('identity or origin lost after edit/reorder')
    evaluate('window.__oldDocument=true')
    pipe.call('Page.reload', {}, session)
    wait('window.__oldDocument !== true', 'new document')
    wait("document.querySelector('[data-k=b1]')?.value === '編集😀'", 'BS2 reopen')
    if stored() != edited: raise ValueError('reopen changed state')
    if evaluate("document.querySelector('[data-k=kl2]')?.classList.contains('on')") is not True or evaluate("document.querySelector('[data-k=b2]')?.value") != '項目😀': raise ValueError('list item did not survive reopen')
    evaluate("document.querySelector('[data-k=backup-export]').click()")
    f = download / 'bunsho-backup.bs2'
    deadline = time.time() + 90
    while time.time() < deadline and not f.exists(): time.sleep(.2)
    if not f.exists() or f.read_text(encoding='utf-8') != edited: raise ValueError('BS2 export mismatch')
    requests = [e['params']['request']['url'] for e in pipe.events if e.get('method') == 'Network.requestWillBeSent']
    if not requests or any(not u.startswith(base) for u in requests): raise ValueError('unexpected network request')
    (out / 'result.json').write_text(json.dumps({'status': 'PASS', 'checks': ['BS1 baseline', 'unsupported refusal', 'preview cancel', 'failed backup preserves BS1', 'failed write preserves BS1', 'explicit BS2 import', 'provenance and IDs', 'edit reorder reopen', 'BS2 export', 'loopback CID only' if os.environ.get('BUNSHO_TEST_CID_BASE') else 'loopback only'], 'limitations': ['synthetic data', 'unsupported legacy kinds refused', 'unknown metadata is provenance only', 'no old-origin fetch', 'no crash/QEMU/publication qualification']}, indent=2) + '\n')
    print('PASS_LEGACY_BROWSER synthetic explicit import, preservation and reopen')
finally:
    pipe.close()
    server.shutdown()
    server.server_close()
