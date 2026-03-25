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
