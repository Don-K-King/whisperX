import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildCompleteUploadPayload,
  mapTranscriptToSpeakerRows,
  parseToken,
  sanitizedError,
} from '../utils.js';

test('parseToken extracts tenant and roles', () => {
  const payload = Buffer.from(JSON.stringify({ tenant_id: 't-1', roles: ['admin'] })).toString('base64');
  const auth = parseToken(`h.${payload}.s`);
  assert.equal(auth.tenant_id, 't-1');
  assert.deepEqual(auth.roles, ['admin']);
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
