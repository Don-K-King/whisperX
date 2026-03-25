import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildCorrectionExportBaseName,
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
    createdAt: new Date('2026-03-25T12:00:00Z'),
    speakerLabels: { SPEAKER_01: 'Alice' },
    segments: [
      { speaker: 'SPEAKER_01', start: 0, end: 5, text: 'Hallo Welt' },
    ],
  });
  assert.ok(markdown.includes('# Korrektur-Export Job job-1'));
  assert.ok(markdown.includes('### Block 1 - Alice (SPEAKER_01)'));
  assert.ok(markdown.includes('- Zeit: 00:00:00 - 00:00:05'));
  assert.ok(markdown.includes('Hallo Welt'));
});

test('buildCorrectionPlainTextExport renders transcript lines', () => {
  const text = buildCorrectionPlainTextExport({
    speakerLabels: { SPEAKER_02: 'Bob' },
    segments: [
      { speaker: 'SPEAKER_02', start: 10, end: 12, text: 'Danke.' },
    ],
  });
  assert.ok(text.includes('[00:00:10 - 00:00:12] Bob (SPEAKER_02)'));
  assert.ok(text.includes('Danke.'));
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
