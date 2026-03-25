export const SIDEBAR_SECTION_IDS = Object.freeze([
  'status',
  'searchReplace',
  'speakerReassign',
  'changeLog',
]);

export function buildSpeakerDisplayLabel({ speakerKey, speakerLabels = {} }) {
  const key = String(speakerKey ?? 'UNKNOWN').trim() || 'UNKNOWN';
  const alias = String(speakerLabels?.[key] ?? '').trim();
  if (!alias || alias === key) return key;
  return `${alias} (${key})`;
}

export function buildSpeakerOptionEntries({ segments = [], speakerLabels = {} }) {
  const keys = new Set();
  for (const segment of segments) {
    const key = String(segment?.speaker ?? 'UNKNOWN').trim() || 'UNKNOWN';
    keys.add(key);
  }
  Object.keys(speakerLabels || {}).forEach((key) => {
    const normalized = String(key ?? '').trim();
    if (normalized) keys.add(normalized);
  });
  return [...keys].map((key) => ({
    key,
    label: buildSpeakerDisplayLabel({ speakerKey: key, speakerLabels }),
  }));
}

export function parseSidebarVisibility(value) {
  if (value === '0') return false;
  return true;
}

export function parseAutoSeekSelectionEnabled(value) {
  if (value === '0') return false;
  return true;
}

export function parseSidebarSectionState(value, sectionIds = SIDEBAR_SECTION_IDS) {
  const defaults = Object.fromEntries(sectionIds.map((id) => [id, true]));
  if (typeof value !== 'string' || value.trim() === '') {
    return defaults;
  }
  try {
    const parsed = JSON.parse(value);
    if (Array.isArray(parsed)) {
      const openSet = new Set(parsed.map((entry) => String(entry)));
      return Object.fromEntries(sectionIds.map((id) => [id, openSet.has(id)]));
    }
    if (parsed && typeof parsed === 'object') {
      return Object.fromEntries(sectionIds.map((id) => [id, parsed[id] !== false]));
    }
    return defaults;
  } catch {
    return defaults;
  }
}

export function serializeSidebarSectionState(state, sectionIds = SIDEBAR_SECTION_IDS) {
  const openSections = sectionIds.filter((id) => state?.[id] !== false);
  return JSON.stringify(openSections);
}

export function deriveMarkedTextRange({ segmentId = '', selectionStart = null, selectionEnd = null, textLength = 0 }) {
  const normalizedSegmentId = String(segmentId ?? '').trim();
  const startChar = Number(selectionStart);
  const endChar = Number(selectionEnd);
  const length = Number(textLength);
  if (!normalizedSegmentId) return null;
  if (!Number.isInteger(startChar) || !Number.isInteger(endChar) || !Number.isFinite(length)) return null;
  if (startChar < 0 || endChar <= startChar || endChar > Math.max(0, length)) return null;
  return {
    segmentId: normalizedSegmentId,
    startChar,
    endChar,
    length: endChar - startChar,
  };
}

export function resolveMarkedTextRange({ previousRange = null, latestRange = null }) {
  if (latestRange && Number(latestRange.length) > 0) {
    return latestRange;
  }
  if (previousRange && Number(previousRange.length) > 0) {
    return previousRange;
  }
  return null;
}

export function resolveMediaSeekTime(startRaw) {
  const start = Number(startRaw);
  if (!Number.isFinite(start)) return null;
  return Math.max(0, start);
}

export function shouldAutoSeek({ previousSegmentId = '', nextSegmentId = '', source = '' }) {
  const previous = String(previousSegmentId ?? '').trim();
  const next = String(nextSegmentId ?? '').trim();
  const trigger = String(source ?? '').trim();
  if (!previous || !next || previous === next) return false;
  return trigger === 'block_click' || trigger === 'text_focus';
}

export function resolveSelectedSegmentId({ previousSegmentId = '', segments = [] }) {
  if (!Array.isArray(segments) || segments.length === 0) return null;
  const previous = String(previousSegmentId ?? '').trim();
  const segmentIds = segments.map((segment) => String(segment?.segment_id ?? '').trim()).filter(Boolean);
  if (!previous) return segmentIds[0] || null;
  if (segmentIds.includes(previous)) return previous;
  const splitPrefix = `${previous}_`;
  const splitCandidate = segmentIds.find((segmentId) => segmentId.startsWith(splitPrefix));
  if (splitCandidate) return splitCandidate;
  return segmentIds[0] || null;
}
