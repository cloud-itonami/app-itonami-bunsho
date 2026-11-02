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
    if evaluate("document.querySelector('[data-k=title]').getAttribute('aria-label')") != '文書タイトル': raise ValueError('title lacks accessible name')
    if evaluate("document.querySelector('[data-k=b0]').getAttribute('aria-label')") != '本文ブロック 1': raise ValueError('block lacks accessible name')
    evaluate("document.querySelector('[data-k=title]').click()")
    time.sleep(1)
    if evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')") is not None: raise ValueError('focusing input wrote state')
    evaluate("(() => {let e=document.querySelector('[data-k=title]'); e.value='議事😀'; e.dispatchEvent(new Event('input',{bubbles:true})); return true;})()")
    wait("document.getElementById('status').textContent === '保存しました'", 'save')
    saved = evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')")
    if not saved or '議事😀' not in saved: raise ValueError('saved state missing edit')
    # Simulate composition while an earlier field's view is in flight.
    original_block = evaluate("document.querySelector('[data-k=b0]').value")
    evaluate("window.originalWorker=window.Worker;window.imeDelay=false;window.Worker=class extends window.originalWorker {postMessage(m,...rest){if(m.args[0]==='view'&&!window.imeDelay){window.imeDelay=true;setTimeout(()=>super.postMessage(m,...rest),1500)}else super.postMessage(m,...rest)}}")
    evaluate("(()=>{let e=document.querySelector('[data-k=b0]');e.value='IME補助';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("window.imeDelay === true", 'pending view before composition')
    evaluate("(()=>{let e=document.querySelector('[data-k=title]');window.imeNode=e;e.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));e.value='仮変換';e.dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:true,inputType:'insertCompositionText',data:'仮変換'}));})()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('IME補助')", 'other field save during composition')
    if not evaluate("window.imeNode === document.querySelector('[data-k=title]')") or evaluate("document.querySelector('[data-k=title]').value") != '仮変換': raise ValueError('composition node or text replaced')
    if evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('仮変換')"): raise ValueError('incomplete composition saved')
    evaluate("(()=>{let e=document.querySelector('[data-k=title]');e.value='日本語';e.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,data:'日本語'}));e.dispatchEvent(new InputEvent('input',{bubbles:true,isComposing:false,inputType:'insertText',data:'日本語'}));})()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('日本語') && document.getElementById('status').textContent === '保存しました'", 'completed composition save')
    evaluate("window.Worker=window.originalWorker")
    evaluate("(()=>{for(const [k,v] of [['title','議事😀'],['b0',"+json.dumps(original_block,ensure_ascii=False)+"]]){let e=document.querySelector('[data-k='+k+']');e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));}})()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1') === "+json.dumps(saved,ensure_ascii=False)+" && document.getElementById('status').textContent === '保存しました'", 'restore after composition')
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
    # A downloaded BS1 can be explicitly reviewed and restored; invalid input
    # and storage failure must never replace the current document.
    download = out / 'downloads'
    download.mkdir()
    pipe.call('Browser.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': str(download)})
    evaluate("document.querySelector('[data-k=backup-export]').click()")
    end = time.time() + 90
    while time.time() < end and not (download / 'bunsho-backup.bs1').exists(): time.sleep(.2)
    exported = download / 'bunsho-backup.bs1'
    if not exported.exists() or exported.read_text() != saved: raise ValueError('backup download mismatch')
    evaluate("(()=>{let e=document.querySelector('[data-k=title]');e.value='復元前';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('復元前')", 'edit before import')
    prior = evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')")
    def select_file(path):
        pipe.call('DOM.enable', {}, session)
        root = pipe.call('DOM.getDocument', {}, session)['root']['nodeId']
        node = pipe.call('DOM.querySelector', {'nodeId': root, 'selector': '#backup-file'}, session)['nodeId']
        pipe.call('DOM.setFileInputFiles', {'nodeId': node, 'files': [str(path)]}, session)
    select_file(exported)
    wait("document.getElementById('backup-dialog').open", 'backup preview')
    if evaluate("document.querySelector('#backup-preview [data-k=title]')?.value") != '連続入力': raise ValueError('preview mismatch')
    evaluate("document.getElementById('backup-cancel').click()")
    if evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')") != prior: raise ValueError('cancel changed storage')
    # Reset the input, as the user action does before selecting a file again.
    evaluate("document.getElementById('backup-file').value=''")
    select_file(exported)
    wait("document.getElementById('backup-dialog').open", 'backup preview again')
    evaluate("document.getElementById('backup-confirm').click()")
    wait("document.getElementById('status').textContent === 'バックアップから復元しました。'", 'restore backup')
    if evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')") != saved: raise ValueError('restore mismatch')
    if not evaluate("Object.keys(localStorage).some(k=>k.startsWith('itonami.bunsho.candidate.bs1.preimport.') && localStorage.getItem(k).includes('復元前'))"): raise ValueError('missing prior backup')
    evaluate("document.querySelector('[data-k=backup-restore]').click()")
    wait("document.getElementById('backup-dialog').open", 'prior backup preview')
    evaluate("document.getElementById('backup-confirm').click()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('復元前')", 'restore prior')
    bad = out / 'bad.bs1'
    bad.write_bytes(b'BS1|bad')
    evaluate("document.getElementById('backup-file').value=''")
    select_file(bad)
    wait("document.getElementById('status').textContent.includes('バックアップを読み込めません')", 'bad backup refusal')
    if evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')") != prior or evaluate("document.getElementById('backup-dialog').open"): raise ValueError('bad import changed state')
    for name, contents in [('utf8.bs1', b'BS1|\xff'), ('large.bs1', b'BS1|' + b'x' * 35000), ('unknown.bs1', b'OLD|document')]:
        invalid = out / name
        invalid.write_bytes(contents)
        evaluate("document.getElementById('status').textContent='' ; document.getElementById('backup-file').value=''")
        select_file(invalid)
        wait("document.getElementById('status').textContent.includes('バックアップを読み込めません')", name + ' refusal')
        if evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')") != prior or evaluate("document.getElementById('backup-dialog').open"): raise ValueError(name + ' changed state')
    evaluate("document.getElementById('backup-file').value=''")
    select_file(exported)
    wait("document.getElementById('backup-dialog').open", 'quota backup preview')
    evaluate("window.savedSetItem=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(k.includes('.preimport.'))throw Error('quota');return window.savedSetItem.call(this,k,v)};document.getElementById('backup-confirm').click()")
    wait("document.getElementById('status').textContent.includes('復元できませんでした')", 'backup quota refusal')
    if evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')") != prior: raise ValueError('quota import changed state')
    evaluate("Storage.prototype.setItem=window.savedSetItem")
    # Fail the second write after the recovery copy succeeds.
    backup_keys = set(evaluate("Object.keys(localStorage).filter(k=>k.startsWith('itonami.bunsho.candidate.bs1.preimport.'))"))
    evaluate("document.getElementById('backup-file').value='';document.getElementById('status').textContent=''")
    select_file(exported)
    wait("document.getElementById('backup-dialog').open", 'current-write failure preview')
    evaluate("Storage.prototype.setItem=function(k,v){if(k==='itonami.bunsho.candidate.bs1')throw Error('quota');return window.savedSetItem.call(this,k,v)};document.getElementById('backup-confirm').click()")
    wait("document.getElementById('status').textContent.includes('復元できませんでした')", 'current-write failure refusal')
    if evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')") != prior: raise ValueError('failed current write changed state')
    after_keys = set(evaluate("Object.keys(localStorage).filter(k=>k.startsWith('itonami.bunsho.candidate.bs1.preimport.'))"))
    new_keys = after_keys - backup_keys
    if len(new_keys) != 1 or evaluate("localStorage.getItem(" + json.dumps(next(iter(new_keys))) + ")") != prior: raise ValueError('pre-import copy missing after failed current write')
    evaluate("Storage.prototype.setItem=window.savedSetItem;document.getElementById('backup-file').value=''")
    # Return to the original exported fixture through the validated import path.
    select_file(exported)
    wait("document.getElementById('backup-dialog').open", 'return backup preview')
    evaluate("document.getElementById('backup-confirm').click()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('連続入力')", 'return to test state')
    second = pipe.call('Target.createTarget', {'url': url})['targetId']
    second_session = pipe.call('Target.attachToTarget', {'targetId': second, 'flatten': True})['sessionId']
    def second_eval(expr):
        result = pipe.call('Runtime.evaluate', {'expression': expr, 'returnByValue': True}, second_session)
        if 'exceptionDetails' in result: raise ValueError(result['exceptionDetails'])
        return result.get('result', {}).get('value')
    end = time.time() + 90
    while time.time() < end and second_eval("document.querySelector('[data-k=title]')?.value") != '連続入力': time.sleep(.2)
    if second_eval("document.querySelector('[data-k=title]')?.value") != '連続入力': raise TimeoutError('second tab')
    pipe.call('DOM.enable', {}, second_session)
    second_root = pipe.call('DOM.getDocument', {}, second_session)['root']['nodeId']
    second_file = pipe.call('DOM.querySelector', {'nodeId': second_root, 'selector': '#backup-file'}, second_session)['nodeId']
    pipe.call('DOM.setFileInputFiles', {'nodeId': second_file, 'files': [str(exported)]}, second_session)
    end = time.time() + 90
    while time.time() < end and not second_eval("document.getElementById('backup-dialog').open"): time.sleep(.2)
    if not second_eval("document.getElementById('backup-dialog').open"): raise TimeoutError('second tab backup preview')
    evaluate("(()=>{let e=document.querySelector('[data-k=title]');e.value='先の変更';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('先の変更') || document.getElementById('status').textContent.includes('保存できませんでした')", 'first tab write')
    if not evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('先の変更')"):
        raise ValueError('first tab write refused: ' + str(evaluate("document.getElementById('status').textContent")))
    second_eval("document.getElementById('backup-confirm').click()")
    end = time.time() + 90
    while time.time() < end and not second_eval("document.getElementById('status')?.textContent.includes('復元できませんでした')"): time.sleep(.2)
    if not second_eval("document.getElementById('status')?.textContent.includes('別のタブ')") or not evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('先の変更')"): raise ValueError('conflicting import clobbered state')
    second_eval("(()=>{let e=document.querySelector('[data-k=title]');e.value='後の変更';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    end = time.time() + 90
    while time.time() < end and not second_eval("document.getElementById('status')?.textContent.includes('保存できませんでした')"): time.sleep(.2)
    if not second_eval("document.getElementById('status')?.textContent.includes('保存できませんでした')"): raise TimeoutError('conflicting tab refusal')
    if not second_eval("document.getElementById('status')?.textContent.includes('別のタブ')"): raise ValueError('conflict reason not shown')
    if second_eval("document.querySelector('[data-k=title]')?.value") != '後の変更' or second_eval("document.getElementById('retry-save').hidden"): raise ValueError('conflicting edit was lost')
    second_eval("document.getElementById('status').textContent='';document.getElementById('retry-save').click()")
    end = time.time() + 90
    while time.time() < end and not second_eval("document.getElementById('status')?.textContent.includes('別のタブ')"): time.sleep(.2)
    if not second_eval("document.getElementById('status')?.textContent.includes('別のタブ')") or second_eval("document.querySelector('[data-k=title]')?.value") != '後の変更': raise ValueError('conflict retry lost input')
    saved = evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')")
    if '先の変更' not in saved or '後の変更' in saved: raise ValueError('concurrent write clobbered state')
    pipe.call('Target.closeTarget', {'targetId': second})
    evaluate("window.savedTimer=window.setTimeout;window.setTimeout=(f,n)=>window.savedTimer(f,n===30000?1:n)")
    evaluate("(()=>{let e=document.querySelector('[data-k=title]');e.value='時間切れ';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("document.getElementById('status').textContent.includes('時間内に完了しませんでした')", 'worker timeout')
    if evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')") != saved: raise ValueError('timeout clobbered storage')
    if evaluate("document.querySelector('[data-k=title]')?.value") != '時間切れ' or evaluate("document.getElementById('retry-save').hidden"): raise ValueError('timeout discarded input')
    evaluate("document.querySelector('[data-k=backup-export]').click()")
    if not evaluate("document.getElementById('status').textContent.includes('未保存')"): raise ValueError('backup allowed with unsaved input')
    evaluate("window.setTimeout=window.savedTimer;document.getElementById('retry-save').click()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('時間切れ') && document.getElementById('retry-save').hidden", 'timeout retry save')
    evaluate("(()=>{let e=document.querySelector('[data-k=title]');e.value='先の変更';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1') === " + json.dumps(saved,ensure_ascii=False), 'restore test fixture after retry')
    # Inject a timeout while this tab is actually hidden, then recover visibly.
    background = pipe.call('Target.createTarget', {'url': 'about:blank'})['targetId']
    wait("document.visibilityState === 'hidden'", 'hidden tab')
    evaluate("window.savedTimer=window.setTimeout;window.setTimeout=(f,n)=>window.savedTimer(f,n===30000?1:n)")
    evaluate("(()=>{let e=document.querySelector('[data-k=title]');e.value='背景の入力';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("document.getElementById('status').textContent.includes('時間内に完了しませんでした')", 'hidden timeout')
    pipe.call('Page.bringToFront', {}, session)
    wait("document.visibilityState === 'visible'", 'return to tab')
    if evaluate("document.querySelector('[data-k=title]')?.value") != '背景の入力' or evaluate("document.getElementById('retry-save').hidden") or evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')") != saved: raise ValueError('hidden timeout discarded input')
    pipe.call('Target.closeTarget', {'targetId': background})
    evaluate("window.setTimeout=window.savedTimer;document.getElementById('retry-save').click()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('背景の入力') && document.getElementById('retry-save').hidden", 'hidden edit retry')
    evaluate("(()=>{let e=document.querySelector('[data-k=title]');e.value='先の変更';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1') === " + json.dumps(saved,ensure_ascii=False), 'restore fixture after hidden retry')
    pipe.call('Page.reload', {}, session)
    wait("document.querySelector('[data-k=title]')?.value === '先の変更'", 'reload after timeout')
    evaluate("window.savedWorker=window.Worker;window.Worker=class extends window.savedWorker {postMessage(msg){if(msg.args[0]==='view'){this.terminate();queueMicrotask(()=>this.onerror(new Event('error')))}else super.postMessage(msg)}}")
    evaluate("(()=>{let e=document.querySelector('[data-k=title]');e.value='中断';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("document.getElementById('status').textContent.includes('保存できませんでした')", 'worker interruption')
    if evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')") != saved: raise ValueError('interrupted render clobbered storage')
    if evaluate("document.querySelector('[data-k=title]')?.value") != '中断' or evaluate("document.getElementById('retry-save').hidden"): raise ValueError('interrupted edit discarded')
    evaluate("window.Worker=window.savedWorker;document.getElementById('retry-save').click()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('中断') && document.getElementById('retry-save').hidden", 'interrupted edit retry')
    evaluate("(()=>{let e=document.querySelector('[data-k=title]');e.value='先の変更';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1') === " + json.dumps(saved,ensure_ascii=False), 'restore fixture after interruption')
    pipe.call('Page.reload', {}, session)
    wait("document.querySelector('[data-k=title]')?.value === '先の変更'", 'reload after interruption')
    evaluate("window.quotaSetter=Storage.prototype.setItem;Storage.prototype.setItem = function(){ throw new Error('quota'); }; (()=>{let e=document.querySelector('[data-k=title]');e.value='失敗';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("document.getElementById('status').textContent.includes('保存できませんでした')", 'storage failure')
    if evaluate("document.querySelector('[data-k=title]')?.value") != '失敗' or evaluate("document.getElementById('retry-save').hidden"): raise ValueError('quota discarded input')
    if evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')") != saved: raise ValueError('storage changed on failure')
    evaluate("Storage.prototype.setItem=window.quotaSetter;document.getElementById('retry-save').click()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('失敗') && document.getElementById('retry-save').hidden", 'quota retry save')
    evaluate("(()=>{let e=document.querySelector('[data-k=title]');e.value='先の変更';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1') === " + json.dumps(saved,ensure_ascii=False), 'restore fixture after quota')
    # One failed field must survive another field's successful redraw.
    old_block = evaluate("document.querySelector('[data-k=b0]').value")
    evaluate("window.partialSetter=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(v.includes('未保存タイトル'))throw Error('quota');return window.partialSetter.call(this,k,v)};(()=>{for(const [k,v] of [['title','未保存タイトル'],['b0','追加本文']]){let e=document.querySelector('[data-k='+k+']');e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));}})()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('追加本文')", 'other field save')
    if evaluate("document.querySelector('[data-k=title]')?.value") != '未保存タイトル' or evaluate("document.getElementById('retry-save').hidden"): raise ValueError('successful redraw erased another failed edit')
    evaluate("Storage.prototype.setItem=window.partialSetter;document.getElementById('retry-save').click()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('未保存タイトル') && localStorage.getItem('itonami.bunsho.candidate.bs1')?.includes('追加本文') && document.getElementById('retry-save').hidden", 'multiple edits retry')
    evaluate("(()=>{for(const [k,v] of [['title','先の変更'],['b0'," + json.dumps(old_block,ensure_ascii=False) + "]]){let e=document.querySelector('[data-k='+k+']');e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));}})()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1') === " + json.dumps(saved,ensure_ascii=False), 'restore fixture after multiple edits')
    evaluate("(()=>{let e=document.querySelector('[data-k=title]');e.value='x'.repeat(1025);e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("document.getElementById('status').textContent.includes('入力が長すぎます')", 'oversized unsaved input')
    if evaluate("document.querySelector('[data-k=title]')?.value.length") != 1025 or evaluate("document.getElementById('retry-save').hidden") or evaluate("localStorage.getItem('itonami.bunsho.candidate.bs1')") != saved: raise ValueError('oversized edit discarded or saved')
    evaluate("(()=>{let e=document.querySelector('[data-k=title]');e.value='先の変更';e.dispatchEvent(new Event('input',{bubbles:true}));})()")
    wait("localStorage.getItem('itonami.bunsho.candidate.bs1') === " + json.dumps(saved,ensure_ascii=False) + " && document.getElementById('retry-save').hidden && document.getElementById('status').textContent === '保存しました'", 'correct oversized input')
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
    if any(u.split('?', 1)[0].endswith('/favicon.ico') for u in requests): raise ValueError('unversioned favicon request')
    if not requests or any(not u.startswith(f'http://127.0.0.1:{server.server_port}/') for u in requests):
        raise ValueError('unexpected request ' + repr(requests))
    (out / 'result.json').write_text(json.dumps({'status': 'PASS', 'checks': ['backup-export-import-cancel-restore', 'backup-invalid-and-both-write-failures', 'init', 'edit-save', 'synthetic-composition-with-concurrent-redraw', 'queued-input', 'add', 'preview', 'reload', 'concurrent-write-refusal', 'worker-timeout-and-retry', 'hidden-timeout-and-retry', 'worker-interruption-and-retry', 'storage-failure-and-retry', 'multiple-unsaved-fields', 'oversized-input-recovery', 'corruption-refusal', 'digest-refusal', 'loopback-only']}, indent=2) + '\n')
    print('PASS_BUNSHO_BROWSER_UI: init, edit, reload and failure preservation')
finally:
    pipe.close()
    server.shutdown()
    server.server_close()
