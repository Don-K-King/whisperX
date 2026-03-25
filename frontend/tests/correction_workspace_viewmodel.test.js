import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildSpeakerDisplayLabel,
  buildSpeakerOptionEntries,
  deriveMarkedTextRange,
  parseSidebarSectionState,
  parseSidebarVisibility,
  resolveMarkedTextRange,
  resolveMediaSeekTime,
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

test('deriveMarkedTextRange returns sanitized range for valid text selection', () => {
  const range = deriveMarkedTextRange({
    segmentId: 'seg_7',
    selectionStart: 2,
    selectionEnd: 6,
    textLength: 10,
  });
  assert.deepEqual(range, {
    segmentId: 'seg_7',
    startChar: 2,
    endChar: 6,
    length: 4,
  });
});

test('deriveMarkedTextRange rejects invalid or empty selection', () => {
  assert.equal(deriveMarkedTextRange({
    segmentId: 'seg_7',
    selectionStart: 4,
    selectionEnd: 4,
    textLength: 10,
  }), null);
  assert.equal(deriveMarkedTextRange({
    segmentId: 'seg_7',
    selectionStart: -1,
    selectionEnd: 3,
    textLength: 10,
  }), null);
  assert.equal(deriveMarkedTextRange({
    segmentId: '',
    selectionStart: 1,
    selectionEnd: 2,
    textLength: 10,
  }), null);
  assert.equal(deriveMarkedTextRange({
    segmentId: 'seg_7',
    selectionStart: 1,
    selectionEnd: 20,
    textLength: 10,
  }), null);
});

test('resolveMarkedTextRange keeps previous range when latest is empty', () => {
  const previous = { segmentId: 'seg_1', startChar: 2, endChar: 5, length: 3 };
  const resolved = resolveMarkedTextRange({ previousRange: previous, latestRange: null });
  assert.deepEqual(resolved, previous);
});

test('resolveMarkedTextRange prefers latest valid range', () => {
  const previous = { segmentId: 'seg_1', startChar: 2, endChar: 5, length: 3 };
  const latest = { segmentId: 'seg_2', startChar: 1, endChar: 4, length: 3 };
  const resolved = resolveMarkedTextRange({ previousRange: previous, latestRange: latest });
  assert.deepEqual(resolved, latest);
});

test('resolveMediaSeekTime normalizes invalid values', () => {
  assert.equal(resolveMediaSeekTime(3.25), 3.25);
  assert.equal(resolveMediaSeekTime(-2), 0);
  assert.equal(resolveMediaSeekTime('abc'), null);
});
