import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const workspaceJsPath = new URL('../correction_workspace.js', import.meta.url);

function loadWorkspaceSource() {
  return readFileSync(workspaceJsPath, 'utf8');
}

test('export menu contains markdown, pdf, word docx and txt entries', () => {
  const js = loadWorkspaceSource();
  assert.match(js, /id="cw-export-md"/);
  assert.match(js, /id="cw-export-pdf"/);
  assert.match(js, /id="cw-export-word-docx"/);
  assert.match(js, /id="cw-export-txt"/);
});

test('print and court labels are removed from export UI', () => {
  const js = loadWorkspaceSource();
  assert.doesNotMatch(js, /id="cw-print"/);
  assert.doesNotMatch(js, /id="cw-export-print"/);
  assert.doesNotMatch(js, /id="cw-export-mode-compact"/);
  assert.doesNotMatch(js, /id="cw-export-mode-raw"/);
  assert.doesNotMatch(js, /Gerichtsexport/);
  assert.doesNotMatch(js, /Drucken/);
});

test('all export actions are hardwired to compact mode', () => {
  const js = loadWorkspaceSource();
  assert.match(js, /const exportMode = 'compact'/);
  assert.match(js, /format === 'word_docx' \|\| format === 'txt'/);
});
