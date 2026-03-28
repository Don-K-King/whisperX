import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const workspaceJsPath = new URL('../correction_workspace.js', import.meta.url);
const workspaceCssPath = new URL('../correction_workspace.css', import.meta.url);

function loadWorkspaceSources() {
  return {
    js: readFileSync(workspaceJsPath, 'utf8'),
    css: readFileSync(workspaceCssPath, 'utf8'),
  };
}

test('footer renders only media player and playback speed control without status text', () => {
  const { js } = loadWorkspaceSources();
  assert.match(js, /<footer class="cw-audio">/);
  assert.match(js, /id="cw-audio-rate"/);
  assert.doesNotMatch(js, /id="cw-global-status"/);
  assert.doesNotMatch(js, /Ursprungsdatei automatisch geladen\./);
  assert.doesNotMatch(js, /<label for="cw-audio-rate">Rate<\/label>/);
});

test('playback speed keeps selected value across re-render and is persisted', () => {
  const { js } = loadWorkspaceSources();
  assert.match(js, /PLAYBACK_RATE_STORAGE_KEY/);
  assert.match(js, /playbackRate:\s*loadPersistedPlaybackRate\(\)/);
  assert.match(js, /function loadPersistedPlaybackRate\(\)/);
  assert.match(js, /function persistPlaybackRate\(rate\)/);
  assert.match(js, /renderPlaybackRateOptions\(state\.playbackRate\)/);
  assert.match(js, /audioRateNode\.value = String\(normalizePlaybackRate\(state\.playbackRate\)\)/);
  assert.match(js, /state\.playbackRate = nextRate/);
  assert.match(js, /persistPlaybackRate\(nextRate\)/);
  assert.doesNotMatch(js, /<option value="1" selected>1\.0x<\/option>/);
});

test('status synchronization no longer writes into footer status node', () => {
  const { js } = loadWorkspaceSources();
  assert.doesNotMatch(js, /cw-global-status/);
});

test('footer media styles remove old hard caps and use full-width media container', () => {
  const { css } = loadWorkspaceSources();
  assert.doesNotMatch(css, /width:\s*min\(640px,\s*100%\);/);
  assert.doesNotMatch(css, /max-height:\s*180px;/);
  assert.match(css, /\.cw-media-shell\s*\{/);
  assert.match(css, /\.cw-media-slot\s*\{/);
  assert.match(css, /\.cw-media-slot audio\s*\{[\s\S]*width:\s*100%;/);
});

test('footer media viewport is compact (small-height strip) while keeping wide layout', () => {
  const { css, js } = loadWorkspaceSources();
  assert.doesNotMatch(css, /min-height:\s*clamp\(220px,\s*30vh,\s*360px\);/);
  assert.match(css, /\.cw-media-shell\s*\{[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s*auto;/);
  assert.match(css, /\.cw-media-slot\s*\{[\s\S]*height:\s*var\(--cw-media-strip-height,\s*108px\);/);
  assert.match(css, /\.cw-media-resize-handle\s*\{/);
  assert.match(js, /FOOTER_MEDIA_HEIGHT_STORAGE_KEY/);
  assert.match(js, /id="cw-media-resize-handle"/);
});

test('video in footer keeps full frame visible and scales by footer height', () => {
  const { css } = loadWorkspaceSources();
  assert.match(css, /\.cw-media-slot\s*\{[\s\S]*display:\s*flex;[\s\S]*justify-content:\s*center;[\s\S]*align-items:\s*center;/);
  assert.match(css, /\.cw-media-slot video\s*\{[\s\S]*width:\s*auto;[\s\S]*height:\s*100%;[\s\S]*max-width:\s*100%;[\s\S]*object-fit:\s*contain;/);
  assert.doesNotMatch(css, /\.cw-media-slot video\s*\{[\s\S]*object-fit:\s*cover;/);
});
