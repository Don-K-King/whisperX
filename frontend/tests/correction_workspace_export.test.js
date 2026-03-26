import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildCorrectionExportBaseName,
  buildCorrectionExportSegments,
  buildCorrectionMarkdownExport,
  buildCorrectionPlainTextExport,
  buildCorrectionWordDocument,
  buildSimplePdfFromPlainText,
} from '../correction_workspace_export.js';

test('buildCorrectionExportBaseName creates stable safe filename', () => {
  const base = buildCorrectionExportBaseName({
    jobId: 'job:abc/123',
    createdAt: new Date('2026-03-25T12:34:00Z'),
  });
  assert.equal(base, 'transcript_job_abc_123_20260325_1234');
});

test('buildCorrectionMarkdownExport renders blocks with timestamps and labels', () => {
  const markdown = buildCorrectionMarkdownExport({
    jobId: 'job-1',
    sessionId: 'cs-1',
    baseVersion: 2,
    workingVersion: 4,
    reviewStatus: 'in_review',
    isFinal: false,
    mode: 'compact',
    createdAt: new Date('2026-03-25T12:00:00Z'),
    speakerLabels: { SPEAKER_01: 'Alice' },
    segments: [
      { speaker: 'SPEAKER_01', start: 0, end: 5, text: 'Hallo Welt' },
    ],
  });
  assert.ok(markdown.includes('# Korrektur-Export Job job-1'));
  assert.ok(markdown.includes('- Session-ID: cs-1'));
  assert.ok(markdown.includes('- Basis-Version: 2'));
  assert.ok(markdown.includes('- Arbeits-Version: 4'));
  assert.ok(markdown.includes('- Review-Status: in_review'));
  assert.ok(markdown.includes('- Final: Nein'));
  assert.ok(markdown.includes('- Export-Modus: compact'));
  assert.ok(markdown.includes('### Alice (SPEAKER_01) | 00:00:00 - 00:00:05'));
  assert.ok(markdown.includes('Hallo Welt'));
});

test('buildCorrectionPlainTextExport renders transcript lines', () => {
  const text = buildCorrectionPlainTextExport({
    jobId: 'job-2',
    sessionId: 'cs-2',
    baseVersion: 1,
    workingVersion: 1,
    reviewStatus: 'approved',
    isFinal: true,
    mode: 'raw',
    createdAt: new Date('2026-03-25T13:00:00Z'),
    speakerLabels: { SPEAKER_02: 'Bob' },
    segments: [
      { speaker: 'SPEAKER_02', start: 10, end: 12, text: 'Danke.' },
    ],
  });
  assert.ok(text.includes('Korrektur-Export'));
  assert.ok(text.includes('Job-ID: job-2'));
  assert.ok(text.includes('Session-ID: cs-2'));
  assert.ok(text.includes('Final: Ja'));
  assert.ok(text.includes('Export-Modus: raw'));
  assert.ok(text.includes('[00:00:10 - 00:00:12] Bob (SPEAKER_02)'));
  assert.ok(text.includes('Danke.'));
});

test('compact_merges_consecutive_same_speaker_even_with_gaps', () => {
  const merged = buildCorrectionExportSegments({
    segments: [
      { speaker: 'S1', start: 0, end: 1, text: 'A' },
      { speaker: 'S1', start: 5, end: 7, text: 'B' },
    ],
    mode: 'compact',
  });
  assert.equal(merged.length, 1);
  assert.equal(merged[0].start, 0);
  assert.equal(merged[0].end, 7);
  assert.equal(merged[0].text, 'A\nB');
});

test('compact_does_not_merge_on_speaker_change', () => {
  const merged = buildCorrectionExportSegments({
    segments: [
      { speaker: 'S1', start: 0, end: 1, text: 'A' },
      { speaker: 'S2', start: 1.5, end: 2, text: 'B' },
      { speaker: 'S1', start: 2.5, end: 3, text: 'C' },
    ],
    mode: 'compact',
  });
  assert.equal(merged.length, 3);
  assert.equal(merged[0].text, 'A');
  assert.equal(merged[1].text, 'B');
  assert.equal(merged[2].text, 'C');
});

test('raw_mode_emits_original_segment_count', () => {
  const raw = buildCorrectionExportSegments({
    segments: [
      { speaker: 'S1', start: 0, end: 1, text: 'A' },
      { speaker: 'S1', start: 5, end: 7, text: 'B' },
    ],
    mode: 'raw',
  });
  assert.equal(raw.length, 2);
});

test('compact_mode_emits_expected_block_count_and_ranges', () => {
  const compact = buildCorrectionExportSegments({
    segments: [
      { speaker: 'S1', start: 0, end: 1, text: 'A' },
      { speaker: 'S1', start: 2, end: 3, text: 'B' },
      { speaker: 'S2', start: 3, end: 4, text: 'C' },
      { speaker: 'S2', start: 4.5, end: 6, text: 'D' },
    ],
    mode: 'compact',
  });
  assert.equal(compact.length, 2);
  assert.equal(compact[0].start, 0);
  assert.equal(compact[0].end, 3);
  assert.equal(compact[1].start, 3);
  assert.equal(compact[1].end, 6);
});

test('buildCorrectionWordDocument escapes control chars and supports unicode', () => {
  const rtf = buildCorrectionWordDocument({
    title: 'Titel {A}',
    text: 'Zeile \\ eins\näöü',
  });
  assert.ok(rtf.startsWith('{\\rtf1'));
  assert.ok(rtf.includes('Titel \\{A\\}'));
  assert.ok(rtf.includes('Zeile \\\\ eins\\par'));
  assert.ok(rtf.includes('\\u228?'));
});

test('buildSimplePdfFromPlainText emits a PDF header and trailer', () => {
  const bytes = buildSimplePdfFromPlainText('Hallo PDF');
  const content = new TextDecoder().decode(bytes);
  assert.ok(content.startsWith('%PDF-1.4'));
  assert.ok(content.includes('xref'));
  assert.ok(content.includes('%%EOF'));
});
