// Release gate (Decision 2026-11-22). Both must hold before a Bunsho release:
// 1. every disclosure page a declared operation names answers 200 (foreign-info-url, without #);
// 2. no feature that worked before the restricted-wasm-v1 move is still off (disabled-features.json).
// deployAllowed() returns every reason; run as a script it exits non-zero when one is left.
import { readFile } from 'node:fs/promises';
import { readFile as readJson } from 'node:fs/promises';
const descriptor = { operations: [] }; // Bunsho declares no operation (checked by the build)

export async function disabledFeatures(file = new URL('../disabled-features.json', import.meta.url)) {
  const data = JSON.parse(await readFile(file, 'utf8'));
  if (data.schema !== 'itonami.disabled-features.v1' || !Array.isArray(data.features)) throw new Error('disabled-features.json: unexpected shape');
  for (const f of data.features) if (typeof f.id !== 'string' || typeof f.label !== 'string' || typeof f.reason !== 'string') throw new Error('disabled-features.json: each feature needs id, label and reason');
  return data.features;
}

export function disclosurePages(d = descriptor) {
  return [...new Set(d.operations.map((op) => op.disclosure?.['foreign-info-url']).filter(Boolean)
    .map((url) => { const u = new URL(url); u.hash = ''; return u.href; }))];
}

export async function deployAllowed({ fetchImpl = globalThis.fetch, features, pages = disclosurePages() } = {}) {
  const reasons = [];
  for (const page of pages) {
    try {
      const response = await fetchImpl(page, { redirect: 'error', signal: AbortSignal.timeout(20_000) });
      if (response.status !== 200) reasons.push(`disclosure page ${page}: HTTP ${response.status}`);
    } catch (error) { reasons.push(`disclosure page ${page}: ${error.message}`); }
  }
  for (const f of features ?? await disabledFeatures()) reasons.push(`feature still off: ${f.id} (${f.label}): ${f.reason}`);
  return { ok: reasons.length === 0, reasons };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const { ok, reasons } = await deployAllowed();
  if (!ok) { console.error('Do not deploy:\n' + reasons.map((r) => `- ${r}`).join('\n')); process.exitCode = 1; }
  else console.log('Deploy gate passes: disclosure pages answer 200 and no feature is off.');
}
