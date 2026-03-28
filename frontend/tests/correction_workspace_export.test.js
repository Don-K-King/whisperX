import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildCorrectionExportBaseName,
  buildCorrectionExportSegments,
  buildCorrectionMarkdownExport,
  buildCorrectionPlainTextExport,
  buildSimpleDocxFromPlainText,
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
  assert.ok(markdown.includes('# Einvernahmeprotokoll'));
  assert.ok(markdown.includes('Job-ID: job-1'));
  assert.ok(markdown.includes('Session-ID: cs-1'));
  assert.ok(markdown.includes('Basis-Version: 2'));
  assert.ok(markdown.includes('Arbeits-Version: 4'));
  assert.ok(markdown.includes('Review-Status: in_review'));
  assert.ok(markdown.includes('Final: Nein'));
  assert.ok(markdown.includes('Exportzeitpunkt (UTC): 2026-03-25T12:00:00.000Z'));
  assert.ok(markdown.includes('[00:00:00 - 00:00:05] Alice:'));
  assert.ok(markdown.includes('Hallo Welt'));
  assert.ok(!markdown.includes('Alice (SPEAKER_01)'));
  assert.ok(!markdown.includes('Export-Modus'));
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
  assert.ok(text.includes('Einvernahmeprotokoll'));
  assert.ok(text.includes('Job-ID: job-2'));
  assert.ok(text.includes('Session-ID: cs-2'));
  assert.ok(text.includes('Review-Status: approved'));
  assert.ok(text.includes('Final: Ja'));
  assert.ok(text.includes('Exportzeitpunkt (UTC): 2026-03-25T13:00:00.000Z'));
  assert.ok(text.includes('[00:00:10 - 00:00:12] Bob:'));
  assert.ok(text.includes('Danke.'));
  assert.ok(!text.includes('Bob (SPEAKER_02)'));
  assert.ok(!text.includes('Export-Modus'));
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

test('plain text export in raw mode preserves original speaker block boundaries', () => {
  const text = buildCorrectionPlainTextExport({
    jobId: 'job-raw',
    sessionId: 'cs-raw',
    mode: 'raw',
    createdAt: new Date('2026-03-28T10:00:00Z'),
    segments: [
      { speaker: 'S1', start: 0, end: 1, text: 'A' },
      { speaker: 'S1', start: 2, end: 3, text: 'B' },
    ],
  });
  const blockMatches = text.match(/\[00:00:\d{2} - 00:00:\d{2}\] S1:/g) || [];
  assert.equal(blockMatches.length, 2);
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

test('buildSimpleDocxFromPlainText creates valid docx zip container', () => {
  const bytes = buildSimpleDocxFromPlainText('Titel\nZeile ���');
  const signature = new TextDecoder().decode(bytes.slice(0, 2));
  assert.equal(signature, 'PK');
  const content = new TextDecoder().decode(bytes);
  assert.ok(content.includes('[Content_Types].xml'));
  assert.ok(content.includes('word/document.xml'));
  assert.ok(content.includes('_rels/.rels'));
});

test('buildSimplePdfFromPlainText emits a PDF header and trailer', () => {
  const bytes = buildSimplePdfFromPlainText('Hallo PDF');
  const content = new TextDecoder().decode(bytes);
  assert.ok(content.startsWith('%PDF-1.4'));
  assert.ok(content.includes('xref'));
  assert.ok(content.includes('%%EOF'));
});
