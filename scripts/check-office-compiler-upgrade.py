#!/usr/bin/env python3
"""Test synthetic same-origin saved data across an Amu/Wasm candidate change.

Usage: APP AMU OLD_BUILD NEW_BUILD NEW_OUTPUT CHROME
Does not use real data, old origins, public routes or crash recovery.
"""
import functools, hashlib, http.server, importlib.util, json, re, sys, threading, time
from pathlib import Path
if len(sys.argv) != 7 or sys.argv[1] not in ('bunsho', 'hyokeisan', 'zuhyo'):
    raise SystemExit(__doc__)
app = sys.argv[1]
amu, old, new, out, chrome = (Path(p).resolve() for p in sys.argv[2:])
out.mkdir(parents=True, mode=0o700, exist_ok=False)
(out / 'profile').mkdir(mode=0o700)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
old_receipt, new_receipt = (json.loads((p / 'build-receipt.json').read_text()) for p in (old, new))
if old_receipt['wasmSha256'] == new_receipt['wasmSha256']:
    raise ValueError('the candidate binaries did not change')
field, suffix = {'bunsho': ('b0', 'bs1'), 'hyokeisan': ('c0', 'hs1'), 'zuhyo': ('body', 'zs1')}[app]
key = f'itonami.{app}.candidate.{suffix}'
draftkey = key + '.session-draft.v1'
dbname = f'itonami.office.{app}.v2'
active = {'path': old}
class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(active['path']), **kwargs)
    def log_message(self, *args):
        pass
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
spec = importlib.util.spec_from_file_location('browser', amu / 'scripts/seed/check-wasm32-browser.py')
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)
pipe = browser.Pipe(str(chrome), out / 'profile')
try:
    target = pipe.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    session = pipe.call('Target.attachToTarget', {'targetId': target, 'flatten': True})['sessionId']
    pipe.call('Page.enable', {}, session)
    def ev(expr, awaited=False):
        r = pipe.call('Runtime.evaluate', {'expression': expr, 'returnByValue': True, 'awaitPromise': awaited}, session)
        if 'exceptionDetails' in r:
            raise ValueError(r['exceptionDetails'])
        return r.get('result', {}).get('value')
    def wait(expr, label):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                if ev(expr): return
            except RuntimeError as error:
                if not any(s in str(error) for s in ('Execution context was destroyed', 'Cannot find context with specified id')):
                    raise
            time.sleep(.1)
        raise TimeoutError(label + ': ' + str(ev('document.getElementById("status")?.textContent')))
    def state():
        return ev('''new Promise((resolve,reject)=>{let r=indexedDB.open(''' + json.dumps(dbname) + ''',1);r.onsuccess=()=>{let d=r.result,t=d.transaction("records","readonly"),g=t.objectStore("records").get("current");g.onsuccess=()=>resolve(g.result||null);g.onerror=()=>reject(Error("get"));t.oncomplete=()=>d.close()};r.onerror=()=>reject(Error("open"))})''', True)
    selector = '[data-k="' + field + '"]'
    def enter(text):
        ev('(()=>{let e=document.querySelector('+json.dumps(selector)+');e.value='+json.dumps(text, ensure_ascii=False)+';e.dispatchEvent(new Event("input",{bubbles:true}))})()')
    pipe.call('Page.navigate', {'url': f'http://127.0.0.1:{server.server_port}/index.html'}, session)
    wait('document.querySelector('+json.dumps(selector)+') !== null', 'old app')
    enter('旧保存😀')
    wait('document.getElementById("status").textContent === "保存しました"', 'old save')
    before = state()
    if before['revision'] != 1 or '旧保存😀' not in before['value']:
        raise ValueError('old save did not commit')
    draft = {'version': 2, 'program': old_receipt['wasmSha256'], 'base': before['value'],
             'baseRevision': before['revision'], 'baseState': before['value'], 'entries': [[field, '未保存😀']]}
    raw = json.dumps(draft, ensure_ascii=False, separators=(',', ':'))
    ev('sessionStorage.setItem('+json.dumps(draftkey)+','+json.dumps(raw,ensure_ascii=False)+')')
    active['path'] = new
    ev('window.__oldCandidate = true')
    pipe.call('Page.reload', {'ignoreCache': True}, session)
    wait('window.__oldCandidate !== true && !document.getElementById("draft-recovery").hidden && document.getElementById("draft-preview").textContent.includes("未保存😀")', 'upgrade draft preview')
    if not ev('document.getElementById("draft-restore").disabled') or state() != before:
        raise ValueError('old draft was auto-restored or saved state changed')
    if ev('sessionStorage.getItem('+json.dumps(draftkey)+')') != raw:
        raise ValueError('old draft was modified')
    pipe.send('Runtime.evaluate', {'expression': 'document.getElementById("draft-discard").click()'}, session)
    for _ in range(40):
        try:
            pipe.call('Page.handleJavaScriptDialog', {'accept': True}, session, timeout=5)
            break
        except RuntimeError: time.sleep(.1)
    else: raise ValueError('discard confirmation missing')
    wait('document.getElementById("draft-recovery").hidden && document.querySelector('+json.dumps(selector)+')?.value === "旧保存😀"', 'saved state reopened')
    enter('新保存😀')
    wait('document.getElementById("status").textContent === "保存しました"', 'new save')
    after = state()
    if after['revision'] != 2 or '新保存😀' not in after['value']:
        raise ValueError('new save failed')
    report = {'status': 'PASS_SYNTHETIC_COMPILER_UPGRADE', 'app': app,
              'oldBuildReceiptSha256': sha(old / 'build-receipt.json'), 'newBuildReceiptSha256': sha(new / 'build-receipt.json'),
              'oldWasmSha256': old_receipt['wasmSha256'], 'newWasmSha256': new_receipt['wasmSha256'],
              'observerSha256': sha(Path(__file__)), 'browserSha256': sha(chrome),
              'checks': ['old-save', 'old-draft-preserved-preview-only', 'explicit-discard', 'new-code-reopens-saved-state', 'new-save-increments-revision'],
              'scope': 'Synthetic same-origin Chrome only; no real user data, cross-origin import, QEMU or production.'}
    (out / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], app, flush=True)
finally:
    pipe.close()
    server.shutdown()
    server.server_close()
