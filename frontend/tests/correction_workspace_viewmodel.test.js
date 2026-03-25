import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildSpeakerDisplayLabel,
  buildSpeakerOptionEntries,
  deriveMarkedTextRange,
  parseAutoSeekSelectionEnabled,
  parseSidebarSectionState,
  parseSidebarVisibility,
  resolveSelectedSegmentId,
  resolveMarkedTextRange,
  resolveMediaSeekTime,
  shouldAutoSeek,
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

test('shouldAutoSeek returns true only for segment change and supported source', () => {
  assert.equal(shouldAutoSeek({
    previousSegmentId: 'seg_1',
    nextSegmentId: 'seg_2',
    source: 'block_click',
  }), true);
  assert.equal(shouldAutoSeek({
    previousSegmentId: 'seg_1',
    nextSegmentId: 'seg_2',
    source: 'text_focus',
  }), true);
});

test('shouldAutoSeek returns false for same segment, missing ids, and unsupported source', () => {
  assert.equal(shouldAutoSeek({
    previousSegmentId: 'seg_1',
    nextSegmentId: 'seg_1',
    source: 'block_click',
  }), false);
  assert.equal(shouldAutoSeek({
    previousSegmentId: '',
    nextSegmentId: 'seg_2',
    source: 'block_click',
  }), false);
  assert.equal(shouldAutoSeek({
    previousSegmentId: 'seg_1',
    nextSegmentId: 'seg_2',
    source: 'jump_button',
  }), false);
});

test('parseAutoSeekSelectionEnabled supports persisted toggle values', () => {
  assert.equal(parseAutoSeekSelectionEnabled('1'), true);
  assert.equal(parseAutoSeekSelectionEnabled('0'), false);
  assert.equal(parseAutoSeekSelectionEnabled(null), true);
});

test('resolveSelectedSegmentId keeps previous id when still available', () => {
  const selected = resolveSelectedSegmentId({
    previousSegmentId: 'seg_2',
    segments: [
      { segment_id: 'seg_1' },
      { segment_id: 'seg_2' },
    ],
  });
  assert.equal(selected, 'seg_2');
});

test('resolveSelectedSegmentId maps to split successor when previous segment was split', () => {
  const selected = resolveSelectedSegmentId({
    previousSegmentId: 'seg_20',
    segments: [
      { segment_id: 'seg_19' },
      { segment_id: 'seg_20_a' },
      { segment_id: 'seg_20_b' },
    ],
  });
  assert.equal(selected, 'seg_20_a');
});

test('resolveSelectedSegmentId falls back to first segment when previous is missing', () => {
  const selected = resolveSelectedSegmentId({
    previousSegmentId: 'seg_99',
    segments: [
      { segment_id: 'seg_1' },
      { segment_id: 'seg_2' },
    ],
  });
  assert.equal(selected, 'seg_1');
  assert.equal(resolveSelectedSegmentId({ previousSegmentId: 'seg_99', segments: [] }), null);
});
