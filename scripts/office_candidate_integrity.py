"""Validate the complete static office candidate before peer distribution."""
import base64
import hashlib
import json
import re
from pathlib import Path

FILES = frozenset(('app.js', 'build-receipt.json', 'bundle.js', 'client-runtime.json',
                   'draft-policy.kotoba', 'draft-policy.wasm', 'index.html',
                   'kotoba-client-runtime.js', 'program.kotoba', 'program.wasm',
                   'style.css', 'worker.js', '.well-known/did.json'))

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def candidate_files(build):
    build = Path(build)
    paths = list(build.rglob('*'))
    if (any(p.is_symlink() or not (p.is_file() or p.is_dir()) for p in paths)
            or {p.relative_to(build).as_posix() for p in paths if p.is_dir()} != {'.well-known'}
            or {p.relative_to(build).as_posix() for p in paths if p.is_file()} != FILES):
        raise ValueError('unexpected candidate files')
    return sorted((p for p in paths if p.is_file()), key=lambda p: p.relative_to(build).as_posix())

def validate(build, name):
    build = Path(build)
    candidate_files(build)
    expected = {'bunsho', 'hyokeisan', 'zuhyo'}
    if name not in expected:
        raise ValueError('unexpected app')
    did = json.loads((build / '.well-known/did.json').read_text())
    if did.get('id') != 'did:web:' + name + '.itonami.app' or did.get('@context') != ['https://www.w3.org/ns/did/v1']:
        raise ValueError('unexpected DID document')
    receipt = json.loads((build / 'build-receipt.json').read_text())
    for filename, key in (('program.kotoba', 'sourceSha256'), ('program.wasm', 'wasmSha256'),
                          ('draft-policy.kotoba', 'draftPolicySourceSha256'),
                          ('draft-policy.wasm', 'draftPolicyWasmSha256'),
                          ('kotoba-client-runtime.js', 'brokerSha256'), ('worker.js', 'workerSha256'),
                          ('.well-known/did.json', 'didSha256')):
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
