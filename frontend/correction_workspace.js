import {
  applyReplaceLiteral,
  applySpeakerReassign,
  findActiveSegmentIndex,
  formatTimestamp,
  normalizeSegments,
} from './correction_utils.js';
import { consumeCorrectionHandoff } from './correction_handoff.js';
import {
  buildSpeakerDisplayLabel,
  deriveMarkedTextRange,
  buildSpeakerOptionEntries,
  parseAutoSeekSelectionEnabled,
  parseSidebarSectionState,
  parseSidebarVisibility,
  resolveExportMenuState,
  resolveMarkedTextRange,
  resolveMediaSeekTime,
  resolveSpeakerTint,
  resolveSelectedSegmentId,
  shouldAutoSeek,
  serializeSidebarSectionState,
  SIDEBAR_SECTION_IDS,
} from './correction_workspace_viewmodel.js';
import {
  buildCorrectionExportBaseName,
  buildCorrectionMarkdownExport,
  buildCorrectionPlainTextExport,
  buildCorrectionWordDocument,
  buildSimplePdfFromPlainText,
} from './correction_workspace_export.js';

const THEME_STORAGE_KEY = 'evodox-theme';
const SIDEBAR_VISIBILITY_STORAGE_KEY = 'evodox-correction-sidebar-visible';
const SIDEBAR_SECTION_STATE_STORAGE_KEY = 'evodox-correction-sidebar-sections';
const AUTO_SEEK_SELECTION_STORAGE_KEY = 'evodox-correction-auto-seek-selection';
const EXPORT_MODE_STORAGE_KEY = 'evodox-correction-export-mode';

const state = {
  token: '',
  tenantId: '',
  jobId: '',
  sessionId: '',
  baseVersion: 1,
  workingVersion: 1,
  autosaveEnabled: false,
  reviewStatus: 'in_review',
  isFinal: false,
  speakerLabels: {},
  segments: [],
  operationLog: [],
  selectedSegmentId: null,
  activeSegmentIndex: -1,
  pendingSave: false,
  autosaveTimer: null,
  statusMessage: '',
  searchQuery: '',
  searchSpeaker: '',
  replaceQuery: '',
  replaceValue: '',
  hasUnsavedChanges: false,
  closePromptVisible: false,
  mediaSource: null,
  mediaLoadError: '',
  sidebarVisible: loadPersistedSidebarVisibility(),
  sidebarSectionsOpen: loadPersistedSidebarSectionState(),
  autoSeekSelectionEnabled: loadPersistedAutoSeekSelectionEnabled(),
  exportMode: loadPersistedExportMode(),
  exportMenuOpen: false,
  lastExportAction: '',
  selectedTextRange: null,
};

let exportMenuDismissHandler = null;
let exportMenuEscapeHandler = null;
let exportMenuFocusHandler = null;

function applyExportMenuEvent(event) {
  const nextState = resolveExportMenuState(
    {
      isOpen: state.exportMenuOpen,
      lastAction: state.lastExportAction,
    },
    event,
  );
  state.exportMenuOpen = Boolean(nextState.isOpen);
  state.lastExportAction = String(nextState.lastAction || '');
}

function teardownExportMenuListeners() {
  if (exportMenuDismissHandler) {
    document.removeEventListener('mousedown', exportMenuDismissHandler, true);
    exportMenuDismissHandler = null;
  }
  if (exportMenuEscapeHandler) {
    document.removeEventListener('keydown', exportMenuEscapeHandler, true);
    exportMenuEscapeHandler = null;
  }
  if (exportMenuFocusHandler) {
    document.removeEventListener('focusin', exportMenuFocusHandler, true);
    exportMenuFocusHandler = null;
  }
}

function syncExportMenuListeners() {
  teardownExportMenuListeners();
  if (!state.exportMenuOpen) return;
  exportMenuDismissHandler = (event) => {
    const menuNode = document.querySelector('[data-export-menu]');
    if (!menuNode || menuNode.contains(event.target)) return;
    applyExportMenuEvent({ type: 'outside' });
    render();
  };
  exportMenuEscapeHandler = (event) => {
    if (event.key !== 'Escape') return;
    applyExportMenuEvent({ type: 'escape' });
    render();
  };
  exportMenuFocusHandler = (event) => {
    const menuNode = document.querySelector('[data-export-menu]');
    if (!menuNode || menuNode.contains(event.target)) return;
    applyExportMenuEvent({ type: 'close' });
    render();
  };
  document.addEventListener('mousedown', exportMenuDismissHandler, true);
  document.addEventListener('keydown', exportMenuEscapeHandler, true);
  document.addEventListener('focusin', exportMenuFocusHandler, true);
}

function getBootstrap() {
  const params = new URLSearchParams(window.location.search);
  const handoff = String(params.get('handoff') || '').trim();
  if (!handoff) {
    return null;
  }
  const payload = consumeCorrectionHandoff(handoff);
  if (!payload) {
    return null;
  }
  return payload;
}

async function callApi(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${state.token}`,
      ...(options.headers ?? {}),
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const message = body?.detail?.error_code || body?.error_code || `http_${response.status}`;
    throw new Error(message);
  }
  if (response.status === 204) return {};
  return response.json();
}

function setStatus(message) {
  state.statusMessage = message;
  const sidebarNode = document.getElementById('cw-status-message');
  if (sidebarNode) sidebarNode.textContent = message;
  const footerNode = document.getElementById('cw-global-status');
  if (footerNode) footerNode.textContent = message;
}

function setTheme(theme) {
  const resolved = theme === 'dark' ? 'dark' : 'light';
  document.body.dataset.theme = resolved;
  try {
    localStorage.setItem(THEME_STORAGE_KEY, resolved);
  } catch {
    // ignore persistence errors
  }
}

function loadPersistedSidebarVisibility() {
  try {
    return parseSidebarVisibility(localStorage.getItem(SIDEBAR_VISIBILITY_STORAGE_KEY));
  } catch {
    return true;
  }
}

function persistSidebarVisibility(visible) {
  try {
    localStorage.setItem(SIDEBAR_VISIBILITY_STORAGE_KEY, visible ? '1' : '0');
  } catch {
    // ignore persistence errors
  }
}

function loadPersistedSidebarSectionState() {
  try {
    return parseSidebarSectionState(localStorage.getItem(SIDEBAR_SECTION_STATE_STORAGE_KEY));
  } catch {
    return parseSidebarSectionState(null);
  }
}

function persistSidebarSectionState() {
  try {
    localStorage.setItem(
      SIDEBAR_SECTION_STATE_STORAGE_KEY,
      serializeSidebarSectionState(state.sidebarSectionsOpen),
    );
  } catch {
    // ignore persistence errors
  }
}

function loadPersistedAutoSeekSelectionEnabled() {
  try {
    return parseAutoSeekSelectionEnabled(localStorage.getItem(AUTO_SEEK_SELECTION_STORAGE_KEY));
  } catch {
    return true;
  }
}

function persistAutoSeekSelectionEnabled(enabled) {
  try {
    localStorage.setItem(AUTO_SEEK_SELECTION_STORAGE_KEY, enabled ? '1' : '0');
  } catch {
    // ignore persistence errors
  }
}

function loadPersistedExportMode() {
  try {
    const mode = String(localStorage.getItem(EXPORT_MODE_STORAGE_KEY) || '').trim().toLowerCase();
    return mode === 'raw' ? 'raw' : 'compact';
  } catch {
    return 'compact';
  }
}

function persistExportMode(mode) {
  try {
    localStorage.setItem(EXPORT_MODE_STORAGE_KEY, mode === 'raw' ? 'raw' : 'compact');
  } catch {
    // ignore persistence errors
  }
}

function renderSidebarTreeSection({ id, title, body }) {
  const isOpen = state.sidebarSectionsOpen?.[id] !== false;
  return `
    <details class="cw-tree-node" data-tree-section="${escapeHtml(id)}" ${isOpen ? 'open' : ''}>
      <summary class="cw-tree-summary">
        <span class="cw-tree-caret" aria-hidden="true">&#9656;</span>
        <span>${escapeHtml(title)}</span>
      </summary>
      <div class="cw-tree-content">
        ${body}
      </div>
    </details>
  `;
}

function getSelectedSegment() {
  if (!state.selectedSegmentId) return null;
  return state.segments.find((segment) => String(segment.segment_id) === String(state.selectedSegmentId)) || null;
}

function clearMarkedTextSelection() {
  state.selectedTextRange = null;
}

function updateMarkedTextSelectionFromNode(textNode, segmentId) {
  if (!textNode) return null;
  const latestRange = deriveMarkedTextRange({
    segmentId,
    selectionStart: textNode.selectionStart,
    selectionEnd: textNode.selectionEnd,
    textLength: String(textNode.value ?? '').length,
  });
  const resolvedRange = resolveMarkedTextRange({
    previousRange: state.selectedTextRange,
    latestRange,
  });
  state.selectedTextRange = resolvedRange;
  return resolvedRange;
}

function seekMediaToSegmentStart(segmentId) {
  const mediaNode = getMediaElement();
  if (!mediaNode || !segmentId) return;
  const segment = state.segments.find((item) => String(item.segment_id) === String(segmentId));
  if (!segment) return;
  const seekTime = resolveMediaSeekTime(segment.start);
  if (seekTime == null) return;
  try {
    mediaNode.currentTime = seekTime;
  } catch {
    // Ignore browser seek restrictions
  }
}

function maybeAutoSeekToSegment({ previousSegmentId = '', nextSegmentId = '', source = '' }) {
  if (!state.autoSeekSelectionEnabled) return;
  if (!shouldAutoSeek({ previousSegmentId, nextSegmentId, source })) return;
  seekMediaToSegmentStart(nextSegmentId);
}

function triggerDownload({ filename, mimeType, payload }) {
  const blob = payload instanceof Blob
    ? payload
    : new Blob([payload], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function openPrintPreview({ title, text }) {
  const popup = window.open('', '_blank', 'noopener,noreferrer,width=980,height=760');
  if (!popup) {
    throw new Error('print_popup_blocked');
  }
  const safeTitle = escapeHtml(title || 'Korrektur-Export');
  const safeText = escapeHtml(String(text ?? ''));
  popup.document.open();
  popup.document.write(`<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <title>${safeTitle}</title>
  <style>
    body { font-family: "Segoe UI", "Noto Sans", sans-serif; margin: 28px; color: #1f1f1b; line-height: 1.45; }
    h1 { font-size: 20px; margin: 0 0 16px; }
    pre { white-space: pre-wrap; word-break: break-word; font: 13px/1.45 "Consolas", "Courier New", monospace; }
  </style>
</head>
<body>
  <h1>${safeTitle}</h1>
  <pre>${safeText}</pre>
</body>
</html>`);
  popup.document.close();
  popup.focus();
  popup.print();
}

function exportCurrentTranscript(format) {
  try {
    const createdAt = new Date();
    const segments = collectSegmentsFromDom();
    const baseName = buildCorrectionExportBaseName({ jobId: state.jobId, createdAt });
    if (format === 'md') {
      const markdown = buildCorrectionMarkdownExport({
        jobId: state.jobId,
        sessionId: state.sessionId,
        baseVersion: state.baseVersion,
        workingVersion: state.workingVersion,
        reviewStatus: state.reviewStatus,
        isFinal: state.isFinal,
        mode: state.exportMode,
        segments,
        speakerLabels: state.speakerLabels,
        createdAt,
      });
      triggerDownload({
        filename: `${baseName}.md`,
        mimeType: 'text/markdown;charset=utf-8',
        payload: markdown,
      });
      setStatus(`Markdown-Export erstellt (${state.exportMode})`);
      return;
    }

    const text = buildCorrectionPlainTextExport({
      jobId: state.jobId,
      sessionId: state.sessionId,
      baseVersion: state.baseVersion,
      workingVersion: state.workingVersion,
      reviewStatus: state.reviewStatus,
      isFinal: state.isFinal,
      mode: state.exportMode,
      createdAt,
      segments,
      speakerLabels: state.speakerLabels,
    });

    if (format === 'pdf') {
      const pdfBytes = buildSimplePdfFromPlainText(text);
      triggerDownload({
        filename: `${baseName}.pdf`,
        mimeType: 'application/pdf',
        payload: pdfBytes,
      });
      setStatus(`PDF-Export erstellt (${state.exportMode})`);
      return;
    }

    if (format === 'print') {
      openPrintPreview({
        title: `Korrektur-Export Job ${state.jobId} (${state.exportMode})`,
        text,
      });
      setStatus(`Druckansicht geoeffnet (${state.exportMode})`);
      return;
    }

    if (format === 'word') {
      const word = buildCorrectionWordDocument({
        title: `Korrektur-Export Job ${state.jobId} (${state.exportMode})`,
        text,
      });
      triggerDownload({
        filename: `${baseName}.doc`,
        mimeType: 'application/msword',
        payload: word,
      });
      setStatus(`Word-Export erstellt (${state.exportMode})`);
    }
  } catch (error) {
    setStatus(`Export fehlgeschlagen: ${error.message}`);
  }
}

function syncSpeakerReassignMeta() {
  const blockInfoNode = document.getElementById('cw-selected-block-info');
  if (blockInfoNode) {
    const selected = getSelectedSegment();
    if (!selected) {
      blockInfoNode.textContent = 'Kein Block ausgewaehlt.';
    } else {
      const speakerLabel = buildSpeakerDisplayLabel({
        speakerKey: selected.speaker,
        speakerLabels: state.speakerLabels,
      });
      blockInfoNode.textContent = `${speakerLabel} | ${formatTimestamp(selected.start)} - ${formatTimestamp(selected.end)}`;
    }
  }

  const markInfoNode = document.getElementById('cw-selected-text-info');
  if (markInfoNode) {
    const range = state.selectedTextRange;
    const hasRange = range && range.length > 0;
    if (!hasRange) {
      markInfoNode.textContent = 'Bitte Text im ausgewaehlten Block markieren.';
    } else if (String(range.segmentId) !== String(state.selectedSegmentId)) {
      markInfoNode.textContent = `Markierung aktiv in anderem Block (${range.length} Zeichen).`;
    } else {
      markInfoNode.textContent = `Markiert: Zeichen ${range.startChar + 1}-${range.endChar} (${range.length} Zeichen)`;
    }
  }
}

function syncSelectedBlockHighlight(editor) {
  if (!editor) return;
  editor.querySelectorAll('.cw-block.selected').forEach((node) => node.classList.remove('selected'));
  if (!state.selectedSegmentId) return;
  const active = editor.querySelector(`[data-segment-id="${CSS.escape(String(state.selectedSegmentId))}"]`);
  if (active) active.classList.add('selected');
}

function autoResizeTextarea(node) {
  if (!node) return;
  node.style.height = 'auto';
  node.style.height = `${Math.max(72, node.scrollHeight)}px`;
}

function syncActiveBlockHighlight(editor) {
  if (!editor) return;
  editor.querySelectorAll('.cw-block.active').forEach((node) => node.classList.remove('active'));
  if (state.activeSegmentIndex < 0) return;
  const segment = state.segments[state.activeSegmentIndex];
  if (!segment) return;
  const active = editor.querySelector(`[data-segment-id="${CSS.escape(String(segment.segment_id))}"]`);
  if (active) active.classList.add('active');
}

function activateSegmentForUi(segmentId, editor) {
  const nextIndex = state.segments.findIndex((segment) => String(segment.segment_id) === String(segmentId));
  if (nextIndex < 0) return;
  state.activeSegmentIndex = nextIndex;
  syncActiveBlockHighlight(editor);
}

function captureEditorContext(editor) {
  if (!editor) return null;
  return {
    scrollTop: editor.scrollTop,
    selectedSegmentId: String(state.selectedSegmentId || ''),
  };
}

function resolveContextSegmentId(preferredSegmentId) {
  return resolveSelectedSegmentId({
    previousSegmentId: preferredSegmentId,
    segments: state.segments,
  });
}

function restoreEditorContext(editor, context) {
  if (!editor || !context) return;
  if (Number.isFinite(context.scrollTop)) {
    editor.scrollTop = Math.max(0, Number(context.scrollTop));
  }
  const resolvedSegmentId = resolveContextSegmentId(context.selectedSegmentId);
  if (!resolvedSegmentId) return;
  state.selectedSegmentId = resolvedSegmentId;
  syncSelectedBlockHighlight(editor);
  syncSpeakerReassignMeta();
  const node = editor.querySelector(`[data-segment-id="${CSS.escape(String(resolvedSegmentId))}"]`);
  if (!node) return;
  const editorRect = editor.getBoundingClientRect();
  const nodeRect = node.getBoundingClientRect();
  if (nodeRect.top < editorRect.top || nodeRect.bottom > editorRect.bottom) {
    node.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }
}

function markUnsavedChanges() {
  state.hasUnsavedChanges = true;
}

function clearUnsavedChanges() {
  state.hasUnsavedChanges = false;
}

function getMediaElement() {
  return document.querySelector('[data-media-player]');
}

function captureMediaPlaybackState() {
  const media = getMediaElement();
  if (!media) return null;
  const src = String(media.currentSrc || media.getAttribute('src') || '').trim();
  const currentTime = Number(media.currentTime);
  const playbackRate = Number(media.playbackRate);
  const volume = Number(media.volume);
  return {
    src,
    currentTime: Number.isFinite(currentTime) ? Math.max(0, currentTime) : 0,
    playbackRate: Number.isFinite(playbackRate) && playbackRate > 0 ? playbackRate : 1,
    volume: Number.isFinite(volume) ? Math.min(1, Math.max(0, volume)) : 1,
    muted: Boolean(media.muted),
    paused: Boolean(media.paused),
  };
}

function restoreMediaPlaybackState(snapshot) {
  if (!snapshot) return;
  const media = getMediaElement();
  if (!media) return;
  const activeSrc = String(media.currentSrc || media.getAttribute('src') || '').trim();
  if (snapshot.src && activeSrc && snapshot.src !== activeSrc) return;

  media.playbackRate = snapshot.playbackRate;
  media.volume = snapshot.volume;
  media.muted = snapshot.muted;

  const applyTime = () => {
    const duration = Number(media.duration);
    const maxTime = Number.isFinite(duration) && duration > 0 ? duration : snapshot.currentTime;
    const safeTime = Math.min(snapshot.currentTime, maxTime);
    if (Number.isFinite(safeTime) && safeTime >= 0) {
      try {
        media.currentTime = safeTime;
      } catch {
        // Ignore browser seek restrictions.
      }
    }
    if (!snapshot.paused) {
      void media.play().catch(() => {
        // Autoplay policies can block this; keep UI responsive.
      });
    }
  };

  if (media.readyState >= 1) {
    applyTime();
    return;
  }
  media.addEventListener('loadedmetadata', applyTime, { once: true });
}

function getSpeakerOptions() {
  return buildSpeakerOptionEntries({
    segments: state.segments,
    speakerLabels: state.speakerLabels,
  });
}

function renderOperationLog() {
  if (!Array.isArray(state.operationLog) || state.operationLog.length === 0) {
    return '<div class="cw-log">Noch keine Aenderungen.</div>';
  }
  const lines = state.operationLog.map((entry, index) => `<div>${index + 1}. ${escapeHtml(JSON.stringify(entry))}</div>`).join('');
  return `<div class="cw-log">${lines}</div>`;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function renderEditorBlocks() {
  return state.segments.map((segment, index) => {
    const activeClass = index === state.activeSegmentIndex ? 'active' : '';
    const selectedClass = String(segment.segment_id) === String(state.selectedSegmentId) ? 'selected' : '';
    const speakerLabel = buildSpeakerDisplayLabel({
      speakerKey: segment.speaker,
      speakerLabels: state.speakerLabels,
    });
    const tint = resolveSpeakerTint({ speakerKey: segment.speaker });
    const tintStyle = [
      `--cw-speaker-bg:${tint.background}`,
      `--cw-speaker-border:${tint.border}`,
      `--cw-speaker-active:${tint.active}`,
      `--cw-speaker-focus:${tint.focus}`,
    ].join(';');
    return `
      <article
        class="cw-block ${activeClass} ${selectedClass}"
        data-segment-id="${escapeHtml(segment.segment_id)}"
        style="${escapeHtml(tintStyle)}"
      >
        <header class="cw-block-header">
          <strong class="cw-block-speaker">${escapeHtml(speakerLabel)}</strong>
          <button
            type="button"
            class="cw-block-jump"
            data-segment-jump="${escapeHtml(segment.segment_id)}"
            aria-label="Zum Start dieses Blocks springen"
            title="Zum Start dieses Blocks springen"
          >Jump</button>
          <small class="cw-block-time">${escapeHtml(formatTimestamp(segment.start))} - ${escapeHtml(formatTimestamp(segment.end))}</small>
        </header>
        <textarea data-text-input="${escapeHtml(segment.segment_id)}">${escapeHtml(segment.text)}</textarea>
      </article>
    `;
  }).join('');
}

function render() {
  const app = document.getElementById('correction-app');
  if (!app) return;
  const mediaSnapshot = captureMediaPlaybackState();
  const speakerOptions = getSpeakerOptions()
    .map((entry) => `<option value="${escapeHtml(entry.key)}">${escapeHtml(entry.label)}</option>`)
    .join('');
  const theme = document.body.dataset.theme === 'dark' ? 'dark' : 'light';
  const mediaNode = renderMediaNode();
  const sidebarToggleLabel = state.sidebarVisible ? 'Sidebar aktiv' : 'Sidebar aus';
  const themeToggleLabel = theme === 'dark' ? 'Dark aktiv' : 'Light aktiv';
  const layoutClass = state.sidebarVisible ? 'cw-layout' : 'cw-layout cw-layout--sidebar-hidden';
  const sidebarStatusBody = `
    <div class="cw-row">
      <label for="cw-review-status">Pruefstatus</label>
      <input id="cw-review-status" value="${escapeHtml(state.reviewStatus)}" />
    </div>
    <div class="cw-row">
      <label>
        <input id="cw-final-toggle" type="checkbox" ${state.isFinal ? 'checked' : ''} /> Final
      </label>
    </div>
    <button id="cw-status-save" class="primary">Status speichern</button>
  `;
  const sidebarSearchBody = `
    <input id="cw-search-query" placeholder="Suche" value="${escapeHtml(state.searchQuery)}" />
    <select id="cw-search-speaker">
      <option value="">Alle Sprecher</option>
      ${speakerOptions}
    </select>
    <input id="cw-replace-query" placeholder="Ersetze" value="${escapeHtml(state.replaceQuery)}" />
    <input id="cw-replace-value" placeholder="Durch" value="${escapeHtml(state.replaceValue)}" />
    <div class="cw-row">
      <button id="cw-replace-one">Ersetze eins</button>
      <button id="cw-replace-all" class="primary">Ersetze alle</button>
    </div>
  `;
  const sidebarReassignBody = `
    <p id="cw-selected-block-info" class="cw-status">Kein Block ausgewaehlt.</p>
    <select id="cw-reassign-speaker">
      ${speakerOptions}
    </select>
    <p id="cw-selected-text-info" class="cw-status">Bitte Text im ausgewaehlten Block markieren.</p>
    <button id="cw-reassign-apply">Markierten Text Sprecher zuweisen</button>
  `;
  const sidebarChangeLogBody = renderOperationLog();

  app.innerHTML = `
    <section class="cw-root">
      <header class="cw-topbar">
        <section class="cw-topbar-actions" aria-label="Aktionen">
          <div class="cw-toolbar-main">
            <button
              id="cw-save"
              class="primary cw-icon-only"
              type="button"
              aria-label="Speichern"
              title="Speichern"
            >
              <span class="cw-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" focusable="false">
                  <path d="M5 3h11l3 3v15H5V3Zm2 2v5h8V5H7Zm0 14h10v-7H7v7Z"/>
                </svg>
              </span>
            </button>
            <button id="cw-commit" class="primary" type="button" title="Version committen">Commit</button>
            <button
              id="cw-print"
              class="cw-icon-only"
              type="button"
              aria-label="Drucken"
              title="Drucken"
            >
              <span class="cw-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" focusable="false">
                  <path d="M6 9V3h12v6h1a3 3 0 0 1 3 3v5h-4v4H6v-4H2v-5a3 3 0 0 1 3-3h1Zm2-4v4h8V5H8Zm8 12H8v2h8v-2Zm2-2h2v-3a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v3h2v-2h12v2Z"/>
                </svg>
              </span>
            </button>
            <button
              id="cw-undo"
              class="cw-icon-only"
              type="button"
              aria-label="Rueckgaengig"
              title="Rueckgaengig (Undo)"
            >
              <span class="cw-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" focusable="false">
                  <path d="M12.5 8H7.83l1.58-1.59L8 5 4 9l4 4 1.41-1.41L7.83 10h4.67A3.5 3.5 0 1 1 12.5 17H8v2h4.5a5.5 5.5 0 1 0 0-11Z"/>
                </svg>
              </span>
            </button>
            <button
              id="cw-redo"
              class="cw-icon-only"
              type="button"
              aria-label="Wiederholen"
              title="Wiederholen (Redo)"
            >
              <span class="cw-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" focusable="false">
                  <path d="M11.5 8h4.67l-1.58-1.59L16 5l4 4-4 4-1.41-1.41L16.17 10H11.5a3.5 3.5 0 1 0 0 7H16v2h-4.5a5.5 5.5 0 1 1 0-11Z"/>
                </svg>
              </span>
            </button>
            <button id="cw-discard" class="danger" type="button" title="Ungespeicherte Aenderungen verwerfen">Verwerfen</button>
            <div class="cw-export-menu ${state.exportMenuOpen ? 'open' : ''}" data-export-menu>
              <button
                id="cw-export-menu-toggle"
                class="cw-icon-only"
                type="button"
                aria-expanded="${state.exportMenuOpen ? 'true' : 'false'}"
                aria-controls="cw-export-menu-list"
                aria-haspopup="menu"
                aria-label="Export-Menue"
                title="Export-Menue"
              >
                <span class="cw-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" focusable="false">
                    <path d="M12 3a1 1 0 0 1 1 1v9.59l2.3-2.29 1.4 1.4-4.7 4.7-4.7-4.7 1.4-1.4L11 13.59V4a1 1 0 0 1 1-1ZM5 19h14v2H5v-2Z"/>
                  </svg>
                </span>
              </button>
              <div id="cw-export-menu-list" class="cw-export-menu-list" role="menu" aria-label="Export und Drucken">
                <div class="cw-export-mode-group" role="group" aria-label="Exportmodus">
                  <button
                    id="cw-export-mode-compact"
                    type="button"
                    class="cw-segment ${state.exportMode === 'compact' ? 'active' : ''}"
                    aria-pressed="${state.exportMode === 'compact' ? 'true' : 'false'}"
                  >Kompakt</button>
                  <button
                    id="cw-export-mode-raw"
                    type="button"
                    class="cw-segment ${state.exportMode === 'raw' ? 'active' : ''}"
                    aria-pressed="${state.exportMode === 'raw' ? 'true' : 'false'}"
                  >Rohdaten</button>
                </div>
                <button id="cw-export-print" role="menuitem" type="button">Drucken</button>
                <button id="cw-export-md" role="menuitem" type="button">Markdown</button>
                <button id="cw-export-pdf" role="menuitem" type="button">PDF</button>
                <button id="cw-export-word" role="menuitem" type="button">Word</button>
              </div>
            </div>
          </div>
          <div class="cw-toolbar-state">
            <button
              id="cw-autosave"
              class="cw-pill-toggle cw-pill-toggle--binary ${state.autosaveEnabled ? 'is-on' : 'is-off'}"
              type="button"
              aria-pressed="${state.autosaveEnabled ? 'true' : 'false'}"
              title="Autosave ${state.autosaveEnabled ? 'aktiv' : 'inaktiv'}"
            >Autosave</button>
            <button
              id="cw-auto-seek-selection"
              class="cw-pill-toggle cw-pill-toggle--binary ${state.autoSeekSelectionEnabled ? 'is-on' : 'is-off'}"
              type="button"
              aria-pressed="${state.autoSeekSelectionEnabled ? 'true' : 'false'}"
              title="Auto-Sprung ${state.autoSeekSelectionEnabled ? 'aktiv' : 'inaktiv'}"
            >Auto-Sprung</button>
            <button
              id="cw-sidebar-toggle"
              class="cw-pill-toggle ${state.sidebarVisible ? 'active' : ''}"
              type="button"
              aria-pressed="${state.sidebarVisible ? 'true' : 'false'}"
              title="${sidebarToggleLabel}"
            >Sidebar</button>
            <button
              id="cw-theme-toggle"
              class="cw-pill-toggle ${theme === 'dark' ? 'active' : ''}"
              type="button"
              aria-pressed="${theme === 'dark' ? 'true' : 'false'}"
              title="${themeToggleLabel}"
            >Theme</button>
            <button
              id="cw-close"
              class="cw-icon-only"
              type="button"
              aria-label="Fenster schliessen"
              title="Fenster schliessen"
            >
              <span class="cw-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" focusable="false">
                  <path d="M18.3 5.7 12 12l6.3 6.3-1.4 1.4L10.6 13.4 4.3 19.7 2.9 18.3 9.2 12 2.9 5.7 4.3 4.3l6.3 6.3 6.3-6.3 1.4 1.4Z"/>
                </svg>
              </span>
            </button>
          </div>
        </section>
        <section class="cw-topbar-status" aria-label="Session-Status">
          <div class="cw-topbar-meta-badges">
            <span class="badge">Job ${escapeHtml(state.jobId)}</span>
            <span class="badge">B${state.baseVersion}</span>
            <span class="badge">W${state.workingVersion}</span>
            <span class="badge">${escapeHtml(state.reviewStatus)}</span>
            <span class="badge">Final ${state.isFinal ? 'Ja' : 'Nein'}</span>
          </div>
        </section>
      </header>
      <section class="${layoutClass}">
        <section class="cw-editor" id="cw-editor">${renderEditorBlocks()}</section>
        ${state.sidebarVisible ? `
        <aside class="cw-sidebar">
          <section class="cw-sidebar-tree" role="tree" aria-label="Korrekturwerkzeuge">
            ${renderSidebarTreeSection({ id: SIDEBAR_SECTION_IDS[0], title: 'Status', body: sidebarStatusBody })}
            ${renderSidebarTreeSection({ id: SIDEBAR_SECTION_IDS[1], title: 'Suche & Ersetzen', body: sidebarSearchBody })}
            ${renderSidebarTreeSection({ id: SIDEBAR_SECTION_IDS[2], title: 'Sprecherumteilung', body: sidebarReassignBody })}
            ${renderSidebarTreeSection({ id: SIDEBAR_SECTION_IDS[3], title: 'Aenderungslog', body: sidebarChangeLogBody })}
          </section>
          <p id="cw-status-message" class="cw-status cw-sidebar-status">${escapeHtml(state.statusMessage)}</p>
        </aside>
        ` : ''}
      </section>
      <footer class="cw-audio">
        ${mediaNode}
        <label for="cw-audio-rate">Rate</label>
        <select id="cw-audio-rate">
          <option value="0.75">0.75x</option>
          <option value="1" selected>1.0x</option>
          <option value="1.25">1.25x</option>
          <option value="1.5">1.5x</option>
          <option value="2">2.0x</option>
        </select>
        <span class="cw-status">${escapeHtml(state.mediaLoadError || 'Ursprungsdatei automatisch geladen.')}</span>
        <span id="cw-global-status" class="cw-status">${escapeHtml(state.statusMessage)}</span>
      </footer>
      ${state.closePromptVisible ? `
      <section class="cw-modal-backdrop" role="dialog" aria-modal="true" aria-label="Ungespeicherte Aenderungen">
        <div class="cw-modal">
          <h3>Ungespeicherte Aenderungen</h3>
          <p>Moechtest du vor dem Schliessen speichern oder verwerfen?</p>
          <div class="cw-row">
            <button id="cw-close-save" class="primary">Speichern</button>
            <button id="cw-close-discard" class="danger">Verwerfen</button>
            <button id="cw-close-cancel">Abbrechen</button>
          </div>
        </div>
      </section>
      ` : ''}
    </section>
  `;

  const speakerFilterNode = document.getElementById('cw-search-speaker');
  if (speakerFilterNode) speakerFilterNode.value = state.searchSpeaker;

  bindInteractions();
  restoreMediaPlaybackState(mediaSnapshot);
  syncExportMenuListeners();
  syncSpeakerReassignMeta();
}

function renderMediaNode() {
  if (!state.mediaSource?.media_url) {
    return '<div class="cw-status">Keine Medienquelle verfuegbar.</div>';
  }
  const url = escapeHtml(state.mediaSource.media_url);
  const isVideo = String(state.mediaSource.content_type || '').startsWith('video/');
  if (isVideo) {
    return `<video id="cw-media" data-media-player controls preload="metadata" src="${url}"></video>`;
  }
  return `<audio id="cw-media" data-media-player controls preload="metadata" src="${url}"></audio>`;
}

function collectSegmentsFromDom() {
  const updated = normalizeSegments(state.segments);
  updated.forEach((segment) => {
    const textNode = document.querySelector(`[data-text-input="${CSS.escape(String(segment.segment_id))}"]`);
    if (textNode) segment.text = String(textNode.value ?? '');
  });
  return updated;
}

async function applySegments(segments, message = 'Aenderungen gespeichert', options = {}) {
  const editor = document.getElementById('cw-editor');
  const fallbackContext = captureEditorContext(editor);
  const context = options?.editorContext || fallbackContext;
  const payload = {
    operations: [
      {
        type: 'set_segments',
        segments,
      },
    ],
  };
  if (state.autosaveEnabled) payload.autosave_enabled = true;
  const result = await callApi(`/api/v1/jobs/${state.jobId}/transcript/correction-sessions/${state.sessionId}/operations`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  patchStateFromSession(result);
  clearUnsavedChanges();
  setStatus(message);
  render();
  const renderedEditor = document.getElementById('cw-editor');
  restoreEditorContext(renderedEditor, context);
}

function scheduleAutosave() {
  state.pendingSave = true;
  markUnsavedChanges();
  if (!state.autosaveEnabled) return;
  if (state.autosaveTimer) clearTimeout(state.autosaveTimer);
  state.autosaveTimer = setTimeout(async () => {
    state.autosaveTimer = null;
    if (!state.pendingSave) return;
    state.pendingSave = false;
    try {
      const segments = collectSegmentsFromDom();
      await applySegments(segments, 'Autosave-Draft aktualisiert');
    } catch (error) {
      setStatus(`Autosave fehlgeschlagen: ${error.message}`);
    }
  }, 1200);
}

function patchStateFromSession(payload) {
  state.sessionId = payload.session_id;
  state.baseVersion = Number(payload.base_version ?? state.baseVersion);
  state.workingVersion = Number(payload.working_version ?? state.workingVersion);
  state.autosaveEnabled = Boolean(payload.autosave_enabled);
  state.speakerLabels = payload.speaker_labels ?? {};
  state.segments = normalizeSegments(payload.segments ?? []);
  state.operationLog = Array.isArray(payload.operation_log) ? payload.operation_log : [];
  state.reviewStatus = String(payload.review_status ?? state.reviewStatus);
  state.isFinal = Boolean(payload.is_final ?? state.isFinal);
  state.selectedSegmentId = resolveContextSegmentId(state.selectedSegmentId);
  if (state.selectedTextRange && !state.segments.some((segment) => String(segment.segment_id) === String(state.selectedTextRange.segmentId))) {
    clearMarkedTextSelection();
  }
}

function bindInteractions() {
  const editor = document.getElementById('cw-editor');
  if (editor) {
    editor.querySelectorAll('[data-text-input]').forEach((node) => {
      autoResizeTextarea(node);
      const syncNodeSelection = () => {
        const segmentId = String(node.getAttribute('data-text-input') || '');
        if (!segmentId) return;
        state.selectedSegmentId = segmentId;
        syncSelectedBlockHighlight(editor);
        updateMarkedTextSelectionFromNode(node, segmentId);
        syncSpeakerReassignMeta();
      };
      node.addEventListener('input', () => {
        autoResizeTextarea(node);
        scheduleAutosave();
        syncNodeSelection();
      });
      node.addEventListener('select', syncNodeSelection);
      node.addEventListener('mouseup', syncNodeSelection);
      node.addEventListener('keyup', syncNodeSelection);
      node.addEventListener('focus', () => {
        const segmentId = String(node.getAttribute('data-text-input') || '');
        if (!segmentId) return;
        const previousSegmentId = String(state.selectedSegmentId || '');
        state.selectedSegmentId = segmentId;
        syncSelectedBlockHighlight(editor);
        activateSegmentForUi(segmentId, editor);
        maybeAutoSeekToSegment({ previousSegmentId, nextSegmentId: segmentId, source: 'text_focus' });
        syncSpeakerReassignMeta();
      });
    });
    editor.querySelectorAll('.cw-block').forEach((blockNode) => {
      blockNode.addEventListener('click', () => {
        const nextSegmentId = String(blockNode.dataset.segmentId || '');
        const previousSegmentId = String(state.selectedSegmentId || '');
        state.selectedSegmentId = nextSegmentId;
        syncSelectedBlockHighlight(editor);
        activateSegmentForUi(nextSegmentId, editor);
        maybeAutoSeekToSegment({ previousSegmentId, nextSegmentId, source: 'block_click' });
        syncSpeakerReassignMeta();
      });
    });
    editor.querySelectorAll('[data-segment-jump]').forEach((jumpNode) => {
      jumpNode.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        const segmentId = String(jumpNode.getAttribute('data-segment-jump') || '');
        if (!segmentId) return;
        state.selectedSegmentId = segmentId;
        syncSelectedBlockHighlight(editor);
        activateSegmentForUi(segmentId, editor);
        seekMediaToSegmentStart(segmentId);
        syncSpeakerReassignMeta();
      });
    });
  }

  const sidebarToggle = document.getElementById('cw-sidebar-toggle');
  if (sidebarToggle) {
    sidebarToggle.onclick = () => {
      state.sidebarVisible = !state.sidebarVisible;
      persistSidebarVisibility(state.sidebarVisible);
      render();
    };
  }

  document.querySelectorAll('[data-tree-section]').forEach((node) => {
    node.addEventListener('toggle', () => {
      const sectionId = String(node.getAttribute('data-tree-section') || '');
      if (!SIDEBAR_SECTION_IDS.includes(sectionId)) return;
      state.sidebarSectionsOpen = {
        ...state.sidebarSectionsOpen,
        [sectionId]: Boolean(node.open),
      };
      persistSidebarSectionState();
    });
  });

  const autosaveNode = document.getElementById('cw-autosave');
  if (autosaveNode) {
    autosaveNode.onclick = async () => {
      const previousAutosaveEnabled = state.autosaveEnabled;
      state.autosaveEnabled = !state.autosaveEnabled;
      try {
        const result = await callApi(`/api/v1/jobs/${state.jobId}/transcript/correction-sessions/${state.sessionId}`, {
          method: 'PATCH',
          body: JSON.stringify({ autosave_enabled: state.autosaveEnabled }),
        });
        patchStateFromSession(result);
        setStatus('Autosave aktualisiert');
        render();
      } catch (error) {
        state.autosaveEnabled = previousAutosaveEnabled;
        setStatus(`Autosave konnte nicht gespeichert werden: ${error.message}`);
        render();
      }
    };
  }

  const autoSeekSelectionNode = document.getElementById('cw-auto-seek-selection');
  if (autoSeekSelectionNode) {
    autoSeekSelectionNode.onclick = () => {
      state.autoSeekSelectionEnabled = !state.autoSeekSelectionEnabled;
      persistAutoSeekSelectionEnabled(state.autoSeekSelectionEnabled);
      setStatus(state.autoSeekSelectionEnabled
        ? 'Auto-Sprung Media aktiviert'
        : 'Auto-Sprung Media deaktiviert');
      render();
    };
  }

  const saveButton = document.getElementById('cw-save');
  if (saveButton) {
    saveButton.onclick = async () => {
      try {
        const segments = collectSegmentsFromDom();
        await applySegments(segments, 'Draft-Stand gespeichert');
      } catch (error) {
        setStatus(`Speichern fehlgeschlagen: ${error.message}`);
      }
    };
  }

  const exportMenuToggle = document.getElementById('cw-export-menu-toggle');
  if (exportMenuToggle) {
    exportMenuToggle.onclick = () => {
      applyExportMenuEvent({ type: 'toggle' });
      render();
    };
  }

  const applyExportMode = (mode) => {
    state.exportMode = mode === 'raw' ? 'raw' : 'compact';
    persistExportMode(state.exportMode);
    setStatus(`Exportmodus: ${state.exportMode === 'raw' ? 'Rohdaten' : 'Kompakt'}`);
    render();
  };

  const exportModeCompactButton = document.getElementById('cw-export-mode-compact');
  if (exportModeCompactButton) {
    exportModeCompactButton.onclick = () => applyExportMode('compact');
  }

  const exportModeRawButton = document.getElementById('cw-export-mode-raw');
  if (exportModeRawButton) {
    exportModeRawButton.onclick = () => applyExportMode('raw');
  }

  const runExportAction = (action) => {
    applyExportMenuEvent({ type: 'select', action });
    exportCurrentTranscript(action);
    render();
  };

  const quickPrintButton = document.getElementById('cw-print');
  if (quickPrintButton) {
    quickPrintButton.onclick = () => {
      exportCurrentTranscript('print');
    };
  }

  const exportPrintButton = document.getElementById('cw-export-print');
  if (exportPrintButton) {
    exportPrintButton.onclick = () => runExportAction('print');
  }

  const exportMarkdownButton = document.getElementById('cw-export-md');
  if (exportMarkdownButton) {
    exportMarkdownButton.onclick = () => runExportAction('md');
  }

  const exportPdfButton = document.getElementById('cw-export-pdf');
  if (exportPdfButton) {
    exportPdfButton.onclick = () => runExportAction('pdf');
  }

  const exportWordButton = document.getElementById('cw-export-word');
  if (exportWordButton) {
    exportWordButton.onclick = () => runExportAction('word');
  }

  const discardButton = document.getElementById('cw-discard');
  if (discardButton) {
    discardButton.onclick = async () => {
      try {
        const result = await callApi(`/api/v1/jobs/${state.jobId}/transcript/correction-sessions/${state.sessionId}/discard`, {
          method: 'POST',
        });
        patchStateFromSession(result);
        clearUnsavedChanges();
        setStatus('Ungespeicherte Aenderungen verworfen');
        render();
      } catch (error) {
        setStatus(`Verwerfen fehlgeschlagen: ${error.message}`);
      }
    };
  }

  const undoButton = document.getElementById('cw-undo');
  if (undoButton) {
    undoButton.onclick = async () => {
      try {
        const result = await callApi(`/api/v1/jobs/${state.jobId}/transcript/correction-sessions/${state.sessionId}/undo`, {
          method: 'POST',
        });
        patchStateFromSession(result);
        clearUnsavedChanges();
        setStatus('Letzte Aktion rueckgaengig');
        render();
      } catch (error) {
        setStatus(`Undo fehlgeschlagen: ${error.message}`);
      }
    };
  }

  const redoButton = document.getElementById('cw-redo');
  if (redoButton) {
    redoButton.onclick = async () => {
      try {
        const result = await callApi(`/api/v1/jobs/${state.jobId}/transcript/correction-sessions/${state.sessionId}/redo`, {
          method: 'POST',
        });
        patchStateFromSession(result);
        clearUnsavedChanges();
        setStatus('Aktion wiederhergestellt');
        render();
      } catch (error) {
        setStatus(`Redo fehlgeschlagen: ${error.message}`);
      }
    };
  }

  const statusButton = document.getElementById('cw-status-save');
  if (statusButton) {
    statusButton.onclick = async () => {
      const reviewStatusNode = document.getElementById('cw-review-status');
      const finalToggleNode = document.getElementById('cw-final-toggle');
      const reviewStatus = String(reviewStatusNode?.value ?? '').trim();
      const isFinal = Boolean(finalToggleNode?.checked);
      try {
        const result = await callApi(`/api/v1/jobs/${state.jobId}/transcript/status`, {
          method: 'PATCH',
          body: JSON.stringify({ review_status: reviewStatus, is_final: isFinal }),
        });
        state.reviewStatus = String(result.review_status ?? state.reviewStatus);
        state.isFinal = Boolean(result.is_final ?? state.isFinal);
        setStatus('Status gespeichert');
        render();
      } catch (error) {
        setStatus(`Status konnte nicht gespeichert werden: ${error.message}`);
      }
    };
  }

  const replaceOneButton = document.getElementById('cw-replace-one');
  const replaceAllButton = document.getElementById('cw-replace-all');
  const searchNode = document.getElementById('cw-search-query');
  const speakerNode = document.getElementById('cw-search-speaker');
  const replaceQueryNode = document.getElementById('cw-replace-query');
  const replaceValueNode = document.getElementById('cw-replace-value');

  if (searchNode) searchNode.oninput = () => { state.searchQuery = String(searchNode.value ?? ''); };
  if (speakerNode) speakerNode.onchange = () => { state.searchSpeaker = String(speakerNode.value ?? ''); };
  if (replaceQueryNode) replaceQueryNode.oninput = () => { state.replaceQuery = String(replaceQueryNode.value ?? ''); };
  if (replaceValueNode) replaceValueNode.oninput = () => { state.replaceValue = String(replaceValueNode.value ?? ''); };

  async function runReplace(replaceAll) {
    const result = applyReplaceLiteral({
      segments: collectSegmentsFromDom(),
      query: state.replaceQuery,
      replace: state.replaceValue,
      speaker: state.searchSpeaker || null,
      replaceAll,
    });
    if (!result.replacements) {
      setStatus('Keine Treffer fuer Ersetzen gefunden');
      return;
    }
    try {
      await applySegments(result.segments, `${result.replacements} Treffer ersetzt`);
    } catch (error) {
      setStatus(`Ersetzen fehlgeschlagen: ${error.message}`);
    }
  }

  if (replaceOneButton) replaceOneButton.onclick = () => { void runReplace(false); };
  if (replaceAllButton) replaceAllButton.onclick = () => { void runReplace(true); };

  const reassignButton = document.getElementById('cw-reassign-apply');
  if (reassignButton) {
    reassignButton.onclick = async () => {
      const speakerSelectNode = document.getElementById('cw-reassign-speaker');
      const segmentId = String(state.selectedSegmentId || '');
      const speaker = String(speakerSelectNode?.value ?? '');
      if (!segmentId) {
        setStatus('Bitte zuerst einen Block auswaehlen');
        return;
      }
      if (!speaker) {
        setStatus('Bitte zuerst einen Zielsprecher auswaehlen');
        return;
      }
      const selectedNode = document.querySelector(`[data-text-input="${CSS.escape(segmentId)}"]`);
      const liveRange = updateMarkedTextSelectionFromNode(selectedNode, segmentId);
      const effectiveRange = liveRange && String(liveRange.segmentId) === segmentId ? liveRange : null;
      syncSpeakerReassignMeta();
      if (!effectiveRange || effectiveRange.length < 1) {
        setStatus('Bitte markiere zuerst Text im ausgewaehlten Block');
        return;
      }

      const next = applySpeakerReassign({
        segments: collectSegmentsFromDom(),
        segmentId,
        speaker,
        startChar: effectiveRange.startChar,
        endChar: effectiveRange.endChar,
      });
      if (!next.changed) {
        setStatus('Sprecherumteilung konnte nicht angewendet werden');
        return;
      }
      try {
        await applySegments(next.segments, 'Sprecherumteilung gespeichert');
        clearMarkedTextSelection();
      } catch (error) {
        setStatus(`Sprecherumteilung fehlgeschlagen: ${error.message}`);
      }
    };
  }

  const mediaNode = getMediaElement();
  const audioRateNode = document.getElementById('cw-audio-rate');

  if (audioRateNode && mediaNode) {
    audioRateNode.onchange = () => {
      mediaNode.playbackRate = Number(audioRateNode.value || '1');
    };
    mediaNode.playbackRate = Number(audioRateNode.value || '1');
  }

  const centerBlockInEditor = (node) => {
    if (!editor || !node) return;
    const editorRect = editor.getBoundingClientRect();
    const blockRect = node.getBoundingClientRect();
    const blockOffsetInEditor = blockRect.top - editorRect.top + editor.scrollTop;
    const targetTop = blockOffsetInEditor - (editor.clientHeight / 2) + (blockRect.height / 2);
    editor.scrollTo({
      top: Math.max(0, targetTop),
      behavior: 'smooth',
    });
  };

  if (mediaNode) {
    const syncActiveFromMedia = (selectSegment) => {
      const nextIndex = findActiveSegmentIndex({ segments: state.segments, currentTime: mediaNode.currentTime });
      const segmentChanged = nextIndex !== state.activeSegmentIndex;
      if (segmentChanged) {
        state.activeSegmentIndex = nextIndex;
        syncActiveBlockHighlight(editor);
      }
      if (nextIndex >= 0) {
        const segment = state.segments[nextIndex];
        if (selectSegment) {
          const segmentId = String(segment.segment_id);
          if (String(state.selectedSegmentId || '') !== segmentId) {
            state.selectedSegmentId = segmentId;
            syncSelectedBlockHighlight(editor);
            syncSpeakerReassignMeta();
          }
        }
        const node = editor?.querySelector(`[data-segment-id="${CSS.escape(String(segment.segment_id))}"]`);
        if (segmentChanged && node) {
          centerBlockInEditor(node);
        }
      }
    };
    mediaNode.ontimeupdate = () => syncActiveFromMedia(false);
    mediaNode.onseeking = () => syncActiveFromMedia(true);
    mediaNode.onseeked = () => syncActiveFromMedia(true);
    mediaNode.onloadedmetadata = () => syncActiveFromMedia(true);
  }

  const commitButton = document.getElementById('cw-commit');
  if (commitButton) {
    commitButton.onclick = async () => {
      try {
        const draftSegments = collectSegmentsFromDom();
        await applySegments(draftSegments, 'Draft synchronisiert');
        const result = await callApi(`/api/v1/jobs/${state.jobId}/transcript/correction-sessions/${state.sessionId}/commit`, {
          method: 'POST',
          body: JSON.stringify({ base_version: state.baseVersion, edit_reason: 'Manueller Commit aus Korrekturmodus' }),
        });
        state.baseVersion = Number(result.version ?? state.baseVersion);
        state.workingVersion = state.baseVersion;
        clearUnsavedChanges();
        setStatus(`Version ${state.baseVersion} gespeichert`);
        render();
      } catch (error) {
        setStatus(`Commit fehlgeschlagen: ${error.message}`);
      }
    };
  }

  const themeToggle = document.getElementById('cw-theme-toggle');
  if (themeToggle) {
    themeToggle.onclick = () => {
      setTheme(document.body.dataset.theme === 'dark' ? 'light' : 'dark');
      render();
    };
  }

  const requestClosePrompt = () => {
    if (!state.hasUnsavedChanges) {
      attemptWindowClose();
      return;
    }
    state.closePromptVisible = true;
    render();
  };

  const closeButton = document.getElementById('cw-close');
  if (closeButton) {
    closeButton.onclick = requestClosePrompt;
  }

  const closeSaveButton = document.getElementById('cw-close-save');
  if (closeSaveButton) {
    closeSaveButton.onclick = async () => {
      try {
        state.closePromptVisible = false;
        await applySegments(collectSegmentsFromDom(), 'Draft gespeichert');
        attemptWindowClose();
      } catch (error) {
        setStatus(`Speichern vor dem Schliessen fehlgeschlagen: ${error.message}`);
      }
    };
  }

  const closeDiscardButton = document.getElementById('cw-close-discard');
  if (closeDiscardButton) {
    closeDiscardButton.onclick = () => {
      state.closePromptVisible = false;
      clearUnsavedChanges();
      render();
      attemptWindowClose();
    };
  }

  const closeCancelButton = document.getElementById('cw-close-cancel');
  if (closeCancelButton) {
    closeCancelButton.onclick = () => {
      state.closePromptVisible = false;
      render();
    };
  }

}

function attemptWindowClose() {
  window.close();
  window.setTimeout(() => {
    if (!window.closed) {
      setStatus('Browser hat das Schliessen blockiert. Bitte Tab manuell schliessen.');
    }
  }, 80);
}

async function init() {
  const bootstrap = getBootstrap();
  const app = document.getElementById('correction-app');
  if (!app) return;
  if (!bootstrap?.token || !bootstrap?.jobId) {
    app.innerHTML = '<p class="error">Korrektur-Startdaten fehlen.</p>';
    return;
  }

  state.token = String(bootstrap.token);
  state.jobId = String(bootstrap.jobId);
  state.tenantId = String(bootstrap.tenantId || '');
  const bootstrapTheme = String(bootstrap.theme || '').trim();
  let storedTheme = 'light';
  try {
    storedTheme = localStorage.getItem(THEME_STORAGE_KEY) || 'light';
  } catch {
    storedTheme = 'light';
  }
  const persistedTheme = bootstrapTheme || storedTheme;
  setTheme(persistedTheme === 'dark' ? 'dark' : 'light');

  try {
    try {
      state.mediaSource = await callApi(`/api/v1/jobs/${state.jobId}/media-source`);
      state.mediaLoadError = '';
    } catch (mediaError) {
      state.mediaSource = null;
      state.mediaLoadError = `Medienquelle konnte nicht geladen werden: ${mediaError.message}`;
    }

    const transcript = await callApi(`/api/v1/jobs/${state.jobId}/transcript`);
    state.baseVersion = Number(transcript.version ?? 1);
    state.reviewStatus = String(transcript.review_status ?? 'in_review');
    state.isFinal = Boolean(transcript.is_final ?? false);

    const session = await callApi(`/api/v1/jobs/${state.jobId}/transcript/correction-sessions`, {
      method: 'POST',
      body: JSON.stringify({
        base_version: state.baseVersion,
        autosave_enabled: false,
        force_reseed_from_transcript: true,
      }),
    });

    patchStateFromSession(session);
    clearUnsavedChanges();
    setStatus('Korrektursitzung gestartet');
    render();
  } catch (error) {
    app.innerHTML = `<p class="error">Korrekturmodus konnte nicht geladen werden: ${escapeHtml(error.message)}</p>`;
  }
}

window.addEventListener('beforeunload', (event) => {
  if (!state.hasUnsavedChanges) return;
  event.preventDefault();
  event.returnValue = '';
});

void init();
