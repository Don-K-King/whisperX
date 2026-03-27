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

export function resolveGapSeekTargetIndex({
  segments = [],
  currentTime = 0,
  activeIndex = -1,
} = {}) {
  if (Number.isInteger(activeIndex) && activeIndex >= 0) return activeIndex;
  if (!Array.isArray(segments) || segments.length === 0) return -1;
  const time = Number(currentTime);
  if (!Number.isFinite(time)) return 0;
  let lo = 0;
  let hi = segments.length - 1;
  let candidate = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const start = Number(segments[mid]?.start);
    if (!Number.isFinite(start)) {
      lo = mid + 1;
      continue;
    }
    if (start >= time) {
      candidate = mid;
      hi = mid - 1;
    } else {
      lo = mid + 1;
    }
  }
  if (candidate >= 0) return candidate;
  return Math.max(0, segments.length - 1);
}

export function resolveVirtualWindowPreferredIndex({
  selectedIndex = -1,
  activeIndex = -1,
  playbackAnchorIndex = -1,
  preferPlaybackAnchor = false,
} = {}) {
  const selected = Number.isInteger(selectedIndex) ? selectedIndex : -1;
  const active = Number.isInteger(activeIndex) ? activeIndex : -1;
  const playbackAnchor = Number.isInteger(playbackAnchorIndex) ? playbackAnchorIndex : -1;
  if (preferPlaybackAnchor && playbackAnchor >= 0) return playbackAnchor;
  if (selected >= 0) return selected;
  if (active >= 0) return active;
  return -1;
}

export function resolveVirtualWindowPinnedIndex({
  preferredIndex = -1,
  preferPlaybackAnchor = false,
} = {}) {
  const preferred = Number.isInteger(preferredIndex) ? preferredIndex : -1;
  if (preferred < 0) return -1;
  if (!preferPlaybackAnchor) return -1;
  return preferred;
}

export function resolveAdaptiveWindowSize({
  totalSegments = 0,
} = {}) {
  const total = Number.isInteger(totalSegments) ? totalSegments : 0;
  if (total <= 0) return 0;
  if (total <= 300) return total;
  if (total <= 600) return Math.min(total, 450);
  if (total <= 1200) return 300;
  if (total <= 3000) return 240;
  return 180;
}

export function resolveAdaptiveVirtualRange({
  totalSegments = 0,
  start = 0,
  end = 0,
  targetWindowSize = 0,
  anchorIndex = -1,
} = {}) {
  const total = Number.isInteger(totalSegments) ? totalSegments : 0;
  if (total <= 0) return { start: 0, end: 0 };
  const target = Math.max(1, Math.min(total, Math.floor(Number(targetWindowSize) || 0)));

  let resolvedStart = Math.floor(Number(start));
  let resolvedEnd = Math.ceil(Number(end));
  if (!Number.isFinite(resolvedStart)) resolvedStart = 0;
  if (!Number.isFinite(resolvedEnd)) resolvedEnd = resolvedStart + 1;

  resolvedStart = Math.min(Math.max(0, resolvedStart), total - 1);
  resolvedEnd = Math.min(total, Math.max(resolvedStart + 1, resolvedEnd));

  if (resolvedEnd - resolvedStart >= target) {
    return { start: resolvedStart, end: resolvedEnd };
  }

  const anchor = Number.isInteger(anchorIndex)
    ? Math.min(Math.max(0, anchorIndex), total - 1)
    : -1;
  const pivot = anchor >= 0
    ? anchor
    : Math.min(total - 1, Math.max(0, Math.floor((resolvedStart + resolvedEnd - 1) / 2)));
  const halfBefore = Math.floor((target - 1) / 2);
  let expandedStart = pivot - halfBefore;
  let expandedEnd = expandedStart + target;

  if (expandedStart < 0) {
    expandedStart = 0;
    expandedEnd = target;
  }
  if (expandedEnd > total) {
    expandedEnd = total;
    expandedStart = Math.max(0, total - target);
  }

  return {
    start: expandedStart,
    end: expandedEnd,
  };
}

export function resolvePlaybackFollowDecision({
  activeIndex = -1,
  rangeStart = 0,
  rangeEnd = 0,
  followPending = false,
  nowMs = 0,
  lastFollowMs = 0,
  throttleMs = 200,
  editorClientHeight = 760,
  rowHeight = 156,
} = {}) {
  const active = Number.isInteger(activeIndex) ? activeIndex : -1;
  const start = Number.isInteger(rangeStart) ? rangeStart : 0;
  const end = Number.isInteger(rangeEnd) ? rangeEnd : 0;
  const last = Number.isFinite(Number(lastFollowMs)) ? Number(lastFollowMs) : 0;
  const now = Number(nowMs);
  const throttle = Number.isFinite(Number(throttleMs)) && Number(throttleMs) > 0
    ? Number(throttleMs)
    : 200;
  const viewport = Math.max(280, Number(editorClientHeight) || 760);
  const safeRowHeight = Math.max(1, Number(rowHeight) || 156);
  const centeredScrollTop = Math.max(0, (active * safeRowHeight) - (viewport / 2) + (safeRowHeight / 2));

  if (active < 0) {
    return {
      shouldShift: false,
      reason: 'no_active',
      nextFollowMs: last,
      targetScrollTop: centeredScrollTop,
    };
  }
  if (followPending) {
    return {
      shouldShift: false,
      reason: 'pending',
      nextFollowMs: last,
      targetScrollTop: centeredScrollTop,
    };
  }
  if (active >= start && active < end) {
    return {
      shouldShift: false,
      reason: 'in_range',
      nextFollowMs: last,
      targetScrollTop: centeredScrollTop,
    };
  }
  if (Number.isFinite(now) && now - last < throttle) {
    return {
      shouldShift: false,
      reason: 'throttled',
      nextFollowMs: last,
      targetScrollTop: centeredScrollTop,
    };
  }
  return {
    shouldShift: true,
    reason: 'out_of_range',
    nextFollowMs: Number.isFinite(now) ? now : last,
    targetScrollTop: centeredScrollTop,
  };
}

export function resolveSeekWarmupRange({
  activeIndex = -1,
  totalSegments = 0,
  lookahead = 10,
  overscan = 8,
} = {}) {
  const active = Number.isInteger(activeIndex) ? activeIndex : -1;
  const total = Number.isInteger(totalSegments) ? totalSegments : 0;
  if (active < 0 || total <= 0 || active >= total) return null;
  const lookaheadCount = Math.max(0, Number.isFinite(Number(lookahead)) ? Number(lookahead) : 10);
  const overscanCount = Math.max(0, Number.isFinite(Number(overscan)) ? Number(overscan) : 8);
  const requiredStartInclusive = Math.max(0, active - lookaheadCount);
  const requiredEndExclusive = Math.min(total, active + lookaheadCount + 1);
  const start = Math.max(0, requiredStartInclusive - overscanCount);
  const end = Math.min(total, requiredEndExclusive + overscanCount);
  return { start, end };
}

export function resolveSeekWarmupReadiness({
  rangeStart = 0,
  rangeEnd = 0,
  activeIndex = -1,
  totalSegments = 0,
  lookahead = 10,
} = {}) {
  const start = Number.isInteger(rangeStart) ? rangeStart : 0;
  const end = Number.isInteger(rangeEnd) ? rangeEnd : 0;
  const active = Number.isInteger(activeIndex) ? activeIndex : -1;
  const total = Number.isInteger(totalSegments) ? totalSegments : 0;
  const lookaheadCount = Math.max(0, Number.isFinite(Number(lookahead)) ? Number(lookahead) : 10);
  if (active < 0 || total <= 0) {
    return { isReady: false, requiredStartInclusive: 0, requiredEndExclusive: 0 };
  }
  const requiredStartInclusive = Math.max(0, active - lookaheadCount);
  const requiredEndExclusive = Math.min(total, active + lookaheadCount + 1);
  const activeVisible = active >= start && active < end;
  const lookbehindCovered = start <= requiredStartInclusive;
  const lookaheadCovered = end >= requiredEndExclusive;
  return {
    isReady: activeVisible && lookbehindCovered && lookaheadCovered,
    requiredStartInclusive,
    requiredEndExclusive,
  };
}

export function resolveSeekPlaybackResumeDecision({
  wasPlaying = false,
  isWarmupReady = false,
  nowMs = 0,
  resumeDeadlineMs = 0,
} = {}) {
  if (isWarmupReady) {
    return {
      shouldResume: Boolean(wasPlaying),
      shouldFinalize: true,
      reason: wasPlaying ? 'ready' : 'ready_not_playing',
    };
  }
  const now = Number(nowMs);
  const deadline = Number(resumeDeadlineMs);
  if (Number.isFinite(now) && Number.isFinite(deadline) && now >= deadline) {
    return {
      shouldResume: Boolean(wasPlaying),
      shouldFinalize: true,
      reason: wasPlaying ? 'timeout' : 'timeout_not_playing',
    };
  }
  if (!wasPlaying) {
    return { shouldResume: false, shouldFinalize: false, reason: 'pending_not_playing' };
  }
  return { shouldResume: false, shouldFinalize: false, reason: 'pending' };
}

export function resolveForcedVirtualRange({
  totalSegments = 0,
  start = 0,
  end = 0,
  fallbackIndex = -1,
  overscan = 8,
} = {}) {
  const total = Number.isInteger(totalSegments) ? totalSegments : 0;
  if (total <= 0) return { start: 0, end: 0 };
  const safeOverscan = Math.max(0, Number.isFinite(Number(overscan)) ? Number(overscan) : 8);
  const fallback = Number.isInteger(fallbackIndex)
    ? Math.min(Math.max(0, fallbackIndex), total - 1)
    : -1;

  let resolvedStart = Math.floor(Number(start));
  let resolvedEnd = Math.ceil(Number(end));
  if (!Number.isFinite(resolvedStart)) resolvedStart = fallback >= 0 ? fallback : 0;
  if (!Number.isFinite(resolvedEnd)) resolvedEnd = resolvedStart + 1;

  resolvedStart = Math.min(Math.max(0, resolvedStart), total - 1);
  resolvedEnd = Math.min(total, Math.max(resolvedStart + 1, resolvedEnd));

  const fallbackOutside = fallback >= 0
    && (fallback < resolvedStart || fallback >= resolvedEnd);
  if (fallbackOutside) {
    resolvedStart = Math.max(0, fallback - safeOverscan);
    resolvedEnd = Math.min(total, fallback + safeOverscan + 1);
  }
  return {
    start: resolvedStart,
    end: resolvedEnd,
  };
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
