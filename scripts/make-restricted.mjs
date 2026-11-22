// Turn the built Bunsho candidate (scripts/build-browser.py OUT) into the restricted-wasm-v1 layout
// (KOTOBA-159), in place:
// - index.html becomes the trusted host page (browser/host.html, host.js) with the canonical runtime;
// - the app becomes one guest document: browser/index.html's body with app.js, managed-storage.js,
//   transactional-storage.js and bundle.js (the two wasm programs and the Amu static host's text)
//   inlined as one module script, and style.css inline; pinned by SHA-256 and the source commit in
//   host-data.js, verified and mounted by the host in an opaque-origin sandbox.
// The page policy admits the runtime's guest preamble, the guest script and the guest style by hash,
// 'wasm-unsafe-eval' for the two programs and worker-src blob: for the static host. The guest's own
// policy is the runtime's (connect-src 'none'). Usage: node scripts/make-restricted.mjs OUT COMMIT
import { createHash } from 'node:crypto';
import { readFile, rm, writeFile, copyFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { bundleModules } from './guest-bundle.mjs';
import { checkNoSubmit } from './check-no-submit.mjs';

const [out, commit] = process.argv.slice(2);
if (!out || !/^[0-9a-f]{40}$/.test(commit ?? '')) throw new Error('usage: make-restricted.mjs OUT COMMIT (40-hex source commit)');
const root = fileURLToPath(new URL('../', import.meta.url));
const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');
const cspHash = (text) => `'sha256-${createHash('sha256').update(text, 'utf8').digest('base64')}'`;
const read = (p) => readFile(join(out, p), 'utf8');

const descriptor = JSON.parse(await read('client-runtime.json'));
const runtime = await import(resolve(out, 'kotoba-client-runtime.js'));
const problems = runtime.clientRuntimeProblems(descriptor, [], 'https://bunsho.itonami.app');
if (problems.length) throw new Error(`invalid descriptor: ${JSON.stringify(problems)}`);
if (runtime.clientRuntimeConnectSrc(descriptor, [], [], 'https://bunsho.itonami.app') !== "connect-src 'none'") throw new Error('Bunsho declares no operation');

const workerSource = await read('worker.js');
const bundle = (await read('bundle.js')) + 'export const workerSource = ' + JSON.stringify(workerSource) + ';\n';
const modules = { 'app.js': await read('app.js'), 'managed-storage.js': await read('managed-storage.js'),
  'transactional-storage.js': await read('transactional-storage.js'), 'bundle.js': bundle };
const script = bundleModules(modules, 'app.js');
checkNoSubmit(script, 'the restricted guest script');
const style = await read('style.css');
if (/<\/style/i.test(style)) throw new Error('style.css contains </style');
const page = await read('index.html');
const body = page.slice(page.indexOf('<body>'), page.lastIndexOf('</body>'));
if (!body.startsWith('<body>')) throw new Error('browser/index.html has no body');
const guestBody = body.replace(/<script\b[^>]*><\/script>\s*/g, '');
const guest = `<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>itonami Bunsho</title><style>${style}</style></head>\n${guestBody}<script type="module">${script}</script>\n</body></html>\n`;
checkNoSubmit(guest.replace(script, ''), 'the restricted guest');
if (guest.length > 8388608) throw new Error('the guest exceeds the 8 MiB mount budget');
const guestBytes = new TextEncoder().encode(guest);
const artifact = { revision: commit, sha256: sha(guestBytes), 'max-bytes': guestBytes.byteLength };
const preamble = /^const GUEST_PREAMBLE = '<script>([^'\\]*)<\/script>';$/m.exec(await read('kotoba-client-runtime.js'))?.[1];
if (!preamble) throw new Error('the canonical runtime has no GUEST_PREAMBLE this build can hash');
const csp = `default-src 'none'; script-src 'self' 'wasm-unsafe-eval' ${cspHash(preamble)} ${cspHash(script)}; style-src 'self' ${cspHash(style)}; worker-src blob:; img-src data:; connect-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'`;

const host = await readFile(join(root, 'browser/host.html'), 'utf8');
if (host.split('@CSP@').length !== 2) throw new Error('host.html has no CSP build marker');
await writeFile(join(out, 'index.html'), host.replace('@CSP@', () => csp));
for (const name of ['host.js', 'host.css']) await copyFile(join(root, 'browser', name), join(out, name));
await writeFile(join(out, 'host-data.js'), `export default ${JSON.stringify({ descriptor, artifact, guest }, null, 1)};\n`);
// The app's own files are now inside the guest; only the host and its runtime are served.
for (const name of ['app.js', 'managed-storage.js', 'transactional-storage.js', 'bundle.js', 'style.css', 'worker.js']) await rm(join(out, name));
const receipt = JSON.parse(await read('build-receipt.json'));
receipt.profile = descriptor.profile;
receipt.guest = artifact;
receipt.hostSha256 = sha(await readFile(join(out, 'index.html')));
receipt.hostJsSha256 = sha(await readFile(join(out, 'host.js')));
receipt.hostDataSha256 = sha(await readFile(join(out, 'host-data.js')));
await writeFile(join(out, 'build-receipt.json'), JSON.stringify(receipt, null, 2) + '\n');
console.log('RESTRICTED_BUNSHO_GUEST', artifact.sha256, artifact['max-bytes']);
