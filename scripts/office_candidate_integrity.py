"""Validate the complete static office candidate before peer distribution."""
import base64
import hashlib
import json
import re
from pathlib import Path

FILES = frozenset(('app.js', 'build-receipt.json', 'bundle.js', 'client-runtime.json',
                   'draft-policy.kotoba', 'draft-policy.wasm', 'index.html',
                   'kotoba-client-runtime.js', 'program.kotoba', 'program.wasm',
                   'style.css', 'worker.js'))

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def validate(build):
    build = Path(build)
    files = list(build.iterdir())
    if any(not p.is_file() or p.is_symlink() for p in files) or {p.name for p in files} != FILES:
        raise ValueError('unexpected candidate files')
    receipt = json.loads((build / 'build-receipt.json').read_text())
    for filename, key in (('program.kotoba', 'sourceSha256'), ('program.wasm', 'wasmSha256'),
                          ('draft-policy.kotoba', 'draftPolicySourceSha256'),
                          ('draft-policy.wasm', 'draftPolicyWasmSha256'),
                          ('kotoba-client-runtime.js', 'brokerSha256'), ('worker.js', 'workerSha256')):
        if sha((build / filename).read_bytes()) != receipt[key]:
            raise ValueError('candidate digest mismatch: ' + filename)
    if not re.fullmatch(r'[0-9a-f]{40}', receipt['draftPolicyRevision']):
        raise ValueError('invalid policy revision')
    bundle = (build / 'bundle.js').read_text()
    for exported, filename, digest in (('wasmBase64', 'program.wasm', 'wasmSha256'),
                                       ('draftPolicyBase64', 'draft-policy.wasm', 'draftPolicyWasmSha256')):
        values = re.findall(r'^export const ' + exported + r' = ("[A-Za-z0-9+/=]*");$', bundle, re.M)
        if len(values) != 1 or base64.b64decode(json.loads(values[0]), validate=True) != (build / filename).read_bytes():
            raise ValueError('bundle bytes mismatch: ' + exported)
        digests = re.findall(r'^export const ' + ('wasmSha256' if exported == 'wasmBase64' else 'draftPolicySha256') + r' = "([0-9a-f]{64})";$', bundle, re.M)
        if len(digests) != 1 or digests[0] != receipt[digest]:
            raise ValueError('bundle digest mismatch: ' + exported)
    return receipt
