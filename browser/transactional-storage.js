// Experimental browser-local storage primitive. Kotoba validates the state;
// this module only performs bounded IndexedDB I/O and transactional CAS.
// It is not wired into the application, does not migrate localStorage, and
// cannot serialize legacy writers which do not use this database.
const FORMAT = 'itonami.office.transactional-state.v2';
const STORE = 'records';
const CURRENT = 'current';
const ENCODER = new TextEncoder();

function scalarString(value) {
  if (typeof value !== 'string') return false;
  for (let i = 0; i < value.length; i++) {
    const c = value.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      if (++i >= value.length) return false;
      const d = value.charCodeAt(i);
      if (d < 0xdc00 || d > 0xdfff) return false;
    } else if (c >= 0xdc00 && c <= 0xdfff) return false;
  }
  return true;
}
function validateValue(value, maximum) {
  return typeof value === 'string' && value.length <= maximum &&
    scalarString(value) && ENCODER.encode(value).length <= maximum;
}
function validRecord(record, maximum) {
  return record && typeof record === 'object' && !Array.isArray(record) &&
    Object.keys(record).sort().join(',') === 'format,legacyAnchor,revision,value' &&
    record.format === FORMAT && Number.isSafeInteger(record.revision) &&
    record.revision > 0 && validateValue(record.value, maximum) &&
    (record.legacyAnchor === null || validateValue(record.legacyAnchor, maximum));
}
function decodeRecord(record, maximum) {
  if (record === undefined) return { revision: 0, value: null, legacyAnchor: null };
  if (!validRecord(record, maximum)) throw Error('invalid stored state');
  return { revision: record.revision, value: record.value, legacyAnchor: record.legacyAnchor };
}
function validExpected(expected, maximum) {
  return expected && Number.isSafeInteger(expected.revision) && expected.revision >= 0 &&
    ((expected.revision === 0 && expected.value === null && expected.legacyAnchor === null) ||
     (expected.revision > 0 && validateValue(expected.value, maximum) &&
      (expected.legacyAnchor === null || validateValue(expected.legacyAnchor, maximum))));
}

export async function openTransactionalStore(name, maximum) {
  if (!/^itonami\.office\.(bunsho|hyokeisan|zuhyo)\.v2$/.test(name) ||
      !Number.isSafeInteger(maximum) || maximum < 1 || maximum > 1000000) throw Error('invalid store configuration');
  const db = await new Promise((resolve, reject) => {
    let failed = false;
    const request = indexedDB.open(name, 1);
    request.onupgradeneeded = event => {
      if (event.oldVersion !== 0 || request.result.objectStoreNames.length !== 0) {
        request.transaction.abort();
        return;
      }
      request.result.createObjectStore(STORE);
    };
    request.onblocked = () => { failed = true; reject(Error('storage blocked')); };
    request.onerror = () => { failed = true; reject(Error('storage open failed')); };
    request.onsuccess = () => {
      if (failed) { request.result.close(); return; }
      const opened = request.result;
      try {
        if (opened.objectStoreNames.length !== 1 || !opened.objectStoreNames.contains(STORE)) throw Error('unexpected storage schema');
        const objectStore = opened.transaction(STORE, 'readonly').objectStore(STORE);
        if (objectStore.keyPath !== null || objectStore.autoIncrement) throw Error('unexpected storage schema');
        opened.onversionchange = () => opened.close();
        resolve(opened);
      } catch (error) { opened.close(); reject(error); }
    };
  });

  function readRawKey(key) {
    return new Promise((resolve, reject) => {
      let value;
      let tx;
      try {
        tx = db.transaction(STORE, 'readonly');
        const request = tx.objectStore(STORE).get(key);
        request.onsuccess = () => { value = request.result; };
        tx.oncomplete = () => resolve(value);
        tx.onabort = () => reject(Error('storage read aborted'));
        tx.onerror = () => {};
      } catch (error) { reject(error); }
    });
  }

  function readKey(key) {
    return readRawKey(key).then(value => decodeRecord(value, maximum));
  }
  function readRecoveryValue() {
    return readRawKey(CURRENT).then(record => {
      if (!record || typeof record !== 'object' || Array.isArray(record) ||
          typeof record.value !== 'string' || record.value.length > 1000000)
        throw Error('recovery value unavailable');
      return record.value;
    });
  }

  // `initialLegacyAnchor` records the exact legacy value selected by the
  // caller during initial import. It never reads or mutates localStorage;
  // a host must obtain explicit user choice and handle later divergence.
  function compareAndSwap(expected, next, backup = false, initialLegacyAnchor = null) {
    if (!validExpected(expected, maximum) || !validateValue(next, maximum) || typeof backup !== 'boolean' ||
        !(initialLegacyAnchor === null || validateValue(initialLegacyAnchor, maximum)) ||
        (expected.revision !== 0 && initialLegacyAnchor !== null))
      return Promise.reject(Error('invalid state request'));
    return new Promise((resolve, reject) => {
      let tx, outcome;
      try {
        tx = db.transaction(STORE, 'readwrite', { durability: 'strict' });
        // Fail closed if the browser cannot report the requested durability.
        // This requests strict durability; it is not a power-loss proof.
        if (tx.durability !== 'strict') { tx.abort(); throw Error('strict durability unavailable'); }
        const store = tx.objectStore(STORE);
        const request = store.get(CURRENT);
        request.onsuccess = () => {
          try {
            const current = decodeRecord(request.result, maximum);
            if (current.revision !== expected.revision || current.value !== expected.value ||
                current.legacyAnchor !== expected.legacyAnchor) {
              outcome = { status: 'conflict', current };
              return;
            }
            if (current.revision === Number.MAX_SAFE_INTEGER) throw Error('revision exhausted');
            const revision = current.revision + 1;
            if (backup && current.revision > 0) store.add(request.result, 'backup:' + String(current.revision).padStart(16, '0'));
            const legacyAnchor = current.revision === 0 ? initialLegacyAnchor : current.legacyAnchor;
            store.put({ format: FORMAT, revision, value: next, legacyAnchor }, CURRENT);
            outcome = { status: 'committed', current: { revision, value: next, legacyAnchor } };
          } catch (_) { tx.abort(); }
        };
        tx.oncomplete = () => outcome ? resolve(outcome) : reject(Error('storage result missing'));
        tx.onabort = () => reject(Error('storage transaction aborted'));
        tx.onerror = () => {};
      } catch (error) { reject(error); }
    });
  }

  function readLatestBackup() {
    return new Promise((resolve, reject) => {
      let tx, value;
      try {
        tx = db.transaction(STORE, 'readonly');
        const range = IDBKeyRange.bound('backup:', 'backup;');
        const request = tx.objectStore(STORE).openCursor(range, 'prev');
        request.onsuccess = () => { value = request.result?.value; };
        tx.oncomplete = () => {
          try { resolve(value === undefined ? null : decodeRecord(value, maximum)); }
          catch (error) { reject(error); }
        };
        tx.onabort = () => reject(Error('storage backup read aborted'));
        tx.onerror = () => {};
      } catch (error) { reject(error); }
    });
  }

  return {
    read: () => readKey(CURRENT),
    readRecoveryValue,
    readLatestBackup,
    readBackup: revision => {
      if (!Number.isSafeInteger(revision) || revision < 1) return Promise.reject(Error('invalid backup revision'));
      return readKey('backup:' + String(revision).padStart(16, '0'));
    },
    compareAndSwap,
    close: () => db.close(),
  };
}
