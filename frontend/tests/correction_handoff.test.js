import test from 'node:test';
import assert from 'node:assert/strict';

import {
  cleanupExpiredCorrectionHandoffs,
  consumeCorrectionHandoff,
  createCorrectionHandoff,
} from '../correction_handoff.js';

function createMemoryStorage() {
  const map = new Map();
  return {
    get length() {
      return map.size;
    },
    key(index) {
      return [...map.keys()][index] || null;
    },
    getItem(key) {
      return map.has(key) ? map.get(key) : null;
    },
    setItem(key, value) {
      map.set(String(key), String(value));
    },
    removeItem(key) {
      map.delete(String(key));
    },
  };
}

test('create and consume handoff roundtrip', () => {
  const storage = createMemoryStorage();
  const handoffId = createCorrectionHandoff(
    {
      token: 'dev:tenant-a:reviewer:u-1',
      jobId: 'job_1',
      tenantId: 'tenant-a',
      theme: 'dark',
    },
    {
      storage,
      nowMs: 1000,
      handoffId: 'handoff-1',
    },
  );
  assert.equal(handoffId, 'handoff-1');

  const consumed = consumeCorrectionHandoff('handoff-1', {
    storage,
    nowMs: 1200,
  });
  assert.deepEqual(consumed, {
    token: 'dev:tenant-a:reviewer:u-1',
    jobId: 'job_1',
    tenantId: 'tenant-a',
    theme: 'dark',
  });
  assert.equal(storage.length, 0);
});

test('consumeCorrectionHandoff drops expired payload', () => {
  const storage = createMemoryStorage();
  createCorrectionHandoff(
    {
      token: 't',
      jobId: 'job_1',
      tenantId: 'tenant-a',
    },
    {
      storage,
      nowMs: 1000,
      ttlMs: 100,
      handoffId: 'handoff-2',
    },
  );
  const consumed = consumeCorrectionHandoff('handoff-2', {
    storage,
    nowMs: 1200,
  });
  assert.equal(consumed, null);
  assert.equal(storage.length, 0);
});

test('cleanupExpiredCorrectionHandoffs removes stale and broken records', () => {
  const storage = createMemoryStorage();
  storage.setItem('evodox-correction-handoff:stale', JSON.stringify({ expiresAt: 10 }));
  storage.setItem('evodox-correction-handoff:fresh', JSON.stringify({ expiresAt: 9999 }));
  storage.setItem('evodox-correction-handoff:broken', '{');
  storage.setItem('unrelated', 'x');

  const deleted = cleanupExpiredCorrectionHandoffs({ storage, nowMs: 100 });
  assert.equal(deleted, 2);
  assert.equal(storage.getItem('evodox-correction-handoff:fresh') !== null, true);
  assert.equal(storage.getItem('unrelated'), 'x');
});

