import test from 'node:test';
import assert from 'node:assert/strict';

import { createAndQueueJobUpload } from '../upload_flow.js';

test('createAndQueueJobUpload orchestrates create/upload/complete in order', async () => {
  const apiCalls = [];
  let idCounter = 0;
  const callApi = async (path, options = {}) => {
    apiCalls.push([path, options]);
    if (path === '/api/v1/jobs') {
      return {
        job_id: 'job_1',
        upload: {
          session_id: 'up_1',
          presigned_url: 'https://object.local/upload',
        },
      };
    }
    if (path === '/api/v1/jobs/job_1/complete-upload') {
      return { status: 'queued', queue: 'gpu-standard' };
    }
    throw new Error(`unexpected call: ${path}`);
  };

  const uploadCalls = [];
  const progressUpdates = [];
  const uploadFileToPresignedUrl = async (input) => {
    uploadCalls.push(input);
    if (typeof input.onProgress === 'function') {
      input.onProgress(35);
      input.onProgress(100);
    }
    return 'a'.repeat(64);
  };

  const result = await createAndQueueJobUpload({
    callApi,
    uploadFileToPresignedUrl,
    tenantId: 'tenant-a',
    file: { name: 'meeting.mp4', type: 'video/mp4', size: 2048 },
    language: 'de',
    retentionMonths: 12,
    idempotencyKeyFactory: () => `idem-${++idCounter}`,
    onUploadProgress: (value) => progressUpdates.push(value),
  });

  assert.equal(result.jobId, 'job_1');
  assert.equal(result.status, 'queued');
  assert.equal(uploadCalls.length, 1);
  assert.equal(uploadCalls[0].presignedUrl, 'https://object.local/upload');
  assert.deepEqual(progressUpdates, [35, 100]);

  assert.equal(apiCalls.length, 2);
  assert.equal(apiCalls[0][0], '/api/v1/jobs');
  assert.equal(apiCalls[0][1].headers['Idempotency-Key'], 'idem-1');
  assert.deepEqual(JSON.parse(apiCalls[0][1].body), {
    filename: 'meeting.mp4',
    content_type: 'video/mp4',
    size_bytes: 2048,
    retention_months: 12,
    language: 'de',
  });
  assert.equal(apiCalls[1][0], '/api/v1/jobs/job_1/complete-upload');
  assert.equal(apiCalls[1][1].headers['Idempotency-Key'], 'idem-2');
  assert.deepEqual(JSON.parse(apiCalls[1][1].body), {
    upload_session_id: 'up_1',
    object_key: 'tenant/tenant-a/job_1/meeting.mp4',
    checksum_sha256: 'a'.repeat(64),
  });
});

test('createAndQueueJobUpload validates missing file', async () => {
  await assert.rejects(
    () => createAndQueueJobUpload({
      callApi: async () => ({}),
      uploadFileToPresignedUrl: async () => 'a'.repeat(64),
      tenantId: 'tenant-a',
      file: null,
      idempotencyKeyFactory: () => 'idem-1',
    }),
    (error) => error?.error_code === 'job.validation.file_missing',
  );
});

test('createAndQueueJobUpload does not upload when create-job fails', async () => {
  let uploadCalled = false;
  await assert.rejects(
    () => createAndQueueJobUpload({
      callApi: async () => { throw { error_code: 'job.validation.content_type' }; },
      uploadFileToPresignedUrl: async () => { uploadCalled = true; return 'a'.repeat(64); },
      tenantId: 'tenant-a',
      file: { name: 'x.bin', type: 'application/octet-stream', size: 10 },
      idempotencyKeyFactory: () => 'idem-1',
    }),
    (error) => error?.error_code === 'job.validation.content_type',
  );
  assert.equal(uploadCalled, false);
});

test('createAndQueueJobUpload forwards selected language', async () => {
  const apiCalls = [];
  const callApi = async (path, options = {}) => {
    apiCalls.push([path, options]);
    if (path === '/api/v1/jobs') {
      return {
        job_id: 'job_2',
        upload: {
          session_id: 'up_2',
          presigned_url: 'https://object.local/upload-2',
        },
      };
    }
    if (path === '/api/v1/jobs/job_2/complete-upload') {
      return { status: 'queued', queue: 'gpu-standard' };
    }
    throw new Error(`unexpected call: ${path}`);
  };

  await createAndQueueJobUpload({
    callApi,
    uploadFileToPresignedUrl: async () => 'b'.repeat(64),
    tenantId: 'tenant-a',
    file: { name: 'meeting.mp4', type: 'video/mp4', size: 2048 },
    language: 'fr',
    idempotencyKeyFactory: () => 'idem-lang',
  });

  assert.equal(JSON.parse(apiCalls[0][1].body).language, 'fr');
});
