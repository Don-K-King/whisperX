import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildSpeakerDisplayLabel,
  buildSpeakerOptionEntries,
  resolveCorrectionBootstrapFeedback,
  deriveMarkedTextRange,
  parseAutoSeekSelectionEnabled,
  parseSidebarSectionState,
  parseSidebarVisibility,
  resolveExportMenuState,
  resolveSpeakerTint,
  resolveSelectedSegmentId,
  resolveGapSeekTargetIndex,
  resolveVirtualWindowPreferredIndex,
  resolvePlaybackFollowDecision,
  resolveSeekWarmupRange,
  resolveSeekWarmupReadiness,
  resolveSeekPlaybackResumeDecision,
  resolveForcedVirtualRange,
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

test('resolveSpeakerTint is deterministic per speaker key and uses neutral unknown fallback', () => {
  const first = resolveSpeakerTint({ speakerKey: 'SPEAKER_12' });
  const second = resolveSpeakerTint({ speakerKey: 'SPEAKER_12' });
  const unknown = resolveSpeakerTint({ speakerKey: 'UNKNOWN' });

  assert.deepEqual(first, second);
  assert.notEqual(first.background, unknown.background);
  assert.match(first.background, /^rgba\(\d+, \d+, \d+, 0\.\d+\)$/);
  assert.match(first.border, /^rgba\(\d+, \d+, \d+, 0\.\d+\)$/);
  assert.match(first.active, /^rgba\(\d+, \d+, \d+, 0\.\d+\)$/);
  assert.match(first.focus, /^rgba\(\d+, \d+, \d+, 0\.\d+\)$/);
});

test('resolveExportMenuState supports toggle, close, outside and select transitions', () => {
  const opened = resolveExportMenuState({ isOpen: false }, { type: 'toggle' });
  assert.deepEqual(opened, { isOpen: true, lastAction: '' });

  const selected = resolveExportMenuState(opened, { type: 'select', action: 'pdf' });
  assert.deepEqual(selected, { isOpen: false, lastAction: 'pdf' });

  const reopened = resolveExportMenuState(selected, { type: 'open' });
  assert.deepEqual(reopened, { isOpen: true, lastAction: 'pdf' });

  const outsideClosed = resolveExportMenuState(reopened, { type: 'outside' });
  assert.deepEqual(outsideClosed, { isOpen: false, lastAction: 'pdf' });

  const escaped = resolveExportMenuState({ isOpen: true, lastAction: 'pdf' }, { type: 'escape' });
  assert.deepEqual(escaped, { isOpen: false, lastAction: 'pdf' });
});

test('parseSidebarVisibility supports persisted toggle values', () => {
  assert.equal(parseSidebarVisibility('1'), true);
  assert.equal(parseSidebarVisibility('0'), false);
  assert.equal(parseSidebarVisibility(null), true);
});

test('parseSidebarSectionState defaults all sections to collapsed', () => {
  const parsed = parseSidebarSectionState(null);
  assert.deepEqual(parsed, {
    status: false,
    searchReplace: false,
    speakerReassign: false,
    changeLog: false,
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

test('parseSidebarSectionState object input requires explicit true', () => {
  const parsed = parseSidebarSectionState('{"status":true,"searchReplace":false}');
  assert.deepEqual(parsed, {
    status: true,
    searchReplace: false,
    speakerReassign: false,
    changeLog: false,
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

test('resolveGapSeekTargetIndex picks next segment in timeline gaps', () => {
  const target = resolveGapSeekTargetIndex({
    segments: [
      { segment_id: 'seg_1', start: 0, end: 2 },
      { segment_id: 'seg_2', start: 5, end: 7 },
      { segment_id: 'seg_3', start: 10, end: 12 },
    ],
    currentTime: 3,
    activeIndex: -1,
  });
  assert.equal(target, 1);
});

test('resolveGapSeekTargetIndex falls back to previous when seek is beyond last segment', () => {
  const target = resolveGapSeekTargetIndex({
    segments: [
      { segment_id: 'seg_1', start: 0, end: 2 },
      { segment_id: 'seg_2', start: 5, end: 7 },
    ],
    currentTime: 99,
    activeIndex: -1,
  });
  assert.equal(target, 1);
});

test('resolveVirtualWindowPreferredIndex prefers playback anchor when follow is enabled', () => {
  const preferred = resolveVirtualWindowPreferredIndex({
    selectedIndex: 12,
    activeIndex: 24,
    playbackAnchorIndex: 240,
    preferPlaybackAnchor: true,
  });
  assert.equal(preferred, 240);
});

test('resolveVirtualWindowPreferredIndex falls back to selected when playback anchor is disabled', () => {
  const preferred = resolveVirtualWindowPreferredIndex({
    selectedIndex: 12,
    activeIndex: 24,
    playbackAnchorIndex: 240,
    preferPlaybackAnchor: false,
  });
  assert.equal(preferred, 12);
});

test('resolvePlaybackFollowDecision requests a window shift when active block is outside range', () => {
  const decision = resolvePlaybackFollowDecision({
    activeIndex: 420,
    rangeStart: 0,
    rangeEnd: 30,
    followPending: false,
    nowMs: 1200,
    lastFollowMs: 0,
    throttleMs: 200,
    editorClientHeight: 760,
    rowHeight: 156,
  });
  assert.equal(decision.shouldShift, true);
  assert.equal(decision.reason, 'out_of_range');
  assert.ok(decision.targetScrollTop > 0);
});

test('resolvePlaybackFollowDecision skips shift when active block is already visible', () => {
  const decision = resolvePlaybackFollowDecision({
    activeIndex: 18,
    rangeStart: 10,
    rangeEnd: 30,
    followPending: false,
    nowMs: 1200,
    lastFollowMs: 0,
    throttleMs: 200,
  });
  assert.equal(decision.shouldShift, false);
  assert.equal(decision.reason, 'in_range');
});

test('resolvePlaybackFollowDecision skips shift while follow render is pending', () => {
  const decision = resolvePlaybackFollowDecision({
    activeIndex: 120,
    rangeStart: 0,
    rangeEnd: 20,
    followPending: true,
    nowMs: 1200,
    lastFollowMs: 0,
    throttleMs: 200,
  });
  assert.equal(decision.shouldShift, false);
  assert.equal(decision.reason, 'pending');
});

test('resolveSeekWarmupRange includes active segment and lookahead window', () => {
  const range = resolveSeekWarmupRange({
    activeIndex: 100,
    totalSegments: 1000,
    lookahead: 10,
    overscan: 8,
  });
  assert.deepEqual(range, { start: 82, end: 119 });
});

test('resolveSeekWarmupRange clamps near transcript end', () => {
  const range = resolveSeekWarmupRange({
    activeIndex: 95,
    totalSegments: 100,
    lookahead: 10,
    overscan: 8,
  });
  assert.deepEqual(range, { start: 77, end: 100 });
});

test('resolveSeekWarmupReadiness returns ready when active and lookahead are covered', () => {
  const readiness = resolveSeekWarmupReadiness({
    rangeStart: 88,
    rangeEnd: 125,
    activeIndex: 100,
    totalSegments: 1000,
    lookahead: 10,
  });
  assert.equal(readiness.isReady, true);
  assert.equal(readiness.requiredStartInclusive, 90);
  assert.equal(readiness.requiredEndExclusive, 111);
});

test('resolveSeekWarmupReadiness returns not ready when lookahead is not covered', () => {
  const readiness = resolveSeekWarmupReadiness({
    rangeStart: 90,
    rangeEnd: 108,
    activeIndex: 100,
    totalSegments: 1000,
    lookahead: 10,
  });
  assert.equal(readiness.isReady, false);
  assert.equal(readiness.requiredStartInclusive, 90);
  assert.equal(readiness.requiredEndExclusive, 111);
});

test('resolveSeekPlaybackResumeDecision resumes when warmup is ready', () => {
  const decision = resolveSeekPlaybackResumeDecision({
    wasPlaying: true,
    isWarmupReady: true,
    nowMs: 100,
    resumeDeadlineMs: 350,
  });
  assert.equal(decision.shouldResume, true);
  assert.equal(decision.shouldFinalize, true);
  assert.equal(decision.reason, 'ready');
});

test('resolveSeekPlaybackResumeDecision resumes on timeout when still not ready', () => {
  const decision = resolveSeekPlaybackResumeDecision({
    wasPlaying: true,
    isWarmupReady: false,
    nowMs: 400,
    resumeDeadlineMs: 350,
  });
  assert.equal(decision.shouldResume, true);
  assert.equal(decision.shouldFinalize, true);
  assert.equal(decision.reason, 'timeout');
});

test('resolveSeekPlaybackResumeDecision stays pending before timeout', () => {
  const decision = resolveSeekPlaybackResumeDecision({
    wasPlaying: true,
    isWarmupReady: false,
    nowMs: 200,
    resumeDeadlineMs: 350,
  });
  assert.equal(decision.shouldResume, false);
  assert.equal(decision.shouldFinalize, false);
  assert.equal(decision.reason, 'pending');
});

test('resolveSeekPlaybackResumeDecision finalizes warmup when paused and ready', () => {
  const decision = resolveSeekPlaybackResumeDecision({
    wasPlaying: false,
    isWarmupReady: true,
    nowMs: 200,
    resumeDeadlineMs: 350,
  });
  assert.equal(decision.shouldResume, false);
  assert.equal(decision.shouldFinalize, true);
  assert.equal(decision.reason, 'ready_not_playing');
});

test('resolveForcedVirtualRange clamps stale ranges and keeps target visible', () => {
  const resolved = resolveForcedVirtualRange({
    totalSegments: 12,
    start: 99,
    end: 110,
    fallbackIndex: 9,
    overscan: 2,
  });
  assert.deepEqual(resolved, { start: 7, end: 12 });
});

test('resolveForcedVirtualRange returns at least one row on inverted ranges', () => {
  const resolved = resolveForcedVirtualRange({
    totalSegments: 6,
    start: 4,
    end: 2,
    fallbackIndex: 4,
    overscan: 2,
  });
  assert.equal(resolved.start, 4);
  assert.equal(resolved.end, 5);
});

test('resolveCorrectionBootstrapFeedback exposes phase message and processing steps', () => {
  const feedback = resolveCorrectionBootstrapFeedback({ phase: 'transcript' });

  assert.equal(feedback.title, 'Transcript mit Media wird geladen');
  assert.equal(feedback.detail, 'Transcript wird geladen...');
  assert.deepEqual(feedback.steps.map((step) => step.status), [
    'done',
    'done',
    'active',
    'pending',
  ]);
});

test('resolveCorrectionBootstrapFeedback falls back to boot phase for unknown values', () => {
  const feedback = resolveCorrectionBootstrapFeedback({ phase: 'unknown' });
  assert.equal(feedback.detail, 'Korrekturmodus wird vorbereitet...');
  assert.deepEqual(feedback.steps.map((step) => step.status), [
    'active',
    'pending',
    'pending',
    'pending',
  ]);
});
