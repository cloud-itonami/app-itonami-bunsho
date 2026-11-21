// Validates this app's static client-runtime descriptor with the canonical
// kotoba-lang/kotoba lib/kotoba.wasmWebcomponent broker module (never a local copy of its
// rules). Usage: node scripts/check-client-runtime.mjs <path/to/kotoba-client-runtime.js>
// (or set KOTOBA_CLIENT_RUNTIME to that path)
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const here = new URL('..', import.meta.url);
const read = p => readFileSync(new URL(p, here), 'utf8');
const pin = JSON.parse(read('client-runtime.pin.json'));
const modulePath = process.argv[2] ?? process.env.KOTOBA_CLIENT_RUNTIME;
if (!modulePath) throw new Error('pass the path of the canonical kotoba-client-runtime.js (or set KOTOBA_CLIENT_RUNTIME)');

const digest = createHash('sha256').update(readFileSync(modulePath)).digest('hex');
if (digest !== pin.sha256) throw new Error(`broker digest ${digest} does not match pin ${pin.sha256}`);
const broker = await import(pathToFileURL(modulePath).href);

const runtime = JSON.parse(read('cljs/public/client-runtime.json'));
const appOrigin = pin['app-origin'];
const problems = broker.clientRuntimeProblems(runtime, [], appOrigin);
if (problems.length) throw new Error(`descriptor problems: ${JSON.stringify(problems)}`);

// Negative control: the same validator must refuse an app-origin endpoint.
const widened = { ...runtime, operations: [{ capability: 'probe/app-origin', service: 'app-origin', operation: 'read',
  consent: 'each-operation', 'data-categories': ['probe'], endpoint: { origin: appOrigin, method: 'GET', path: '/xrpc/probe' } }] };
if (!broker.clientRuntimeProblems(widened, ['probe/app-origin'], appOrigin).length)
  throw new Error('negative control failed: an app-origin endpoint was accepted');

const connectSrc = broker.clientRuntimeConnectSrc(runtime, [], [], appOrigin);
const html = read('cljs/public/index.html');
if (!html.includes(`<meta http-equiv="Content-Security-Policy" content="${connectSrc}">`))
  throw new Error(`index.html does not carry the derived CSP: ${connectSrc}`);

const did = JSON.parse(read('cljs/public/.well-known/did.json'));
if (did.id !== `did:web:${new URL(appOrigin).host}`) throw new Error(`did.json id ${did.id} does not match ${appOrigin}`);

console.log(`ok: descriptor valid, ${connectSrc}, ${did.id}`);
