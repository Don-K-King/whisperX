import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildCompleteUploadPayload,
  deriveProgress,
  jobActionsForStatus,
  mapTranscriptToSpeakerRows,
  nextPollingIntervalMs,
  parseToken,
  sanitizedError,
  sha256HexFromArrayBuffer,
  uploadFileToPresignedUrl,
} from '../utils.js';

test('parseToken extracts tenant and roles', () => {
  const payload = Buffer.from(JSON.stringify({ tenant_id: 't-1', roles: ['admin'] })).toString('base64');
  const auth = parseToken(`h.${payload}.s`);
  assert.equal(auth.tenant_id, 't-1');
  assert.deepEqual(auth.roles, ['admin']);
});

test('parseToken supports dev token format', () => {
  const auth = parseToken('dev:tenant-a:admin,user:alice');
  assert.equal(auth.tenant_id, 'tenant-a');
  assert.deepEqual(auth.roles, ['admin', 'user']);
});

test('sanitizedError hides details and keeps correlation id', () => {
  assert.equal(sanitizedError({ error_code: 'auth.invalid', correlation_id: 'corr-1', detail: 'secret' }), 'auth.invalid (corr-1)');
});

test('buildCompleteUploadPayload creates tenant-scoped object_key', () => {
  const payload = buildCompleteUploadPayload({
    tenantId: 'tenant-a',
    jobId: 'job_1',
    filename: 'meeting.mp4',
    uploadSessionId: 'up_1',
    checksumSha256: 'a'.repeat(64),
  });
  assert.equal(payload.upload_session_id, 'up_1');
  assert.equal(payload.object_key, 'tenant/tenant-a/job_1/meeting.mp4');
  assert.equal(payload.checksum_sha256, 'a'.repeat(64));
});

test('mapTranscriptToSpeakerRows maps transcript API payload for frontend rendering', () => {
  const rows = mapTranscriptToSpeakerRows({
    version: 1,
    segments: [
      { start: 0.0, end: 1.2, speaker: 'SPEAKER_00', text: 'Hallo Welt' },
      { start: 1.2, end: 2.0, speaker: 'SPEAKER_01', text: 'Wie geht es?' },
    ],
  });

  assert.equal(rows.length, 2);
  assert.deepEqual(rows[0], {
    speaker: 'SPEAKER_00',
    timeRange: '00:00:00 - 00:00:01',
    text: 'Hallo Welt',
  });
});

test('deriveProgress uses milestone defaults when API omits progress', () => {
  assert.equal(deriveProgress({ status: 'queued' }), 5);
  assert.equal(deriveProgress({ status: 'processing' }), 20);
  assert.equal(deriveProgress({ status: 'completed' }), 100);
});

test('jobActionsForStatus returns status-dependent lifecycle actions', () => {
  assert.deepEqual(jobActionsForStatus('processing'), { canPause: true, canResume: false, canDelete: false });
  assert.deepEqual(jobActionsForStatus('paused'), { canPause: false, canResume: true, canDelete: true });
  assert.deepEqual(jobActionsForStatus('completed'), { canPause: false, canResume: false, canDelete: true });
});

test('nextPollingIntervalMs backs off on 429 and resets on success', () => {
  assert.equal(nextPollingIntervalMs({ currentMs: 5000, statusCode: 429 }), 10000);
  assert.equal(nextPollingIntervalMs({ currentMs: 30000, statusCode: 429 }), 30000);
  assert.equal(nextPollingIntervalMs({ currentMs: 30000, statusCode: 200 }), 5000);
});

test('sha256HexFromArrayBuffer returns deterministic digest', async () => {
  const buffer = new TextEncoder().encode('abc').buffer;
  const digest = await sha256HexFromArrayBuffer(buffer);
  assert.equal(digest, 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
});

test('uploadFileToPresignedUrl performs PUT and returns checksum', async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push([url, options]);
    return { ok: true, status: 200 };
  };
  try {
    const file = new Blob(['hello'], { type: 'video/mp4' });
    const checksum = await uploadFileToPresignedUrl({
      presignedUrl: 'https://object.local/upload',
      file,
      contentType: 'video/mp4',
    });

    assert.equal(checksum, '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824');
    assert.equal(calls.length, 1);
    assert.equal(calls[0][0], 'https://object.local/upload');
    assert.equal(calls[0][1].method, 'PUT');
    assert.equal(calls[0][1].headers['Content-Type'], 'video/mp4');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('uploadFileToPresignedUrl reports progress callback in fetch fallback', async () => {
  const originalFetch = globalThis.fetch;
  const updates = [];
  globalThis.fetch = async () => ({ ok: true, status: 200 });
  try {
    const file = new Blob(['hello'], { type: 'video/mp4' });
    await uploadFileToPresignedUrl({
      presignedUrl: 'https://object.local/upload',
      file,
      contentType: 'video/mp4',
      onProgress: (value) => updates.push(value),
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.deepEqual(updates, [100]);
});
