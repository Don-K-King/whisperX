import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildSpeakerDisplayLabel,
  buildSpeakerOptionEntries,
  parseSidebarSectionState,
  parseSidebarVisibility,
  SIDEBAR_SECTION_IDS,
  serializeSidebarSectionState,
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

test('parseSidebarSectionState defaults all sections to open', () => {
  const parsed = parseSidebarSectionState(null);
  assert.deepEqual(parsed, {
    status: true,
    searchReplace: true,
    speakerReassign: true,
    changeLog: true,
  });
});

test('parseSidebarSectionState applies persisted open sections only for known ids', () => {
  const parsed = parseSidebarSectionState('["status","changeLog","unknown"]');
  assert.deepEqual(parsed, {
    status: true,
    searchReplace: false,
    speakerReassign: false,
    changeLog: true,
  });
});

test('serializeSidebarSectionState persists only open and known sections', () => {
  const serialized = serializeSidebarSectionState({
    status: true,
    searchReplace: false,
    speakerReassign: true,
    changeLog: false,
    rogue: true,
  });
  assert.equal(serialized, '["status","speakerReassign"]');
});

test('parse and serialize sidebar section state round-trip', () => {
  const openState = {
    status: false,
    searchReplace: true,
    speakerReassign: false,
    changeLog: true,
  };
  const serialized = serializeSidebarSectionState(openState);
  const parsed = parseSidebarSectionState(serialized);
  assert.deepEqual(parsed, openState);
  assert.deepEqual(SIDEBAR_SECTION_IDS, ['status', 'searchReplace', 'speakerReassign', 'changeLog']);
});
