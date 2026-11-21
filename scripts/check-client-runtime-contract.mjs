// Checks this app against the pinned canonical client runtime (KOTOBA-159, 2026-11-22 contract).
// Usage: node scripts/check-client-runtime-contract.mjs <kotoba-client-runtime.js> <pin.json> <client-runtime.json> [app-origin]
// It never carries a copy of the runtime's rules: every verdict comes from the pinned module.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const [modulePath, pinPath, descriptorPath, originArg] = process.argv.slice(2);
if (!modulePath || !pinPath || !descriptorPath) throw new Error('usage: <runtime.js> <pin.json> <client-runtime.json> [app-origin]');
const pin = JSON.parse(readFileSync(pinPath, 'utf8'));
const digest = createHash('sha256').update(readFileSync(modulePath)).digest('hex');
if (digest !== pin.sha256) throw new Error(`runtime digest ${digest} does not match pin ${pin.sha256}`);
const runtime = await import(pathToFileURL(resolve(modulePath)).href);
const appOrigin = originArg ?? pin['app-origin'] ?? 'https://app.invalid';
const descriptor = JSON.parse(readFileSync(descriptorPath, 'utf8'));
const capabilities = (descriptor.operations ?? []).map((op) => op.capability);
const fail = (message) => { throw new Error(message); };

const problems = runtime.clientRuntimeProblems(descriptor, capabilities, appOrigin);
if (problems.length) fail(`descriptor problems: ${JSON.stringify(problems)}`);

// Controls use a synthetic public service; none of them is declared by the app.
const disclosure = { recipient: 'Example Recipient K.K.', country: 'JP', data: ['検索語'], 'special-care': false,
  purpose: '契約の確認のための合成の操作です。', frequency: 'one-time', withdrawal: '設定 › 許可した送信' };
const base = { capability: 'probe/read', service: 'probe', operation: 'read', consent: 'each-operation',
  'data-categories': ['query'], endpoint: { origin: 'https://probe.example.com', method: 'GET', path: '/probe' } };
const check = (operation) => runtime.clientRuntimeProblems({ ...descriptor, operations: [operation] }, ['probe/read'], appOrigin);

const positive = check({ ...base, disclosure });
if (positive.length) fail(`positive control rejected: ${JSON.stringify(positive)}`);
const missing = check(base);
if (!missing.some((p) => p.error === 'invalid-disclosure')) fail(`missing disclosure was not refused: ${JSON.stringify(missing)}`);
for (const key of ['recipient', 'country', 'data', 'purpose', 'frequency', 'withdrawal']) {
  const { [key]: _omitted, ...partial } = disclosure;
  if (!check({ ...base, disclosure: partial }).some((p) => p.error === 'invalid-disclosure')) fail(`disclosure without ${key} was accepted`);
}
const foreign = check({ ...base, disclosure: { ...disclosure, country: 'US' } });
if (!foreign.some((p) => p.error === 'invalid-disclosure')) fail('foreign recipient without country-name/foreign-info-url was accepted');
const internal = { ...base, disclosure, endpoint: { ...base.endpoint, origin: 'https://192.168.1.10' } };
if (!check(internal).some((p) => p.error === 'internal-address-requires-lan-scope')) fail('internal address without scope: lan was accepted');
const lanProblems = check({ ...internal, scope: 'lan' });
if (lanProblems.length) fail(`scope: lan control rejected: ${JSON.stringify(lanProblems)}`);

// Only a broker made by createClientOperationBroker may be mounted (finding R4).
let refused = false;
try {
  await runtime.mountRestrictedClientApp({ artifact: { html: '<p></p>' }, container: {}, broker: { invoke: async () => null } });
} catch (error) { refused = /trusted host broker required/.test(String(error?.message)); }
if (!refused) fail('a hand-made broker was not refused');

console.log(`ok: ${descriptorPath} valid with runtime ${digest.slice(0, 12)}; ${descriptor.operations?.length ?? 0} operation(s); `
  + 'missing disclosure fields, foreign recipient without notice, internal address without scope: lan and a hand-made broker are refused');
