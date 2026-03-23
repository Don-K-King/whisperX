export const DEFAULT_DECODING_OPTIONS = {
  temperature: 0.0,
  beam_size: 5,
  patience: 1.0,
  length_penalty: 1.0,
  compression_ratio_threshold: 2.4,
  logprob_threshold: -1.0,
  no_speech_threshold: 0.6,
  suppress_tokens: '-1',
  initial_prompt: '',
  condition_on_previous_text: false,
  chunk_size: 30,
  vad_onset: 0.5,
  vad_offset: 0.363,
  language: 'auto',
};

const FLOAT_RANGES = {
  temperature: [0.0, 1.0],
  patience: [0.1, 2.0],
  length_penalty: [0.1, 2.0],
  compression_ratio_threshold: [0.5, 5.0],
  logprob_threshold: [-5.0, 0.0],
  no_speech_threshold: [0.0, 1.0],
  vad_onset: [0.0, 1.0],
  vad_offset: [0.0, 1.0],
};

const INT_RANGES = {
  beam_size: [1, 10],
  chunk_size: [5, 60],
};
const ALLOWED_LANGUAGES = new Set(['auto', 'de', 'en', 'fr', 'es', 'it']);

function validationError(message){
  const err = new Error(message);
  err.error_code = 'transcription_settings.invalid_payload';
  return err;
}

function coerceFloat(value, key){
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw validationError(`${key} must be numeric`);
  return parsed;
}

function coerceInt(value, key){
  const parsed = Number(value);
  if (!Number.isInteger(parsed)) throw validationError(`${key} must be an integer`);
  return parsed;
}

function normalizeSuppressTokens(value){
  const text = String(value ?? '').trim();
  if (!text) throw validationError('suppress_tokens must not be empty');
  const parts = text.split(',').map((entry) => entry.trim());
  if (parts.some((entry) => entry.length === 0)) throw validationError('suppress_tokens csv invalid');
  for (const part of parts){
    if (!/^-?\d+$/.test(part)) throw validationError('suppress_tokens must contain integer ids');
  }
  return parts.join(',');
}

function normalizeCondition(raw){
  if (typeof raw === 'boolean') return raw;
  if (String(raw).toLowerCase() === 'true') return true;
  if (String(raw).toLowerCase() === 'false') return false;
  throw validationError('condition_on_previous_text must be boolean');
}

export function validateDecodingOptions(input){
  if (!input || typeof input !== 'object') throw validationError('payload must be object');
  const normalized = { ...DEFAULT_DECODING_OPTIONS };
  const unknown = Object.keys(input).filter((key) => !(key in DEFAULT_DECODING_OPTIONS));
  if (unknown.length > 0) throw validationError(`unknown options: ${unknown.join(',')}`);

  for (const [key, [min, max]] of Object.entries(FLOAT_RANGES)){
    if (!(key in input)) continue;
    const value = coerceFloat(input[key], key);
    if (value < min || value > max) throw validationError(`${key} out of range`);
    normalized[key] = value;
  }

  for (const [key, [min, max]] of Object.entries(INT_RANGES)){
    if (!(key in input)) continue;
    const value = coerceInt(input[key], key);
    if (value < min || value > max) throw validationError(`${key} out of range`);
    normalized[key] = value;
  }

  if ('suppress_tokens' in input) normalized.suppress_tokens = normalizeSuppressTokens(input.suppress_tokens);
  if ('initial_prompt' in input){
    const prompt = String(input.initial_prompt ?? '');
    if (prompt.length > 500) throw validationError('initial_prompt too long');
    normalized.initial_prompt = prompt;
  }
  if ('condition_on_previous_text' in input){
    normalized.condition_on_previous_text = normalizeCondition(input.condition_on_previous_text);
  }
  if ('language' in input){
    const value = String(input.language ?? '').trim().toLowerCase();
    if (!ALLOWED_LANGUAGES.has(value)) throw validationError('language not supported');
    normalized.language = value;
  }

  return normalized;
}

export async function loadTranscriptionSettings({ callApi }){
  const response = await callApi('/api/v1/admin/transcription-settings');
  const options = validateDecodingOptions(response?.decoding_options ?? {});
  return {
    ...response,
    decoding_options: options,
  };
}

export async function saveTranscriptionSettings({ callApi, decodingOptions }){
  const payload = validateDecodingOptions(decodingOptions);
  const response = await callApi('/api/v1/admin/transcription-settings', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
  return {
    ...response,
    decoding_options: validateDecodingOptions(response?.decoding_options ?? payload),
  };
}
