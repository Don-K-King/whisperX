import { buildCompleteUploadPayload } from './utils.js';

export async function createAndQueueJobUpload({
  callApi,
  uploadFileToPresignedUrl,
  tenantId,
  file,
  language = 'de',
  retentionMonths = 12,
  idempotencyKeyFactory = () => globalThis.crypto.randomUUID(),
  onUploadProgress = null,
}) {
  if (!file) {
    throw { error_code: 'job.validation.file_missing' };
  }
  if (!tenantId) {
    throw { error_code: 'auth.tenant_missing' };
  }

  const contentType = file.type || 'application/octet-stream';
  const created = await callApi('/api/v1/jobs', {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKeyFactory() },
    body: JSON.stringify({
      filename: file.name,
      content_type: contentType,
      size_bytes: file.size,
      retention_months: retentionMonths,
      language,
    }),
  });

  const upload = created?.upload ?? {};
  if (!created?.job_id || !upload?.session_id || !upload?.presigned_url) {
    throw { error_code: 'job.create.invalid_response' };
  }

  const checksumSha256 = await uploadFileToPresignedUrl({
    presignedUrl: upload.presigned_url,
    file,
    contentType,
    onProgress: onUploadProgress,
  });

  const completed = await callApi(`/api/v1/jobs/${created.job_id}/complete-upload`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKeyFactory() },
    body: JSON.stringify(buildCompleteUploadPayload({
      tenantId,
      jobId: created.job_id,
      filename: file.name,
      uploadSessionId: upload.session_id,
      checksumSha256,
    })),
  });

  return {
    jobId: created.job_id,
    status: completed?.status ?? 'queued',
    queue: completed?.queue ?? null,
  };
}
