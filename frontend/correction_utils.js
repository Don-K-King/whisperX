const EPSILON = 1e-6;

export function normalizeSegments(rawSegments = []) {
  const segments = [];
  let previousEnd = 0;
  for (let index = 0; index < rawSegments.length; index += 1) {
    const raw = rawSegments[index] ?? {};
    const segmentId = String(raw.segment_id ?? '').trim() || `seg_${String(index + 1).padStart(6, '0')}`;
    const speaker = String(raw.speaker ?? 'UNKNOWN').trim() || 'UNKNOWN';
    const text = String(raw.text ?? '');
    let start = Number(raw.start);
    let end = Number(raw.end);
    if (!Number.isFinite(start)) start = previousEnd;
    if (!Number.isFinite(end)) end = start;
    segments.push({
      segment_id: segmentId,
      speaker,
      text,
      start,
      end,
    });
    previousEnd = end;
  }
  return segments;
}

export function findActiveSegmentIndex({ segments = [], currentTime = 0 }) {
  if (!Array.isArray(segments) || segments.length === 0) return -1;
  const time = Number(currentTime);
  if (!Number.isFinite(time)) return -1;
  // Binary search for the latest segment whose start is <= current time.
  let low = 0;
  let high = segments.length - 1;
  let candidate = -1;
  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const start = Number(segments[mid]?.start ?? 0);
    if (time >= start - EPSILON) {
      candidate = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  if (candidate >= 0) {
    const segment = segments[candidate];
    const start = Number(segment.start ?? 0);
    const end = Number(segment.end ?? start);
    if (time >= start - EPSILON && time <= end + EPSILON) {
      return candidate;
    }
  }
  const firstStart = Number(segments[0]?.start ?? 0);
  const lastEnd = Number(segments[segments.length - 1]?.end ?? firstStart);
  if (time < firstStart - EPSILON) return -1;
  if (time > lastEnd + EPSILON) return -1;
  // Internal gap between two non-overlapping segments.
  return -1;
}

export function mergeConsecutiveSpeakerBlocks(segments = []) {
  const normalized = normalizeSegments(segments);
  if (normalized.length < 2) return normalized;
  const merged = [];
  for (const segment of normalized) {
    const last = merged[merged.length - 1];
    if (!last) {
      merged.push({ ...segment });
      continue;
    }
    const contiguous = Math.abs(Number(segment.start) - Number(last.end)) <= EPSILON;
    if (contiguous && String(segment.speaker) === String(last.speaker)) {
      last.end = Number(segment.end);
      last.text = last.text ? `${last.text}\n${segment.text}` : segment.text;
      continue;
    }
    merged.push({ ...segment });
  }
  return merged;
}

export function applyReplaceLiteral({ segments = [], query = '', replace = '', speaker = null, replaceAll = true }) {
  const search = String(query ?? '');
  if (!search) {
    return { segments: normalizeSegments(segments), replacements: 0 };
  }
  const updated = normalizeSegments(segments);
  let replacements = 0;
  for (const segment of updated) {
    if (speaker && String(segment.speaker) !== String(speaker)) continue;
    const text = String(segment.text ?? '');
    if (!text.includes(search)) continue;
    if (replaceAll) {
      const count = text.split(search).length - 1;
      segment.text = text.split(search).join(String(replace ?? ''));
      replacements += count;
      continue;
    }
    segment.text = text.replace(search, String(replace ?? ''));
    replacements += 1;
    break;
  }
  return { segments: updated, replacements };
}

function splitSegment(segment, startChar, endChar, newSpeaker) {
  const text = String(segment.text ?? '');
  const left = text.slice(0, startChar);
  const middle = text.slice(startChar, endChar);
  const right = text.slice(endChar);
  const segmentId = String(segment.segment_id ?? 'seg');
  const oldSpeaker = String(segment.speaker ?? 'UNKNOWN');
  const start = Number(segment.start ?? 0);
  const end = Number(segment.end ?? start);
  const duration = Math.max(0, end - start);
  const pieces = [];
  if (left) pieces.push({ suffix: 'a', speaker: oldSpeaker, text: left });
  pieces.push({ suffix: 'b', speaker: String(newSpeaker ?? oldSpeaker), text: middle });
  if (right) pieces.push({ suffix: 'c', speaker: oldSpeaker, text: right });
  const totalChars = Math.max(1, pieces.reduce((sum, piece) => sum + piece.text.length, 0));
  let cursor = start;
  return pieces.map((piece, index) => {
    const partStart = duration <= EPSILON ? start : cursor;
    const partEnd = duration <= EPSILON
      ? start
      : index === pieces.length - 1
        ? end
        : cursor + (duration * (piece.text.length / totalChars));
    cursor = partEnd;
    return {
      segment_id: `${segmentId}_${piece.suffix}`,
      speaker: piece.speaker,
      text: piece.text,
      start: partStart,
      end: partEnd,
    };
  });
}

export function mergeAdjacentSegments(segments = []) {
  const normalized = normalizeSegments(segments);
  if (normalized.length < 2) return normalized;
  const merged = [];
  for (const segment of normalized) {
    const last = merged[merged.length - 1];
    if (!last) {
      merged.push({ ...segment });
      continue;
    }
    const contiguous = Math.abs(Number(segment.start) - Number(last.end)) <= EPSILON;
    if (contiguous && String(segment.speaker) === String(last.speaker)) {
      last.end = Number(segment.end);
      last.text = last.text ? `${last.text}\n${segment.text}` : segment.text;
      continue;
    }
    merged.push({ ...segment });
  }
  return merged;
}

export function applySpeakerReassign({ segments = [], segmentId = '', speaker = '', startChar = null, endChar = null }) {
  const normalized = normalizeSegments(segments);
  const targetIndex = normalized.findIndex((segment) => String(segment.segment_id) === String(segmentId));
  if (targetIndex < 0) return { segments: normalized, changed: false };
  const target = { ...normalized[targetIndex] };
  if (!speaker) return { segments: normalized, changed: false };

  if (startChar == null || endChar == null) {
    target.speaker = String(speaker);
    normalized[targetIndex] = target;
    return { segments: normalized, changed: true };
  }

  const startIndex = Number(startChar);
  const endIndex = Number(endChar);
  const text = String(target.text ?? '');
  if (!Number.isInteger(startIndex) || !Number.isInteger(endIndex) || startIndex < 0 || endIndex <= startIndex || endIndex > text.length) {
    return { segments: normalized, changed: false };
  }

  const split = splitSegment(target, startIndex, endIndex, speaker);
  const replaced = [...normalized.slice(0, targetIndex), ...split, ...normalized.slice(targetIndex + 1)];
  return { segments: replaced, changed: true };
}

export function formatTimestamp(secondsRaw) {
  const seconds = Math.max(0, Number(secondsRaw ?? 0));
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}
