import test from 'node:test';
import assert from 'node:assert/strict';

import {
  DEFAULT_DECODING_OPTIONS,
  loadTranscriptionSettings,
  saveTranscriptionSettings,
  validateDecodingOptions,
} from '../transcription_settings_flow.js';

test('loadTranscriptionSettings reads decoding options from API', async () => {
  const apiCalls = [];
  const callApi = async (path) => {
    apiCalls.push(path);
    return {
      tenant_id: 'tenant-a',
      decoding_options: { ...DEFAULT_DECODING_OPTIONS, beam_size: 4 },
    };
  };

  const result = await loadTranscriptionSettings({ callApi });

  assert.equal(apiCalls[0], '/api/v1/admin/transcription-settings');
  assert.equal(result.decoding_options.beam_size, 4);
});

test('saveTranscriptionSettings validates and persists options via PUT', async () => {
  const apiCalls = [];
  const callApi = async (path, options = {}) => {
    apiCalls.push([path, options]);
    return {
      tenant_id: 'tenant-a',
      decoding_options: JSON.parse(options.body),
    };
  };

  const result = await saveTranscriptionSettings({
    callApi,
    decodingOptions: {
      temperature: 0.2,
      beam_size: 4,
      patience: 1.1,
      length_penalty: 1.0,
      compression_ratio_threshold: 2.2,
      logprob_threshold: -1.0,
      no_speech_threshold: 0.5,
      suppress_tokens: '-1,12',
      initial_prompt: 'Fachsprache',
      condition_on_previous_text: true,
      chunk_size: 24,
      vad_onset: 0.4,
      vad_offset: 0.3,
      language: 'de',
    },
  });

  assert.equal(apiCalls.length, 1);
  assert.equal(apiCalls[0][0], '/api/v1/admin/transcription-settings');
  assert.equal(apiCalls[0][1].method, 'PUT');
  assert.equal(result.decoding_options.beam_size, 4);
  assert.equal(result.decoding_options.condition_on_previous_text, true);
  assert.equal(result.decoding_options.chunk_size, 24);
  assert.equal(result.decoding_options.vad_onset, 0.4);
  assert.equal(result.decoding_options.vad_offset, 0.3);
  assert.equal(result.decoding_options.language, 'de');
});

test('validateDecodingOptions rejects out-of-range values', () => {
  assert.throws(
    () => validateDecodingOptions({ ...DEFAULT_DECODING_OPTIONS, temperature: 9 }),
    (error) => error?.error_code === 'transcription_settings.invalid_payload',
  );
});

test('validateDecodingOptions rejects malformed suppress_tokens', () => {
  assert.throws(
    () => validateDecodingOptions({ ...DEFAULT_DECODING_OPTIONS, suppress_tokens: '-1,abc' }),
    (error) => error?.error_code === 'transcription_settings.invalid_payload',
  );
});

test('validateDecodingOptions rejects chunk_size outside allowed range', () => {
  assert.throws(
    () => validateDecodingOptions({ ...DEFAULT_DECODING_OPTIONS, chunk_size: 2 }),
    (error) => error?.error_code === 'transcription_settings.invalid_payload',
  );
});
