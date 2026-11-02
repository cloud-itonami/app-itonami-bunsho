// Experimental browser host adapter; Kotoba owns state validation and the UI
// owns explicit migration consent. This module never writes the legacy store.
import { openTransactionalStore } from './transactional-storage.js';

export async function openManagedStore(name, maximum, readLegacy) {
  if (typeof readLegacy !== 'function') throw Error('legacy reader required');
  const store = await openTransactionalStore(name, maximum);
  function legacy() {
    const value = readLegacy();
    if (value !== null && typeof value !== 'string') throw Error('invalid legacy read');
    return value;
  }
  async function inspect() {
    const current = await store.read();
    const observedLegacy = legacy();
    return { current, legacy: observedLegacy,
      legacyMatches: current.revision === 0 || current.legacyAnchor === observedLegacy };
  }
  async function commit(expected, next, { backup = false, initialLegacyAnchor = null } = {}) {
    const anchor = expected.revision === 0 ? initialLegacyAnchor : expected.legacyAnchor;
    // The caller previews and obtains the user's choice before passing a
    // legacy value here. Checking is not an atomic lock on localStorage.
    if (legacy() !== anchor) return { status: 'legacy-changed' };
    const result = await store.compareAndSwap(expected, next, backup, initialLegacyAnchor);
    if (result.status !== 'committed') return result;
    try {
      if (legacy() !== anchor) return { status: 'legacy-changed-after-commit', current: result.current };
    } catch (_) { return { status: 'legacy-unreadable-after-commit', current: result.current }; }
    return result;
  }
  return { inspect, commit, readLatestBackup: store.readLatestBackup, close: store.close };
}
