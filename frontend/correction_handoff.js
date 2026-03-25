const HANDOFF_PREFIX = 'evodox-correction-handoff:';
const HANDOFF_TTL_MS = 5 * 60 * 1000;

export function createCorrectionHandoff(
  {
    token,
    jobId,
    tenantId,
    theme = 'light',
  },
  {
    storage = globalThis.localStorage,
    nowMs = Date.now(),
    ttlMs = HANDOFF_TTL_MS,
    handoffId = crypto.randomUUID(),
  } = {},
) {
  if (!storage) throw new Error('handoff.storage_unavailable');
  const normalizedToken = String(token || '').trim();
  const normalizedJobId = String(jobId || '').trim();
  if (!normalizedToken || !normalizedJobId) {
    throw new Error('handoff.invalid_payload');
  }

  const key = `${HANDOFF_PREFIX}${handoffId}`;
  const payload = {
    token: normalizedToken,
    jobId: normalizedJobId,
    tenantId: String(tenantId || '').trim(),
    theme: theme === 'dark' ? 'dark' : 'light',
    createdAt: Number(nowMs),
    expiresAt: Number(nowMs) + Number(ttlMs),
  };
  storage.setItem(key, JSON.stringify(payload));
  return handoffId;
}

export function consumeCorrectionHandoff(
  handoffId,
  {
    storage = globalThis.localStorage,
    nowMs = Date.now(),
  } = {},
) {
  if (!storage) return null;
  const id = String(handoffId || '').trim();
  if (!id) return null;
  const key = `${HANDOFF_PREFIX}${id}`;
  const raw = storage.getItem(key);
  if (!raw) return null;
  storage.removeItem(key);

  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== 'object') return null;
  if (Number(parsed.expiresAt || 0) <= Number(nowMs)) return null;
  const token = String(parsed.token || '').trim();
  const jobId = String(parsed.jobId || '').trim();
  if (!token || !jobId) return null;
  return {
    token,
    jobId,
    tenantId: String(parsed.tenantId || '').trim(),
    theme: parsed.theme === 'dark' ? 'dark' : 'light',
  };
}

export function cleanupExpiredCorrectionHandoffs(
  {
    storage = globalThis.localStorage,
    nowMs = Date.now(),
  } = {},
) {
  if (!storage) return 0;
  const keysToDelete = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (!key || !key.startsWith(HANDOFF_PREFIX)) continue;
    const raw = storage.getItem(key);
    if (!raw) {
      keysToDelete.push(key);
      continue;
    }
    try {
      const payload = JSON.parse(raw);
      if (Number(payload?.expiresAt || 0) <= Number(nowMs)) {
        keysToDelete.push(key);
      }
    } catch {
      keysToDelete.push(key);
    }
  }
  keysToDelete.forEach((key) => storage.removeItem(key));
  return keysToDelete.length;
}

