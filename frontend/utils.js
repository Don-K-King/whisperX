function decodeBase64(value){
  if (typeof atob === 'function') {
    return atob(value);
  }
  return Buffer.from(value, 'base64').toString('utf-8');
}

export function parseToken(token){
  const [, payload] = token.split('.');
  if (!payload) return { token, tenant_id: 'unknown', roles: ['user'] };
  try {
    const claims = JSON.parse(decodeBase64(payload));
    return { token, tenant_id: claims.tenant_id ?? 'unknown', roles: claims.roles ?? ['user'] };
  } catch {
    return { token, tenant_id: 'unknown', roles: ['user'] };
  }
}

export function sanitizedError(problem){
  return `${problem.error_code ?? 'unknown_error'}${problem.correlation_id ? ` (${problem.correlation_id})` : ''}`;
}

export function buildCompleteUploadPayload({ tenantId, jobId, filename, uploadSessionId, checksumSha256 }) {
  return {
    upload_session_id: uploadSessionId,
    object_key: `tenant/${tenantId}/${jobId}/${filename}`,
    checksum_sha256: checksumSha256,
  };
}

export function mapTranscriptToSpeakerRows(payload) {
  const segments = Array.isArray(payload?.segments) ? payload.segments : [];
  return segments.map((segment) => ({
    speaker: String(segment?.speaker ?? 'UNKNOWN'),
    timeRange: `${formatSeconds(segment?.start) ?? '00:00:00'} - ${formatSeconds(segment?.end) ?? '00:00:00'}`,
    text: String(segment?.text ?? ''),
  }));
}

function formatSeconds(rawValue) {
  const seconds = Number(rawValue ?? 0);
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00:00';
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}
