import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildCompleteUploadPayload,
  deriveProgress,
  estimateTranscriptionDurationMs,
  jobActionsForStatus,
  mapTranscriptToSpeakerAliases,
  mapTranscriptToSpeakerBlocks,
  mapTranscriptToSpeakerRows,
  nextPollingIntervalMs,
  parseToken,
  resolveDisplayedProgress,
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
    speakerKey: 'SPEAKER_00',
    speaker: 'SPEAKER_00',
    timeRange: '00:00:00 - 00:00:01',
    text: 'Hallo Welt',
  });
});

test('mapTranscriptToSpeakerRows prefers persisted speaker labels for display', () => {
  const rows = mapTranscriptToSpeakerRows({
    version: 2,
    speaker_labels: { SPEAKER_00: 'Patrick' },
    segments: [
      { start: 0.0, end: 1.2, speaker: 'SPEAKER_00', text: 'Hallo Welt' },
    ],
  });

  assert.equal(rows[0].speakerKey, 'SPEAKER_00');
  assert.equal(rows[0].speaker, 'Patrick');
});

test('mapTranscriptToSpeakerBlocks merges only consecutive segments for same speaker', () => {
  const blocks = mapTranscriptToSpeakerBlocks({
    version: 3,
    speaker_labels: { SPEAKER_01: 'Patrick', SPEAKER_02: 'Angela' },
    segments: [
      { start: 0.0, end: 2.0, speaker: 'SPEAKER_01', text: 'Erster Satz.' },
      { start: 2.0, end: 4.0, speaker: 'SPEAKER_01', text: 'Zweiter Satz.' },
      { start: 4.0, end: 5.0, speaker: 'SPEAKER_02', text: 'Antwort.' },
      { start: 5.0, end: 6.0, speaker: 'SPEAKER_01', text: 'Rueckfrage.' },
    ],
  });

  assert.equal(blocks.length, 3);
  assert.deepEqual(blocks[0], {
    speakerKey: 'SPEAKER_01',
    speaker: 'Patrick',
    timeRange: '00:00:00 - 00:00:04',
    text: 'Erster Satz.\nZweiter Satz.',
  });
  assert.deepEqual(blocks[1], {
    speakerKey: 'SPEAKER_02',
    speaker: 'Angela',
    timeRange: '00:00:04 - 00:00:05',
    text: 'Antwort.',
  });
  assert.deepEqual(blocks[2], {
    speakerKey: 'SPEAKER_01',
    speaker: 'Patrick',
    timeRange: '00:00:05 - 00:00:06',
    text: 'Rueckfrage.',
  });
});

test('mapTranscriptToSpeakerAliases keeps segment order and includes persisted aliases', () => {
  const aliases = mapTranscriptToSpeakerAliases({
    speaker_labels: { SPEAKER_99: 'Gast', SPEAKER_01: 'Patrick' },
    segments: [
      { speaker: 'SPEAKER_01', text: 'A' },
      { speaker: 'SPEAKER_02', text: 'B' },
      { speaker: 'SPEAKER_01', text: 'C' },
    ],
  });

  assert.deepEqual(aliases, [
    { speakerKey: 'SPEAKER_01', alias: 'Patrick' },
    { speakerKey: 'SPEAKER_02', alias: '' },
    { speakerKey: 'SPEAKER_99', alias: 'Gast' },
  ]);
});

test('deriveProgress uses milestone defaults when API omits progress', () => {
  assert.equal(deriveProgress({ status: 'queued' }), 5);
  assert.equal(deriveProgress({ status: 'processing' }), 20);
  assert.equal(deriveProgress({ status: 'cancel_requested' }), 20);
  assert.equal(deriveProgress({ status: 'completed' }), 100);
});

test('resolveDisplayedProgress interpolates monotonically between server updates', () => {
  const initial = resolveDisplayedProgress({
    job: { job_id: 'job-1', status: 'processing', progress: 20 },
    nowMs: 0,
  });
  const second = resolveDisplayedProgress({
    job: { job_id: 'job-1', status: 'processing', progress: 20 },
    previousState: initial.state,
    nowMs: 6000,
  });

  assert.equal(initial.displayProgress, 20);
  assert.ok(second.displayProgress >= initial.displayProgress);
  assert.ok(second.displayProgress <= 99);
});

test('resolveDisplayedProgress can advance beyond 59 in long processing phases but never reaches 100 before terminal', () => {
  let current = resolveDisplayedProgress({
    job: { job_id: 'job-2', status: 'processing', progress: 20 },
    nowMs: 0,
    hasFreshServerSnapshot: true,
  });

  for (let nowMs = 5000; nowMs <= 360000; nowMs += 5000) {
    current = resolveDisplayedProgress({
      job: { job_id: 'job-2', status: 'processing', progress: 20 },
      previousState: current.state,
      nowMs,
      hasFreshServerSnapshot: true,
    });
  }

  assert.ok(current.displayProgress > 59);
  assert.ok(current.displayProgress <= 99);
});

test('resolveDisplayedProgress does not move backwards on delayed lower server progress', () => {
  const high = resolveDisplayedProgress({
    job: { job_id: 'job-3', status: 'processing', progress: 60 },
    nowMs: 2000,
  });
  const delayedLower = resolveDisplayedProgress({
    job: { job_id: 'job-3', status: 'processing', progress: 20 },
    previousState: high.state,
    nowMs: 4000,
  });

  assert.ok(delayedLower.displayProgress >= 60);
  assert.ok(delayedLower.state.lastServerProgress >= 60);
});

test('resolveDisplayedProgress stops interpolation for stale server updates', () => {
  const initial = resolveDisplayedProgress({
    job: { job_id: 'job-4', status: 'processing', progress: 20 },
    nowMs: 0,
  });
  const stale = resolveDisplayedProgress({
    job: { job_id: 'job-4', status: 'processing', progress: 20 },
    previousState: initial.state,
    nowMs: 70000,
  });

  assert.equal(stale.displayProgress, 20);
});

test('resolveDisplayedProgress keeps interpolating when fresh server snapshots keep arriving', () => {
  let current = resolveDisplayedProgress({
    job: { job_id: 'job-4b', status: 'processing', progress: 20 },
    nowMs: 0,
    hasFreshServerSnapshot: true,
  });

  for (let nowMs = 5000; nowMs <= 70000; nowMs += 5000) {
    current = resolveDisplayedProgress({
      job: { job_id: 'job-4b', status: 'processing', progress: 20 },
      previousState: current.state,
      nowMs,
      hasFreshServerSnapshot: true,
    });
  }

  assert.ok(current.displayProgress > 20);
  assert.ok(current.displayProgress <= 99);
});

test('resolveDisplayedProgress terminal status snaps to final progress and zero eta', () => {
  const previous = resolveDisplayedProgress({
    job: { job_id: 'job-5', status: 'processing', progress: 62 },
    nowMs: 1000,
  });
  const terminal = resolveDisplayedProgress({
    job: { job_id: 'job-5', status: 'completed', progress: 100 },
    previousState: previous.state,
    nowMs: 3000,
  });

  assert.equal(terminal.displayProgress, 100);
  assert.equal(terminal.etaSeconds, 0);
});

test('estimateTranscriptionDurationMs uses fallback defaults when media size is missing', () => {
  assert.equal(estimateTranscriptionDurationMs({ status: 'queued' }), 120000);
  assert.equal(estimateTranscriptionDurationMs({ status: 'processing' }), 540000);
});

test('jobActionsForStatus returns status-dependent lifecycle actions', () => {
  assert.deepEqual(jobActionsForStatus('processing'), {
    canPause: true,
    canResume: false,
    canCancel: true,
    canDelete: true,
  });
  assert.deepEqual(jobActionsForStatus('paused'), {
    canPause: false,
    canResume: true,
    canCancel: true,
    canDelete: true,
  });
  assert.deepEqual(jobActionsForStatus('completed'), {
    canPause: false,
    canResume: false,
    canCancel: false,
    canDelete: true,
  });
  assert.deepEqual(jobActionsForStatus('canceled'), {
    canPause: false,
    canResume: false,
    canCancel: false,
    canDelete: true,
  });
  assert.deepEqual(jobActionsForStatus('upload_pending'), {
    canPause: false,
    canResume: false,
    canCancel: false,
    canDelete: true,
  });
  assert.deepEqual(jobActionsForStatus('cancel_requested'), {
    canPause: false,
    canResume: false,
    canCancel: false,
    canDelete: true,
  });
  assert.deepEqual(jobActionsForStatus('deleted'), {
    canPause: false,
    canResume: false,
    canCancel: false,
    canDelete: false,
  });
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
