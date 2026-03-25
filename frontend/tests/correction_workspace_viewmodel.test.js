import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildSpeakerDisplayLabel,
  buildSpeakerOptionEntries,
  parseSidebarVisibility,
} from '../correction_workspace_viewmodel.js';

test('buildSpeakerDisplayLabel renders alias plus speaker key', () => {
  const label = buildSpeakerDisplayLabel({
    speakerKey: 'SPEAKER_01',
    speakerLabels: {
      SPEAKER_01: 'Patrick',
    },
  });
  assert.equal(label, 'Patrick (SPEAKER_01)');
});

test('buildSpeakerDisplayLabel falls back to speaker key when alias missing', () => {
  const label = buildSpeakerDisplayLabel({
    speakerKey: 'SPEAKER_02',
    speakerLabels: {},
  });
  assert.equal(label, 'SPEAKER_02');
});

test('buildSpeakerOptionEntries keeps unique speaker keys and uses display labels', () => {
  const entries = buildSpeakerOptionEntries({
    segments: [
      { speaker: 'SPEAKER_01' },
      { speaker: 'SPEAKER_01' },
      { speaker: 'SPEAKER_02' },
    ],
    speakerLabels: {
      SPEAKER_01: 'Patrick',
      SPEAKER_03: 'Angela',
    },
  });

  assert.deepEqual(entries, [
    { key: 'SPEAKER_01', label: 'Patrick (SPEAKER_01)' },
    { key: 'SPEAKER_02', label: 'SPEAKER_02' },
    { key: 'SPEAKER_03', label: 'Angela (SPEAKER_03)' },
  ]);
});

test('parseSidebarVisibility supports persisted toggle values', () => {
  assert.equal(parseSidebarVisibility('1'), true);
  assert.equal(parseSidebarVisibility('0'), false);
  assert.equal(parseSidebarVisibility(null), true);
});
