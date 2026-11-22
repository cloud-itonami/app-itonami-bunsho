// The release gate (Decision 2026-11-22). Negative control: with no disclosure page to wait for,
// a release stays blocked while a feature from before the move is still off.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { deployAllowed, disabledFeatures } from './deploy-gate.mjs';

const ok200 = async () => new Response('', { status: 200 });

test('blocked while a feature from before the move is off; allowed only when none is', async () => {
  const ids = (await disabledFeatures()).map((f) => f.id);
  assert.deepEqual(ids, ['document-kept', 'backup-export']);
  assert.equal((await deployAllowed({ fetchImpl: ok200 })).ok, false);
  assert.deepEqual(await deployAllowed({ fetchImpl: ok200, features: [] }), { ok: true, reasons: [] });
});

test('the list matches the code', async () => {
  const build = await readFile(new URL('./build-browser.py', import.meta.url), 'utf8');
  const app = await readFile(new URL('../browser/app.js', import.meta.url), 'utf8');
  // document-kept: listed while local-state is memory and the app stops without storage.
  assert.equal((await disabledFeatures()).some((f) => f.id === 'document-kept'), /'adapter': 'memory'/.test(build) && /if \(!storageAvailable\(\)\)/.test(app));
  // backup-export: listed while exports are anchor downloads, which the sandbox blocks.
  assert.equal((await disabledFeatures()).some((f) => f.id === 'backup-export'), /link\.download = /.test(app));
});

test('the 8 MiB mount budget is checked by the build, and the backup bound is unchanged', async () => {
  const make = await readFile(new URL('./make-restricted.mjs', import.meta.url), 'utf8');
  assert.match(make, /guest\.length > 8388608/);
  const app = await readFile(new URL('../browser/app.js', import.meta.url), 'utf8');
  assert.match(app, /const LIMIT = 35000;/);
});
