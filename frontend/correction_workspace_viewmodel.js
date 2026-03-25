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
