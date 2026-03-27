function decodeBase64(value){
  if (typeof atob === 'function') {
    return atob(value);
  }
  return Buffer.from(value, 'base64').toString('utf-8');
}

const MILESTONE_PROGRESS = {
  queued: 5,
  processing: 20,
  pause_requested: 20,
  cancel_requested: 20,
  paused: 20,
  failed_retryable: 20,
  failed_terminal: 20,
  completed: 100,
  canceled: 100,
  deleted: 100,
};

const POLLING_BASE_MS = 5000;
const POLLING_MAX_MS = 30000;
const TERMINAL_PROGRESS_STATUSES = new Set(['completed', 'failed_terminal', 'canceled', 'deleted']);
const INTERPOLATION_ELIGIBLE_STATUSES = new Set(['queued', 'processing']);
const PROGRESS_STALE_AFTER_MS = 60000;

const DEFAULT_ESTIMATED_DURATION_MS = Object.freeze({
  queued: 120000,
  processing: 540000,
});

export function parseToken(token){
  if (token?.startsWith('dev:')) {
    const parts = token.split(':');
    if (parts.length >= 4) {
      const roles = parts[2] ? parts[2].split(',').filter(Boolean) : ['user'];
      return {
        token,
        tenant_id: parts[1] || 'tenant-a',
        roles: roles.length > 0 ? roles : ['user'],
      };
    }
    return { token, tenant_id: 'tenant-a', roles: ['user'] };
  }
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

export function deriveProgress(job){
  const status = String(job?.status ?? '');
  const raw = job?.progress;
  if (Number.isInteger(raw)) {
    return Math.max(0, Math.min(100, raw));
  }
  return MILESTONE_PROGRESS[status] ?? 0;
}

function clampInt(value, min, max) {
  return Math.max(min, Math.min(max, Math.round(Number(value) || 0)));
}

function resolveNextProgressMilestone(progressValue) {
  const milestones = [5, 20, 60, 90, 100];
  const current = clampInt(progressValue, 0, 100);
  for (const milestone of milestones) {
    if (milestone > current) {
      return milestone;
    }
  }
  return 100;
}

function resolveInterpolationCap({ status, monotonicServerProgress, nextMilestone }) {
  if (status === 'processing') {
    return 99;
  }
  const boundedMilestone = nextMilestone >= 100 ? 99 : nextMilestone;
  return Math.max(monotonicServerProgress, boundedMilestone - 1);
}

export function estimateTranscriptionDurationMs({ sizeBytes = null, status = 'processing' } = {}) {
  const normalizedStatus = String(status ?? '').trim().toLowerCase();
  const fallback = DEFAULT_ESTIMATED_DURATION_MS[normalizedStatus] ?? DEFAULT_ESTIMATED_DURATION_MS.processing;
  const size = Number(sizeBytes);
  if (!Number.isFinite(size) || size <= 0) return fallback;
  const megaBytes = size / (1024 * 1024);
  const estimated = 90000 + (megaBytes * 1200);
  return Math.max(120000, Math.min(2700000, Math.round(estimated)));
}

export function resolveDisplayedProgress({
  job = {},
  previousState = null,
  nowMs = Date.now(),
  pollIntervalMs = POLLING_BASE_MS,
  hasFreshServerSnapshot = false,
} = {}) {
  const status = String(job?.status ?? '').trim();
  const serverProgress = deriveProgress(job);
  const previous = previousState && typeof previousState === 'object' ? previousState : null;
  const previousServerProgress = clampInt(previous?.lastServerProgress ?? serverProgress, 0, 100);
  const monotonicServerProgress = Math.max(serverProgress, previousServerProgress);
  const estimatedDurationMs = estimateTranscriptionDurationMs({
    sizeBytes: job?.size_bytes,
    status,
  });
  const isTerminal = TERMINAL_PROGRESS_STATUSES.has(status);
  const previousDisplay = clampInt(previous?.displayProgress ?? monotonicServerProgress, 0, 100);

  if (isTerminal) {
    const finalDisplay = clampInt(monotonicServerProgress, 0, 100);
    return {
      displayProgress: finalDisplay,
      etaSeconds: 0,
      state: {
        status,
        displayProgress: finalDisplay,
        lastServerProgress: finalDisplay,
        lastServerTimestamp: nowMs,
        estimatedDurationMs,
        phaseStartMs: nowMs,
      },
    };
  }

  if (!INTERPOLATION_ELIGIBLE_STATUSES.has(status)) {
    const displayProgress = Math.max(previousDisplay, monotonicServerProgress);
    return {
      displayProgress,
      etaSeconds: null,
      state: {
        status,
        displayProgress,
        lastServerProgress: monotonicServerProgress,
        lastServerTimestamp: nowMs,
        estimatedDurationMs,
        phaseStartMs: nowMs,
      },
    };
  }

  const nextMilestone = resolveNextProgressMilestone(monotonicServerProgress);
  const interpolationCap = resolveInterpolationCap({
    status,
    monotonicServerProgress,
    nextMilestone,
  });
  const phaseSpan = Math.max(1, interpolationCap - monotonicServerProgress);
  const progressToComplete = Math.max(1, 100 - monotonicServerProgress);

  const hasNewServerSignal = !previous
    || String(previous.status ?? '') !== status
    || monotonicServerProgress > previousServerProgress
    || nowMs < Number(previous?.lastServerTimestamp ?? nowMs);
  const staleThresholdMs = Math.max(20000, Number(pollIntervalMs || POLLING_BASE_MS) * 4);
  const staleMs = Math.min(PROGRESS_STALE_AFTER_MS, staleThresholdMs);

  let phaseStartMs = Number(previous?.phaseStartMs ?? nowMs);
  let lastServerTimestamp = Number(previous?.lastServerTimestamp ?? nowMs);
  let displayProgress = Math.max(previousDisplay, monotonicServerProgress);

  if (hasNewServerSignal) {
    phaseStartMs = nowMs;
    lastServerTimestamp = nowMs;
    displayProgress = Math.max(monotonicServerProgress, previousDisplay);
  } else {
    if (hasFreshServerSnapshot) {
      // Poll response arrived, so the server snapshot is still fresh.
      // Keep phaseStart for smooth interpolation, but refresh heartbeat timestamp.
      lastServerTimestamp = nowMs;
    }
    const elapsedSinceServerMs = Math.max(0, nowMs - lastServerTimestamp);
    if (elapsedSinceServerMs <= staleMs) {
      const phaseDurationMs = clampInt(
        estimatedDurationMs * (phaseSpan / progressToComplete),
        4000,
        3600000,
      );
      const elapsedPhaseMs = Math.max(0, nowMs - phaseStartMs);
      const interpolatedStep = Math.floor((elapsedPhaseMs / phaseDurationMs) * phaseSpan);
      const candidate = monotonicServerProgress + interpolatedStep;
      const phaseCap = Math.max(monotonicServerProgress, interpolationCap);
      displayProgress = clampInt(Math.max(displayProgress, candidate), monotonicServerProgress, phaseCap);
    }
  }

  const remainingRatio = Math.max(0, (100 - displayProgress) / Math.max(1, 100 - monotonicServerProgress));
  const etaSeconds = displayProgress >= 100 ? 0 : clampInt((estimatedDurationMs * remainingRatio) / 1000, 0, 7200);

  return {
    displayProgress,
    etaSeconds,
    state: {
      status,
      displayProgress,
      lastServerProgress: monotonicServerProgress,
      lastServerTimestamp,
      estimatedDurationMs,
      phaseStartMs,
    },
  };
}

export function jobActionsForStatus(statusRaw){
  const status = String(statusRaw ?? '');
  return {
    canPause: status === 'queued' || status === 'processing',
    canResume: status === 'paused' || status === 'failed_retryable',
    canCancel: status === 'queued' || status === 'processing' || status === 'pause_requested' || status === 'paused',
    canDelete: status !== 'deleted',
  };
}

export function nextPollingIntervalMs({ currentMs = POLLING_BASE_MS, statusCode = 200 } = {}){
  if (statusCode === 429) {
    return Math.min(POLLING_MAX_MS, Math.max(POLLING_BASE_MS, currentMs) * 2);
  }
  return POLLING_BASE_MS;
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
  const speakerLabels = normalizeSpeakerLabels(payload?.speaker_labels);
  return segments.map((segment) => ({
    speaker: resolveSpeakerLabel({
      speakerKey: String(segment?.speaker ?? 'UNKNOWN'),
      speakerLabels,
    }),
    speakerKey: String(segment?.speaker ?? 'UNKNOWN'),
    timeRange: `${formatSeconds(segment?.start) ?? '00:00:00'} - ${formatSeconds(segment?.end) ?? '00:00:00'}`,
    text: String(segment?.text ?? ''),
  }));
}

export function mapTranscriptToSpeakerBlocks(payload) {
  const segments = Array.isArray(payload?.segments) ? payload.segments : [];
  const speakerLabels = normalizeSpeakerLabels(payload?.speaker_labels);
  const blocks = [];

  for (const segment of segments) {
    const speakerKey = String(segment?.speaker ?? 'UNKNOWN');
    const text = String(segment?.text ?? '');
    const start = Number(segment?.start ?? 0);
    const end = Number(segment?.end ?? 0);
    const lastBlock = blocks[blocks.length - 1];
    if (lastBlock && lastBlock.speakerKey === speakerKey) {
      lastBlock.end = end;
      lastBlock.lines.push(text);
      continue;
    }
    blocks.push({
      speakerKey,
      speaker: resolveSpeakerLabel({ speakerKey, speakerLabels }),
      start,
      end,
      lines: [text],
    });
  }

  return blocks.map((block) => ({
    speakerKey: block.speakerKey,
    speaker: block.speaker,
    timeRange: `${formatSeconds(block.start)} - ${formatSeconds(block.end)}`,
    text: block.lines.join('\n'),
  }));
}

export function mapTranscriptToSpeakerAliases(payload) {
  const segments = Array.isArray(payload?.segments) ? payload.segments : [];
  const speakerLabels = normalizeSpeakerLabels(payload?.speaker_labels);
  const uniqueSpeakerKeys = [];
  const seen = new Set();

  for (const segment of segments) {
    const speakerKey = String(segment?.speaker ?? 'UNKNOWN');
    if (seen.has(speakerKey)) continue;
    seen.add(speakerKey);
    uniqueSpeakerKeys.push(speakerKey);
  }

  for (const speakerKey of Object.keys(speakerLabels)) {
    if (seen.has(speakerKey)) continue;
    seen.add(speakerKey);
    uniqueSpeakerKeys.push(speakerKey);
  }

  return uniqueSpeakerKeys.map((speakerKey) => ({
    speakerKey,
    alias: speakerLabels[speakerKey] ?? '',
  }));
}

export async function sha256HexFromArrayBuffer(buffer) {
  if (!globalThis.crypto?.subtle) {
    throw { error_code: 'upload.crypto_unavailable' };
  }
  const digest = await globalThis.crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

export async function uploadFileToPresignedUrl({ presignedUrl, file, contentType, onProgress }) {
  if (!presignedUrl) {
    throw { error_code: 'upload.missing_url' };
  }
  if (!file || typeof file.arrayBuffer !== 'function') {
    throw { error_code: 'upload.file_missing' };
  }

  const checksum = await sha256HexFromArrayBuffer(await file.arrayBuffer());
  const progressCallback = typeof onProgress === 'function' ? onProgress : null;

  if (typeof XMLHttpRequest === 'function') {
    await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('PUT', presignedUrl, true);
      xhr.setRequestHeader('Content-Type', contentType || file.type || 'application/octet-stream');
      if (xhr.upload && progressCallback) {
        xhr.upload.onprogress = (event) => {
          if (!event.lengthComputable || event.total <= 0) return;
          const percent = Math.max(0, Math.min(100, Math.round((event.loaded / event.total) * 100)));
          progressCallback(percent);
        };
      }
      xhr.onerror = () => reject({ error_code: 'upload.failed', status_code: xhr.status || 0 });
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          if (progressCallback) progressCallback(100);
          resolve(null);
        } else {
          reject({ error_code: 'upload.failed', status_code: xhr.status });
        }
      };
      xhr.send(file);
    });
    return checksum;
  }

  const response = await fetch(presignedUrl, {
    method: 'PUT',
    headers: {
      'Content-Type': contentType || file.type || 'application/octet-stream',
    },
    body: file,
  });
  if (!response.ok) {
    throw { error_code: 'upload.failed', status_code: response.status };
  }
  if (progressCallback) progressCallback(100);
  return checksum;
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

function normalizeSpeakerLabels(rawValue) {
  if (!rawValue || typeof rawValue !== 'object') {
    return {};
  }
  const normalized = {};
  for (const [rawKey, rawLabel] of Object.entries(rawValue)) {
    const speakerKey = String(rawKey ?? '').trim();
    const speakerLabel = String(rawLabel ?? '').trim();
    if (!speakerKey || !speakerLabel) continue;
    normalized[speakerKey] = speakerLabel;
  }
  return normalized;
}

function resolveSpeakerLabel({ speakerKey, speakerLabels }) {
  const label = speakerLabels[speakerKey];
  return label ? label : speakerKey;
}
