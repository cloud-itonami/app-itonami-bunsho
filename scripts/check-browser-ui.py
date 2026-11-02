#!/usr/bin/env python3
"""Exercise a built Bunsho candidate in an isolated loopback browser profile.

Usage: python3 scripts/check-browser-ui.py AMU_DIR BUILD_DIR OUTPUT_DIR CHROME
"""
import functools
import http.server
import importlib.util
import json
import shutil
import threading
import time
import sys
from pathlib import Path

if len(sys.argv) != 5:
    raise SystemExit(__doc__)
amu, build, out, chrome = [Path(x).resolve() for x in sys.argv[1:]]
out.mkdir(parents=True, exist_ok=False)
profile = out / 'profile'
profile.mkdir()
site = out / 'site'
shutil.copytree(build, site)
spec = importlib.util.spec_from_file_location('browser', amu / 'scripts/seed/check-wasm32-browser.py')
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(out)))
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
pipe = browser.Pipe(str(chrome), profile)
url = f'http://127.0.0.1:{server.server_port}/site/index.html'
try:
    target = pipe.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    session = pipe.call('Target.attachToTarget', {'targetId': target, 'flatten': True})['sessionId']
    pipe.call('Network.enable', {}, session)
    pipe.call('Page.navigate', {'url': url}, session)
    def evaluate(expr):
        result = pipe.call('Runtime.evaluate', {'expression': expr, 'returnByValue': True}, session)
        if 'exceptionDetails' in result: raise ValueError(result['exceptionDetails'])
        return result.get('result', {}).get('value')
    def wait(expr, label, seconds=90):
        end = time.time() + seconds
        while time.time() < end:
            if evaluate(expr): return
            time.sleep(.2)
        raise TimeoutError(label + ': ' + str(evaluate('document.body.innerText')))
    wait("document.querySelector('[data-k=title]') !== null", 'initial UI')
    evaluate("document.querySelector('[data-k=title]').click()")
    time.sleep(1)
    if evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')") is not None: raise ValueError('focusing input wrote state')
    evaluate("(() => {let e=document.querySelector('[data-k=title]'); e.value='議事😀'; e.dispatchEvent(new Event('input',{bubbles:true})); return true;})()")
    wait("document.getElementById('status').textContent === '保存しました'", 'save')
    saved = evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')")
    if not saved or '議事😀' not in saved: raise ValueError('saved state missing edit')
    evaluate("(() => {let e=document.querySelector('[data-k=title]');for(const v of ['連','連続','連続入力']){e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));}})()")
    wait("document.querySelector('[data-k=title]')?.value === '連続入力' && localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('連続入力')", 'queued inputs')
    evaluate("document.querySelector('[data-k=add-p]').click()")
    wait("document.querySelector('[data-k=b2]') !== null", 'add paragraph')
    evaluate("document.querySelector('[data-k=mode]').click()")
    wait("document.querySelector('main.page.preview') !== null", 'preview')
    evaluate("document.querySelector('[data-k=mode]').click()")
    wait("document.querySelector('[data-k=b2]') !== null", 'edit mode')
    saved = evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')")
    pipe.call('Page.reload', {}, session)
    wait("document.querySelector('[data-k=title]')?.value === '連続入力'", 'reload')
    second = pipe.call('Target.createTarget', {'url': url})['targetId']
    second_session = pipe.call('Target.attachToTarget', {'targetId': second, 'flatten': True})['sessionId']
    def second_eval(expr):
        result = pipe.call('Runtime.evaluate', {'expression': expr, 'returnByValue': True}, second_session)
        if 'exceptionDetails' in result: raise ValueError(result['exceptionDetails'])
        return result.get('result', {}).get('value')
    end = time.time() + 90
    while time.time() < end and second_eval("document.querySelector('[data-k=title]')?.value") != '連続入力': time.sleep(.2)
    if second_eval("document.querySelector('[data-k=title]')?.value") != '連続入力': raise TimeoutError('second tab')
    evaluate("(()=>{let e=document.querySelector('[data-k=title]');e.value='先の変更';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('先の変更')", 'first tab write')
    second_eval("(()=>{let e=document.querySelector('[data-k=title]');e.value='後の変更';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    end = time.time() + 90
    while time.time() < end and not second_eval("document.getElementById('status')?.textContent.includes('保存できませんでした')"): time.sleep(.2)
    if not second_eval("document.getElementById('status')?.textContent.includes('保存できませんでした')"): raise TimeoutError('conflicting tab refusal')
    saved = evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')")
    if '先の変更' not in saved or '後の変更' in saved: raise ValueError('concurrent write clobbered state')
    pipe.call('Target.closeTarget', {'targetId': second})
    evaluate("window.savedWorker=window.Worker;window.Worker=class extends window.savedWorker {postMessage(msg){if(msg.args[0]==='view'){this.terminate();queueMicrotask(()=>this.onerror(new Event('error')))}else super.postMessage(msg)}}")
    evaluate("(()=>{let e=document.querySelector('[data-k=title]');e.value='中断';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("document.getElementById('status').textContent.includes('保存できませんでした')", 'worker interruption')
    if evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')") != saved: raise ValueError('interrupted render clobbered storage')
    evaluate("window.Worker=window.savedWorker")
    pipe.call('Page.reload', {}, session)
    wait("document.querySelector('[data-k=title]')?.value === '先の変更'", 'reload after interruption')
    evaluate("Storage.prototype.setItem = function(){ throw new Error('quota'); }; (()=>{let e=document.querySelector('[data-k=title]');e.value='失敗';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("document.getElementById('status').textContent.includes('保存できませんでした')", 'storage failure')
    wait("document.querySelector('[data-k=title]')?.value === '先の変更'", 'restore prior view')
    if evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')") != saved: raise ValueError('storage changed on failure')
    # Use the saved original setter from a new realm after reload for corruption injection.
    pipe.call('Page.reload', {}, session)
    wait("document.querySelector('[data-k=title]')?.value === '先の変更'", 'reload before corrupt')
    evaluate("localStorage.setItem('itonami.bunsho.candidate.bs1','BS1|bad')")
    pipe.call('Page.reload', {}, session)
    wait("document.getElementById('status').textContent.includes('文書を開けません')", 'corruption refusal')
    if evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')") != 'BS1|bad': raise ValueError('corrupt input overwritten')
    evaluate("localStorage.removeItem('itonami.bunsho.candidate.bs1')")
    tampered = out / 'tampered'
    shutil.copytree(site, tampered)
    bundle = tampered / 'bundle.js'
    content = bundle.read_text()
    content, count = __import__('re').subn(r'(export const wasmSha256 = ")[0-9a-f]{64}(";)', r'\g<1>' + '0' * 64 + r'\g<2>', content)
    if count != 1: raise ValueError('digest mutation anchor')
    bundle.write_text(content)
    pipe.call('Page.navigate', {'url': f'http://127.0.0.1:{server.server_port}/tampered/index.html'}, session)
    wait("document.getElementById('status')?.textContent.includes('文書を開けません')", 'digest refusal')
    if evaluate("document.querySelector('[data-k=title]') !== null || localStorage.getItem('itonami.bunsho.candidate.bs1') !== null"):
        raise ValueError('tampered candidate ran or wrote state')
    requests = [e['params']['request']['url'] for e in pipe.events if e.get('method') == 'Network.requestWillBeSent']
    if not requests or any(not u.startswith(f'http://127.0.0.1:{server.server_port}/') for u in requests):
        raise ValueError('unexpected request ' + repr(requests))
    (out / 'result.json').write_text(json.dumps({'status': 'PASS', 'checks': ['init', 'edit-save', 'queued-input', 'add', 'preview', 'reload', 'concurrent-write-refusal', 'worker-interruption', 'storage-failure', 'corruption-refusal', 'digest-refusal', 'loopback-only']}, indent=2) + '\n')
    print('PASS_BUNSHO_BROWSER_UI: init, edit, reload and failure preservation')
finally:
    pipe.close()
    server.shutdown()
    server.server_close()
