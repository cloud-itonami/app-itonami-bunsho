#!/usr/bin/env python3
"""Verify an older BS1-only candidate refuses BS2 without altering it.

Usage: python3 scripts/check-legacy-rollback.py AMU_DIR OLD_BUILD NEW_BUILD BS2_FILE OUTPUT_DIR CHROME
Synthetic state only; does not establish production rollback or crash recovery.
"""
import functools
import http.server
import importlib.util
import json
import shutil
import sys
import threading
import time
from pathlib import Path

amu, old, new, sample, out, chrome = map(lambda s: Path(s).resolve(), sys.argv[1:])
out.mkdir(parents=True, exist_ok=False)
shutil.copytree(old, out / 'old')
shutil.copytree(new, out / 'new')
profile = out / 'profile'
profile.mkdir()
raw = sample.read_text(encoding='utf-8')
if not raw.startswith('BS2|'): raise ValueError('fixture is not BS2')
spec = importlib.util.spec_from_file_location('browser', amu / 'scripts/seed/check-wasm32-browser.py')
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(out)))
threading.Thread(target=server.serve_forever, daemon=True).start()
pipe = browser.Pipe(str(chrome), profile)
key = 'itonami.bunsho.candidate.bs1'
try:
    target = pipe.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    session = pipe.call('Target.attachToTarget', {'targetId': target, 'flatten': True})['sessionId']
    pipe.call('Network.enable', {}, session)
    pipe.call('Page.navigate', {'url': f'http://127.0.0.1:{server.server_port}/old/index.html'}, session)
    def evaluate(expr):
        r = pipe.call('Runtime.evaluate', {'expression': expr, 'returnByValue': True}, session)
        if 'exceptionDetails' in r: raise ValueError(r['exceptionDetails'])
        return r.get('result', {}).get('value')
    def wait(expr, label):
        until = time.time() + 120
        while time.time() < until:
            try:
                if evaluate(expr): return
            except RuntimeError as e:
                if not any(x in str(e) for x in ('Inspected target navigated or closed', 'Execution context was destroyed', 'Cannot find context with specified id')): raise
            time.sleep(.2)
        raise TimeoutError(label + ': ' + str(evaluate("document.getElementById('status')?.textContent")))
    wait("document.querySelector('[data-k=title]') !== null", 'old candidate ready')
    evaluate('localStorage.setItem(' + json.dumps(key) + ',' + json.dumps(raw, ensure_ascii=False) + ');window.__oldDocument=true')
    pipe.call('Page.reload', {}, session)
    wait('window.__oldDocument !== true', 'old reload')
    wait("document.getElementById('status').textContent.includes('開けません')", 'old candidate refuses BS2')
    if evaluate('localStorage.getItem(' + json.dumps(key) + ')') != raw or evaluate("document.querySelector('[data-k=title]') !== null"):
        raise ValueError('older app modified BS2 or opened it')
    pipe.call('Page.navigate', {'url': f'http://127.0.0.1:{server.server_port}/new/index.html'}, session)
    wait("document.querySelector('[data-k=b1]')?.value === '編集😀'", 'new candidate reopens BS2')
    if evaluate('localStorage.getItem(' + json.dumps(key) + ')') != raw: raise ValueError('new app changed state on reopen')
    requests = [e['params']['request']['url'] for e in pipe.events if e.get('method') == 'Network.requestWillBeSent']
    if not requests or any(not u.startswith(f'http://127.0.0.1:{server.server_port}/') for u in requests): raise ValueError('unexpected request')
    (out / 'result.json').write_text(json.dumps({'status': 'PASS', 'checks': ['old refuses BS2', 'BS2 unchanged', 'new reopens BS2', 'loopback only'], 'limitations': ['synthetic state', 'no production rollback or crash qualification']}, indent=2) + '\n')
    print('PASS_BS1_ROLLBACK refuses BS2 without changing it; new candidate reopens')
finally:
    pipe.close()
    server.shutdown()
    server.server_close()
