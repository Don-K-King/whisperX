import test from 'node:test';
import assert from 'node:assert/strict';

import {
  applyReplaceLiteral,
  applySpeakerReassign,
  findActiveSegmentIndex,
  mergeConsecutiveSpeakerBlocks,
  mergeAdjacentSegments,
  normalizeSegments,
} from '../correction_utils.js';

test('normalizeSegments creates deterministic segment ids', () => {
  const segments = normalizeSegments([{ speaker: 'S1', text: 'Hallo', start: 0, end: 1 }]);
  assert.equal(segments[0].segment_id, 'seg_000001');
});

test('findActiveSegmentIndex returns segment for current time and fallback', () => {
  const segments = normalizeSegments([
    { segment_id: 'seg_1', start: 0, end: 1, speaker: 'S1', text: 'A' },
    { segment_id: 'seg_2', start: 1, end: 2, speaker: 'S2', text: 'B' },
  ]);
  assert.equal(findActiveSegmentIndex({ segments, currentTime: 0.5 }), 0);
  assert.equal(findActiveSegmentIndex({ segments, currentTime: 2.5 }), 1);
});

test('applyReplaceLiteral replaces one or many matches', () => {
  const payload = {
    segments: [
      { segment_id: 'seg_1', start: 0, end: 1, speaker: 'S1', text: 'Hallo Hallo' },
      { segment_id: 'seg_2', start: 1, end: 2, speaker: 'S2', text: 'Welt' },
    ],
    query: 'Hallo',
    replace: 'Tag',
    replaceAll: false,
  };
  const single = applyReplaceLiteral(payload);
  assert.equal(single.replacements, 1);
  assert.equal(single.segments[0].text, 'Tag Hallo');

  const all = applyReplaceLiteral({ ...payload, replaceAll: true });
  assert.equal(all.replacements, 2);
  assert.equal(all.segments[0].text, 'Tag Tag');
});

test('applySpeakerReassign supports partial segment reassignment', () => {
  const original = [
    { segment_id: 'seg_1', start: 0, end: 10, speaker: 'S1', text: 'Hallo Welt' },
  ];
  const result = applySpeakerReassign({
    segments: original,
    segmentId: 'seg_1',
    speaker: 'S2',
    startChar: 6,
    endChar: 10,
  });

  assert.equal(result.changed, true);
  assert.equal(result.segments.length, 2);
  assert.equal(result.segments[1].speaker, 'S2');
});

test('mergeAdjacentSegments merges contiguous segments of same speaker', () => {
  const merged = mergeAdjacentSegments([
    { segment_id: 'a', start: 0, end: 1, speaker: 'S1', text: 'A' },
    { segment_id: 'b', start: 1, end: 2, speaker: 'S1', text: 'B' },
    { segment_id: 'c', start: 2, end: 3, speaker: 'S2', text: 'C' },
  ]);

  assert.equal(merged.length, 2);
  assert.equal(merged[0].text, 'A\nB');
});

test('mergeConsecutiveSpeakerBlocks merges consecutive speaker blocks and keeps range', () => {
  const merged = mergeConsecutiveSpeakerBlocks([
    { segment_id: 'seg_1', start: 0, end: 1, speaker: 'S1', text: 'A' },
    { segment_id: 'seg_2', start: 1.2, end: 2, speaker: 'S1', text: 'B' },
    { segment_id: 'seg_3', start: 2, end: 3, speaker: 'S2', text: 'C' },
  ]);

  assert.equal(merged.length, 2);
  assert.equal(merged[0].segment_id, 'seg_1');
  assert.equal(merged[0].start, 0);
  assert.equal(merged[0].end, 2);
  assert.equal(merged[0].text, 'A\nB');
});
