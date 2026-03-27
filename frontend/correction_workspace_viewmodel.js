export const SIDEBAR_SECTION_IDS = Object.freeze([
  'status',
  'searchReplace',
  'speakerReassign',
  'changeLog',
]);

const CORRECTION_BOOTSTRAP_PHASES = Object.freeze([
  Object.freeze({ id: 'boot', label: 'Arbeitsbereich vorbereiten', detail: 'Korrekturmodus wird vorbereitet...' }),
  Object.freeze({ id: 'media', label: 'Media laden', detail: 'Media wird geladen...' }),
  Object.freeze({ id: 'transcript', label: 'Transcript laden', detail: 'Transcript wird geladen...' }),
  Object.freeze({ id: 'session', label: 'Session starten', detail: 'Korrektursitzung wird gestartet...' }),
]);

const SPEAKER_TINT_NEUTRAL = Object.freeze({ r: 120, g: 128, b: 142 });
const SPEAKER_TINT_PALETTE = Object.freeze([
  Object.freeze({ r: 70, g: 125, b: 193 }),
  Object.freeze({ r: 54, g: 146, b: 101 }),
  Object.freeze({ r: 198, g: 135, b: 66 }),
  Object.freeze({ r: 127, g: 99, b: 186 }),
  Object.freeze({ r: 193, g: 98, b: 128 }),
  Object.freeze({ r: 57, g: 141, b: 150 }),
  Object.freeze({ r: 168, g: 116, b: 58 }),
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

function hashSpeakerKey(value) {
  let hash = 0;
  for (const char of String(value || '')) {
    hash = ((hash * 31) + char.charCodeAt(0)) >>> 0;
  }
  return hash >>> 0;
}

function toTint(r, g, b) {
  return {
    background: `rgba(${r}, ${g}, ${b}, 0.14)`,
    border: `rgba(${r}, ${g}, ${b}, 0.46)`,
    active: `rgba(${r}, ${g}, ${b}, 0.28)`,
    focus: `rgba(${r}, ${g}, ${b}, 0.48)`,
  };
}

export function resolveSpeakerTint({ speakerKey = 'UNKNOWN' } = {}) {
  const normalized = String(speakerKey ?? 'UNKNOWN').trim().toUpperCase() || 'UNKNOWN';
  if (normalized === 'UNKNOWN') {
    return toTint(
      SPEAKER_TINT_NEUTRAL.r,
      SPEAKER_TINT_NEUTRAL.g,
      SPEAKER_TINT_NEUTRAL.b,
    );
  }
  const hash = hashSpeakerKey(normalized);
  const selected = SPEAKER_TINT_PALETTE[hash % SPEAKER_TINT_PALETTE.length] || SPEAKER_TINT_NEUTRAL;
  return toTint(selected.r, selected.g, selected.b);
}

export function resolveExportMenuState(
  state = { isOpen: false, lastAction: '' },
  event = { type: '' },
) {
  const previousOpen = Boolean(state?.isOpen);
  const previousAction = String(state?.lastAction ?? '').trim();
  const type = String(event?.type ?? '').trim().toLowerCase();
  const action = String(event?.action ?? '').trim().toLowerCase();

  if (type === 'toggle') {
    return { isOpen: !previousOpen, lastAction: previousAction };
  }
  if (type === 'open') {
    return { isOpen: true, lastAction: previousAction };
  }
  if (type === 'close' || type === 'outside' || type === 'escape') {
    return { isOpen: false, lastAction: previousAction };
  }
  if (type === 'select') {
    return { isOpen: false, lastAction: action || previousAction };
  }
  return { isOpen: previousOpen, lastAction: previousAction };
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
  const defaults = Object.fromEntries(sectionIds.map((id) => [id, false]));
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
      return Object.fromEntries(sectionIds.map((id) => [id, parsed[id] === true]));
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

export function resolveCorrectionBootstrapFeedback({ phase = 'boot' } = {}) {
  const normalizedPhase = String(phase ?? '').trim().toLowerCase();
  const phaseIndex = CORRECTION_BOOTSTRAP_PHASES.findIndex((entry) => entry.id === normalizedPhase);
  const activeIndex = phaseIndex >= 0 ? phaseIndex : 0;
  const activePhase = CORRECTION_BOOTSTRAP_PHASES[activeIndex];

  return {
    title: 'Transcript mit Media wird geladen',
    detail: activePhase.detail,
    steps: CORRECTION_BOOTSTRAP_PHASES.map((entry, index) => ({
      id: entry.id,
      label: entry.label,
      status: index < activeIndex ? 'done' : (index === activeIndex ? 'active' : 'pending'),
    })),
  };
}
