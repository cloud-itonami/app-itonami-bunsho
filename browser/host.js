// restricted-wasm-v1 host (KOTOBA-159). This page is the trusted shell: it holds the canonical
// runtime, verifies the guest document against the SHA-256 and source commit pinned at build time,
// and mounts it with mountRestrictedClientApp in an opaque-origin sandbox. The descriptor declares no
// operation, so the broker refuses every call before any dialog. The host reads nothing but
// ./host-data.js.
import { createClientConsentHost, createClientOperationBroker, mountRestrictedClientApp, verifyClientArtifact } from './kotoba-client-runtime.js';
import host from './host-data.js';

const container = document.getElementById('app');
try {
  const broker = createClientOperationBroker({ runtime: host.descriptor, consentHost: createClientConsentHost({ locale: 'ja' }) });
  const artifact = await verifyClientArtifact(new TextEncoder().encode(host.guest), host.artifact);
  await mountRestrictedClientApp({ artifact, container, broker });
} catch (error) {
  const p = document.createElement('p');
  p.className = 'problem';
  p.textContent = 'アプリを起動できませんでした。 ' + String(error?.message ?? error);
  container.replaceChildren(p);
}
