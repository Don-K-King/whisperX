import {
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
  parseMediaStripHeightPx,
  parseSidebarSectionState,
  parseSidebarVisibility,
  resolveCorrectionBootstrapFeedback,
  resolveMediaStripHeightPx,
  resolveExportMenuState,
  resolveMarkedTextRange,
  resolveMediaSeekTime,
  resolveSpeakerTint,
  resolveSelectedSegmentId,
  resolveGapSeekTargetIndex,
  resolveVirtualWindowPreferredIndex,
  resolveVirtualWindowPinnedIndex,
  resolveAdaptiveWindowSize,
  resolveAdaptiveVirtualRange,
  resolvePlaybackFollowDecision,
  resolveSeekWarmupRange,
  resolveSeekWarmupReadiness,
  resolveSeekPlaybackResumeDecision,
  resolveForcedVirtualRange,
  shouldAutoSeek,
  serializeSidebarSectionState,
  SIDEBAR_SECTION_IDS,
} from './correction_workspace_viewmodel.js';
import {
  buildCorrectionExportBaseName,
  buildCorrectionMarkdownExport,
  buildCorrectionPlainTextExport,
  buildSimpleDocxFromPlainText,
  buildSimplePdfFromPlainText,
} from './correction_workspace_export.js';

const THEME_STORAGE_KEY = 'evodox-theme';
const SIDEBAR_VISIBILITY_STORAGE_KEY = 'evodox-correction-sidebar-visible';
const SIDEBAR_SECTION_STATE_STORAGE_KEY = 'evodox-correction-sidebar-sections';
const AUTO_SEEK_SELECTION_STORAGE_KEY = 'evodox-correction-auto-seek-selection';
const FOOTER_MEDIA_HEIGHT_STORAGE_KEY = 'evodox-correction-footer-media-height-px';
const FOOTER_MEDIA_HEIGHT_MIN_PX = 56;
const FOOTER_MEDIA_HEIGHT_MAX_PX = 220;
const FOOTER_MEDIA_HEIGHT_DEFAULT_PX = 108;
const FOOTER_MEDIA_HEIGHT_STEP_PX = 8;
const VIRTUAL_ROW_HEIGHT = 156;
const VIRTUAL_OVERSCAN = 8;
const SEEK_WARMUP_LOOKAHEAD = 10;
const SEEK_WARMUP_TIMEOUT_MS = 250;

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
  isBootstrapping: true,
  bootstrapPhase: 'boot',
  bootstrapError: '',
  sidebarVisible: loadPersistedSidebarVisibility(),
  sidebarSectionsOpen: loadPersistedSidebarSectionState(),
  autoSeekSelectionEnabled: loadPersistedAutoSeekSelectionEnabled(),
  mediaStripHeightPx: loadPersistedMediaStripHeightPx(),
  exportMenuOpen: false,
  lastExportAction: '',
  selectedTextRange: null,
  segmentIndexById: {},
  dirtySegmentIds: new Set(),
  editorScrollTop: 0,
  editorClientHeight: 760,
  virtualRange: { start: 0, end: 0 },
  playbackFollowAnchorSegmentId: null,
  playbackFollowPending: false,
  lastPlaybackFollowMs: 0,
  lastPlaybackTickMs: 0,
  seekForcedRange: null,
  seekWarmupTargetIndex: -1,
  seekWarmupTargetSegmentId: null,
  seekResumePending: false,
  seekResumeWasPlaying: false,
  seekResumeDeadlineMs: 0,
  seekResumeTimerId: null,
  segmentHeightById: {},
  segmentHeightPrefix: [0],
  segmentHeightCacheDirty: true,
  initializedTextareaIds: new Set(),
};

let exportMenuDismissHandler = null;
let exportMenuEscapeHandler = null;
let exportMenuFocusHandler = null;
let cachedBootstrapPayload = null;

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
  if (cachedBootstrapPayload) {
    return cachedBootstrapPayload;
  }
  const params = new URLSearchParams(window.location.search);
  const handoff = String(params.get('handoff') || '').trim();
  if (!handoff) {
    return null;
  }
  const payload = consumeCorrectionHandoff(handoff);
  if (!payload) {
    return null;
  }
  cachedBootstrapPayload = payload;
  return cachedBootstrapPayload;
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
  syncStatusMessageNodes();
}

function resolveDisplayedStatusMessage() {
  if (state.playbackFollowPending) {
    return 'Aktiven Block synchronisieren ...';
  }
  return String(state.statusMessage || '');
}

function syncStatusMessageNodes() {
  const message = resolveDisplayedStatusMessage();
  const sidebarNode = document.getElementById('cw-status-message');
  if (sidebarNode) sidebarNode.textContent = message;
}

function clearSeekResumeTimer() {
  if (!state.seekResumeTimerId) return;
  window.clearTimeout(state.seekResumeTimerId);
  state.seekResumeTimerId = null;
}

function resetSeekWarmupState() {
  state.seekForcedRange = null;
  state.seekWarmupTargetIndex = -1;
  state.seekWarmupTargetSegmentId = null;
  state.seekResumePending = false;
  state.seekResumeWasPlaying = false;
  state.seekResumeDeadlineMs = 0;
  clearSeekResumeTimer();
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

function loadPersistedMediaStripHeightPx() {
  try {
    return parseMediaStripHeightPx(
      localStorage.getItem(FOOTER_MEDIA_HEIGHT_STORAGE_KEY),
      {
        minPx: FOOTER_MEDIA_HEIGHT_MIN_PX,
        maxPx: FOOTER_MEDIA_HEIGHT_MAX_PX,
        fallbackPx: FOOTER_MEDIA_HEIGHT_DEFAULT_PX,
      },
    );
  } catch {
    return FOOTER_MEDIA_HEIGHT_DEFAULT_PX;
  }
}

function persistMediaStripHeightPx(heightPx) {
  try {
    localStorage.setItem(FOOTER_MEDIA_HEIGHT_STORAGE_KEY, String(heightPx));
  } catch {
    // ignore persistence errors
  }
}

function applyMediaStripHeightPx(heightPx, options = {}) {
  const next = resolveMediaStripHeightPx(heightPx, {
    minPx: FOOTER_MEDIA_HEIGHT_MIN_PX,
    maxPx: FOOTER_MEDIA_HEIGHT_MAX_PX,
    fallbackPx: FOOTER_MEDIA_HEIGHT_DEFAULT_PX,
  });
  state.mediaStripHeightPx = next;
  if (document.body) {
    document.body.style.setProperty('--cw-media-strip-height', `${next}px`);
  }
  if (options.persist !== false) {
    persistMediaStripHeightPx(next);
  }
  return next;
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
  const index = getSegmentIndex(String(state.selectedSegmentId));
  if (index < 0) return null;
  return state.segments[index] || null;
}

function getSegmentIndex(segmentId) {
  const key = String(segmentId || '');
  if (!key) return -1;
  const index = state.segmentIndexById?.[key];
  return Number.isInteger(index) ? index : -1;
}

function getSegmentById(segmentId) {
  const index = getSegmentIndex(segmentId);
  if (index < 0) return null;
  return state.segments[index] || null;
}

function rebuildSegmentIndex() {
  const map = {};
  state.segments.forEach((segment, index) => {
    const key = String(segment?.segment_id || '');
    if (!key) return;
    map[key] = index;
  });
  state.segmentIndexById = map;
  state.segmentHeightCacheDirty = true;
}

function estimateSegmentRowHeight(segment) {
  const text = String(segment?.text ?? '');
  const newlineCount = (text.match(/\n/g) || []).length;
  const textLength = text.length;
  const wrappedLines = Math.ceil(Math.max(1, textLength) / 120);
  const totalLines = Math.max(1, newlineCount + wrappedLines);
  const estimated = 112 + (totalLines * 20);
  return Math.max(96, estimated);
}

function getSegmentHeightByIndex(index) {
  const segment = state.segments[index];
  if (!segment) return VIRTUAL_ROW_HEIGHT;
  const segmentId = String(segment.segment_id || '');
  const cached = Number(state.segmentHeightById?.[segmentId]);
  if (Number.isFinite(cached) && cached > 20) {
    return cached;
  }
  return estimateSegmentRowHeight(segment);
}

function updateSegmentHeightCache(segmentId, height) {
  const key = String(segmentId || '').trim();
  const next = Number(height);
  if (!key || !Number.isFinite(next) || next < 20) return false;
  const previous = Number(state.segmentHeightById?.[key]);
  if (Number.isFinite(previous) && Math.abs(previous - next) < 2) return false;
  state.segmentHeightById[key] = next;
  state.segmentHeightCacheDirty = true;
  return true;
}

function rebuildSegmentHeightPrefixIfDirty() {
  if (!state.segmentHeightCacheDirty && Array.isArray(state.segmentHeightPrefix) && state.segmentHeightPrefix.length === (state.segments.length + 1)) {
    return;
  }
  const prefix = [0];
  let cumulative = 0;
  for (let i = 0; i < state.segments.length; i += 1) {
    cumulative += getSegmentHeightByIndex(i);
    prefix.push(cumulative);
  }
  state.segmentHeightPrefix = prefix;
  state.segmentHeightCacheDirty = false;
}

function lowerBoundPrefix(prefix, target) {
  let lo = 0;
  let hi = Math.max(0, prefix.length - 1);
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (Number(prefix[mid]) < target) {
      lo = mid + 1;
    } else {
      hi = mid;
    }
  }
  return lo;
}

function resolveEditorScrollTopForIndex(index) {
  const targetIndex = Number.isInteger(index) ? index : -1;
  if (targetIndex < 0) return 0;
  rebuildSegmentHeightPrefixIfDirty();
  const prefix = state.segmentHeightPrefix;
  const viewport = Math.max(280, Number(state.editorClientHeight || 760));
  const top = Number(prefix[targetIndex] || 0);
  const bottom = Number(prefix[targetIndex + 1] || top + VIRTUAL_ROW_HEIGHT);
  const center = (top + bottom) / 2;
  return Math.max(0, center - (viewport / 2));
}

function syncVisibleBlockHeightCache(editor) {
  if (!editor) return false;
  let changed = false;
  editor.querySelectorAll('.cw-block[data-segment-id]').forEach((block) => {
    const segmentId = String(block.getAttribute('data-segment-id') || '');
    if (!segmentId) return;
    const measuredHeight = Number(block.getBoundingClientRect().height || block.offsetHeight || 0);
    if (updateSegmentHeightCache(segmentId, measuredHeight)) {
      changed = true;
    }
  });
  return changed;
}

function initializeVisibleTextareas(editor) {
  if (!editor) return;
  editor.querySelectorAll('[data-text-input]').forEach((node) => {
    const segmentId = String(node.getAttribute('data-text-input') || '').trim();
    if (!segmentId) return;
    if (!state.initializedTextareaIds.has(segmentId)) {
      autoResizeTextarea(node);
      state.initializedTextareaIds.add(segmentId);
    }
  });
  syncVisibleBlockHeightCache(editor);
}

function markSegmentDirty(segmentId) {
  const key = String(segmentId || '').trim();
  if (!key) return;
  state.dirtySegmentIds.add(key);
  state.pendingSave = true;
  markUnsavedChanges();
}

function clearDirtySegments(segmentIds = []) {
  segmentIds.forEach((segmentId) => {
    state.dirtySegmentIds.delete(String(segmentId));
  });
  if (state.dirtySegmentIds.size === 0) {
    state.pendingSave = false;
    clearUnsavedChanges();
  }
}

function resetDirtyState() {
  state.dirtySegmentIds = new Set();
  state.pendingSave = false;
  clearUnsavedChanges();
}

function buildUpdateTextOperationsFromDirtySegments() {
  if (!(state.dirtySegmentIds instanceof Set) || state.dirtySegmentIds.size === 0) return [];
  const operations = [];
  state.dirtySegmentIds.forEach((segmentId) => {
    const segment = getSegmentById(segmentId);
    if (!segment) return;
    operations.push({
      type: 'update_text',
      segment_id: String(segment.segment_id),
      text: String(segment.text ?? ''),
    });
  });
  return operations;
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
  const segment = getSegmentById(segmentId);
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
  // Defer revocation so slow browser download managers can still resolve the URL.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function exportCurrentTranscript(format) {
  try {
    const createdAt = new Date();
    const segments = collectSegmentsFromState();
    const baseName = buildCorrectionExportBaseName({ jobId: state.jobId, createdAt });
    const exportMode = 'compact';
    if (format === 'md') {
      const markdown = buildCorrectionMarkdownExport({
        jobId: state.jobId,
        sessionId: state.sessionId,
        baseVersion: state.baseVersion,
        workingVersion: state.workingVersion,
        reviewStatus: state.reviewStatus,
        isFinal: state.isFinal,
        mode: exportMode,
        segments,
        speakerLabels: state.speakerLabels,
        createdAt,
      });
      triggerDownload({
        filename: `${baseName}.md`,
        mimeType: 'text/markdown;charset=utf-8',
        payload: markdown,
      });
      setStatus('Markdown-Export erstellt (Kompakt)');
      return;
    }

    const text = buildCorrectionPlainTextExport({
      jobId: state.jobId,
      sessionId: state.sessionId,
      baseVersion: state.baseVersion,
      workingVersion: state.workingVersion,
      reviewStatus: state.reviewStatus,
      isFinal: state.isFinal,
      mode: exportMode,
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
      setStatus('PDF-Export erstellt (Kompakt)');
      return;
    }

    if (format === 'word_docx' || format === 'txt') {
      if (format === 'txt') {
        triggerDownload({
          filename: `${baseName}.txt`,
          mimeType: 'text/plain;charset=utf-8',
          payload: text,
        });
        setStatus('TXT-Export erstellt (Kompakt)');
        return;
      }

      const docxBytes = buildSimpleDocxFromPlainText(text);
      triggerDownload({
        filename: `${baseName}.docx`,
        mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        payload: docxBytes,
      });
      setStatus('Word DOCX-Export erstellt (Kompakt)');
      return;
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
  const nextIndex = getSegmentIndex(segmentId);
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
  if (!node) {
    const segmentIndex = getSegmentIndex(resolvedSegmentId);
    if (segmentIndex >= 0) {
      editor.scrollTop = resolveEditorScrollTopForIndex(segmentIndex);
    }
    return;
  }
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

function resolveVirtualRange() {
  const total = state.segments.length;
  if (total === 0) {
    return { start: 0, end: 0, topSpacer: 0, bottomSpacer: 0 };
  }
  rebuildSegmentHeightPrefixIfDirty();
  const prefix = state.segmentHeightPrefix;
  const totalHeight = Number(prefix[total] || 0);
  const selectedIndex = getSegmentIndex(state.selectedSegmentId);
  const activeIndex = Number.isInteger(state.activeSegmentIndex) ? state.activeSegmentIndex : -1;
  const playbackAnchorIndex = getSegmentIndex(state.playbackFollowAnchorSegmentId);
  const followPlaybackAnchor = Boolean(state.playbackFollowAnchorSegmentId)
    && (state.playbackFollowPending || ((Date.now() - Number(state.lastPlaybackTickMs || 0)) < 1200));
  const preferredIndex = resolveVirtualWindowPreferredIndex({
    selectedIndex,
    activeIndex,
    playbackAnchorIndex,
    preferPlaybackAnchor: followPlaybackAnchor,
  });
  const pinnedIndex = resolveVirtualWindowPinnedIndex({
    preferredIndex,
    preferPlaybackAnchor: followPlaybackAnchor,
  });
  const adaptiveWindowSize = resolveAdaptiveWindowSize({ totalSegments: total });
  if (adaptiveWindowSize >= total) {
    return { start: 0, end: total, topSpacer: 0, bottomSpacer: 0 };
  }
  const forcedRange = state.seekForcedRange;
  if (forcedRange && Number.isFinite(Number(forcedRange.start)) && Number.isFinite(Number(forcedRange.end))) {
    const resolvedForcedRange = resolveForcedVirtualRange({
      totalSegments: total,
      start: Number(forcedRange.start),
      end: Number(forcedRange.end),
      fallbackIndex: preferredIndex,
      overscan: VIRTUAL_OVERSCAN,
    });
    const anchoredForcedRange = resolveAdaptiveVirtualRange({
      totalSegments: total,
      start: resolvedForcedRange.start,
      end: resolvedForcedRange.end,
      targetWindowSize: adaptiveWindowSize,
      anchorIndex: preferredIndex,
    });
    const start = anchoredForcedRange.start;
    const end = anchoredForcedRange.end;
    const topSpacer = Number(prefix[start] || 0);
    const bottomSpacer = Math.max(0, totalHeight - Number(prefix[end] || 0));
    return { start, end, topSpacer, bottomSpacer };
  }
  const viewport = Math.max(280, Number(state.editorClientHeight || 760));
  const scrollTop = Math.max(0, Math.min(Number(state.editorScrollTop || 0), Math.max(0, totalHeight - viewport)));
  let start = Math.max(0, lowerBoundPrefix(prefix, scrollTop) - 1 - VIRTUAL_OVERSCAN);
  let end = Math.min(total, lowerBoundPrefix(prefix, scrollTop + viewport + 1) + VIRTUAL_OVERSCAN);
  if (end <= start) {
    end = Math.min(total, start + 1);
  }
  if (pinnedIndex >= 0) {
    if (pinnedIndex < start || pinnedIndex >= end) {
      start = Math.max(0, pinnedIndex - VIRTUAL_OVERSCAN);
      end = Math.min(total, pinnedIndex + VIRTUAL_OVERSCAN + 1);
    }
  }
  const anchorIndex = pinnedIndex >= 0 ? pinnedIndex : preferredIndex;
  const adaptiveRange = resolveAdaptiveVirtualRange({
    totalSegments: total,
    start,
    end,
    targetWindowSize: adaptiveWindowSize,
    anchorIndex,
  });
  start = adaptiveRange.start;
  end = adaptiveRange.end;
  const topSpacer = Number(prefix[start] || 0);
  const bottomSpacer = Math.max(0, totalHeight - Number(prefix[end] || 0));
  return { start, end, topSpacer, bottomSpacer };
}

function renderEditorBlocks() {
  const range = resolveVirtualRange();
  state.virtualRange = { start: range.start, end: range.end };
  const rows = state.segments.slice(range.start, range.end).map((segment, relativeIndex) => {
    const index = range.start + relativeIndex;
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
        data-segment-index="${index}"
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
  return `
    <div class="cw-virtual-spacer" style="height:${Math.max(0, range.topSpacer)}px"></div>
    ${rows}
    <div class="cw-virtual-spacer" style="height:${Math.max(0, range.bottomSpacer)}px"></div>
  `;
}

function renderBootstrapScreen() {
  const app = document.getElementById('correction-app');
  if (!app) return;
  const feedback = resolveCorrectionBootstrapFeedback({ phase: state.bootstrapPhase });
  const hasError = Boolean(String(state.bootstrapError || '').trim());
  const steps = feedback.steps.map((step) => `
    <li class="cw-loading-step cw-loading-step--${escapeHtml(step.status)}">
      <span class="cw-loading-step-dot" aria-hidden="true"></span>
      <span>${escapeHtml(step.label)}</span>
    </li>
  `).join('');
  app.innerHTML = `
    <section
      class="cw-loading-root"
      role="status"
      aria-live="polite"
      aria-busy="${hasError ? 'false' : 'true'}"
      aria-label="Korrekturmodus wird geladen"
    >
      <article class="cw-loading-card">
        <div class="cw-loading-header">
          <span class="cw-loading-spinner" aria-hidden="true"></span>
          <div>
            <h1>${escapeHtml(feedback.title)}</h1>
            <p class="cw-status">${escapeHtml(feedback.detail)}</p>
          </div>
        </div>
        <ol class="cw-loading-steps">${steps}</ol>
        ${hasError ? `
          <p class="error">Korrekturmodus konnte nicht geladen werden: ${escapeHtml(state.bootstrapError)}</p>
          <div class="cw-row">
            <button id="cw-bootstrap-retry" class="primary" type="button">Erneut versuchen</button>
          </div>
        ` : ''}
      </article>
    </section>
  `;
  if (hasError) {
    const retryButton = document.getElementById('cw-bootstrap-retry');
    if (retryButton) {
      retryButton.onclick = () => {
        retryButton.disabled = true;
        state.bootstrapError = '';
        void init();
      };
    }
  }
}

function render() {
  const app = document.getElementById('correction-app');
  if (!app) return;
  applyMediaStripHeightPx(state.mediaStripHeightPx, { persist: false });
  if (state.isBootstrapping) {
    renderBootstrapScreen();
    return;
  }
  const previousEditor = document.getElementById('cw-editor');
  if (previousEditor) {
    state.editorScrollTop = Number(previousEditor.scrollTop || 0);
    state.editorClientHeight = Number(previousEditor.clientHeight || state.editorClientHeight || 760);
  }
  const existingMedia = getMediaElement();
  const existingMediaSrc = String(existingMedia?.currentSrc || existingMedia?.getAttribute('src') || '').trim();
  const mediaSnapshot = captureMediaPlaybackState();
  const speakerOptions = getSpeakerOptions()
    .map((entry) => `<option value="${escapeHtml(entry.key)}">${escapeHtml(entry.label)}</option>`)
    .join('');
  const theme = document.body.dataset.theme === 'dark' ? 'dark' : 'light';
  const mediaNode = renderMediaNode();
  const displayedStatusMessage = resolveDisplayedStatusMessage();
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
              <div id="cw-export-menu-list" class="cw-export-menu-list" role="menu" aria-label="Export">
                <button id="cw-export-md" role="menuitem" type="button">Markdown</button>
                <button id="cw-export-pdf" role="menuitem" type="button">PDF</button>
                <button id="cw-export-word-docx" role="menuitem" type="button">Word (DOCX)</button>
                <button id="cw-export-txt" role="menuitem" type="button">TXT</button>
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
          <p id="cw-status-message" class="cw-status cw-sidebar-status">${escapeHtml(displayedStatusMessage)}</p>
        </aside>
        ` : ''}
      </section>
      <footer class="cw-audio">
        <button
          id="cw-media-resize-handle"
          class="cw-media-resize-handle"
          type="button"
          aria-label="Footerhoehe anpassen"
          aria-valuemin="${FOOTER_MEDIA_HEIGHT_MIN_PX}"
          aria-valuemax="${FOOTER_MEDIA_HEIGHT_MAX_PX}"
          aria-valuenow="${state.mediaStripHeightPx}"
          title="Footerhoehe ziehen oder mit Pfeiltasten anpassen"
        ></button>
        <div class="cw-media-shell">
          <div id="cw-media-slot" class="cw-media-slot">${mediaNode}</div>
          <div class="cw-media-controls">
            <select id="cw-audio-rate" aria-label="Wiedergabegeschwindigkeit">
              <option value="0.75">0.75x</option>
              <option value="1" selected>1.0x</option>
              <option value="1.25">1.25x</option>
              <option value="1.5">1.5x</option>
              <option value="2">2.0x</option>
            </select>
          </div>
        </div>
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

  const shouldReuseMedia = existingMedia
    && existingMediaSrc
    && state.mediaSource?.media_url
    && existingMediaSrc === String(state.mediaSource.media_url).trim();
  if (shouldReuseMedia) {
    const mediaSlot = document.getElementById('cw-media-slot');
    if (mediaSlot) {
      mediaSlot.replaceChildren(existingMedia);
    }
  } else {
    restoreMediaPlaybackState(mediaSnapshot);
  }
  const renderedEditor = document.getElementById('cw-editor');
  if (renderedEditor) {
    renderedEditor.scrollTop = Math.max(0, Number(state.editorScrollTop || 0));
    const measured = syncVisibleBlockHeightCache(renderedEditor);
    if (measured) {
      state.segmentHeightCacheDirty = true;
    }
  }
  bindInteractions();
  syncExportMenuListeners();
  syncSpeakerReassignMeta();
  syncStatusMessageNodes();
}

function renderMediaNode() {
  if (!state.mediaSource?.media_url) {
    return '<div class="cw-media-empty" aria-hidden="true"></div>';
  }
  const url = escapeHtml(state.mediaSource.media_url);
  const isVideo = String(state.mediaSource.content_type || '').startsWith('video/');
  if (isVideo) {
    return `<video id="cw-media" data-media-player controls preload="metadata" src="${url}"></video>`;
  }
  return `<audio id="cw-media" data-media-player controls preload="metadata" src="${url}"></audio>`;
}

function collectSegmentsFromState() {
  return normalizeSegments(state.segments.map((segment) => ({ ...segment })));
}

function mergeChangedSegmentsIntoState(changedSegments = [], removedSegmentIds = []) {
  const removedSet = new Set((removedSegmentIds || []).map((item) => String(item)).filter(Boolean));
  const changedMap = new Map();
  (changedSegments || []).forEach((segment) => {
    const key = String(segment?.segment_id || '').trim();
    if (!key) return;
    changedMap.set(key, segment);
  });
  const merged = [];
  for (const segment of state.segments) {
    const key = String(segment.segment_id || '');
    if (!key || removedSet.has(key)) continue;
    if (changedMap.has(key)) {
      merged.push({ ...segment, ...changedMap.get(key) });
      changedMap.delete(key);
      continue;
    }
    merged.push(segment);
  }
  changedMap.forEach((segment) => {
    merged.push(segment);
  });
  state.segments = normalizeSegments(merged);
  rebuildSegmentIndex();
  state.segmentHeightCacheDirty = true;
}

async function applyOperations(operations, message = 'Aenderungen gespeichert', options = {}) {
  if (!Array.isArray(operations) || operations.length === 0) return null;
  const editor = document.getElementById('cw-editor');
  const fallbackContext = captureEditorContext(editor);
  const context = options?.editorContext || fallbackContext;
  const payload = {
    operations,
    return_mode: options.returnMode || 'changed_segments',
  };
  if (state.autosaveEnabled) payload.autosave_enabled = true;
  const result = await callApi(`/api/v1/jobs/${state.jobId}/transcript/correction-sessions/${state.sessionId}/operations`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  patchStateFromSession(result);
  if (Array.isArray(options.clearDirtyIds) && options.clearDirtyIds.length > 0) {
    clearDirtySegments(options.clearDirtyIds);
  }
  setStatus(message);
  if (options.renderAfter !== false) {
    render();
    const renderedEditor = document.getElementById('cw-editor');
    restoreEditorContext(renderedEditor, context);
  }
  return result;
}

async function flushDirtyTextOperations(message = 'Draft-Stand gespeichert', options = {}) {
  const operations = buildUpdateTextOperationsFromDirtySegments();
  if (operations.length === 0) return false;
  const dirtyIds = operations.map((operation) => operation.segment_id);
  await applyOperations(operations, message, {
    returnMode: options.returnMode || 'ack',
    renderAfter: options.renderAfter !== false,
    clearDirtyIds: dirtyIds,
  });
  return true;
}

function scheduleAutosave() {
  state.pendingSave = true;
  if (!state.autosaveEnabled) return;
  if (state.autosaveTimer) clearTimeout(state.autosaveTimer);
  state.autosaveTimer = setTimeout(async () => {
    state.autosaveTimer = null;
    if (!state.pendingSave) return;
    try {
      await flushDirtyTextOperations('Autosave-Draft aktualisiert', {
        returnMode: 'ack',
        renderAfter: false,
      });
    } catch (error) {
      setStatus(`Autosave fehlgeschlagen: ${error.message}`);
    }
  }, 1200);
}

function patchStateFromSession(payload) {
  state.sessionId = payload.session_id;
  state.baseVersion = Number(payload.base_version ?? state.baseVersion);
  state.workingVersion = Number(payload.working_version ?? state.workingVersion);
  if (typeof payload.autosave_enabled === 'boolean') {
    state.autosaveEnabled = payload.autosave_enabled;
  }
  if (payload.speaker_labels && typeof payload.speaker_labels === 'object') {
    state.speakerLabels = payload.speaker_labels;
  }
  const returnMode = String(payload.return_mode || 'full').trim().toLowerCase();
  if (Array.isArray(payload.segments)) {
    if (returnMode === 'changed_segments') {
      mergeChangedSegmentsIntoState(payload.segments, payload.removed_segment_ids || []);
    } else {
      state.segments = normalizeSegments(payload.segments ?? []);
      rebuildSegmentIndex();
      state.segmentHeightCacheDirty = true;
    }
  }
  if (Array.isArray(payload.operation_log)) {
    state.operationLog = payload.operation_log;
  }
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
    initializeVisibleTextareas(editor);
    const syncNodeSelection = (node) => {
      if (!node) return;
      const segmentId = String(node.getAttribute('data-text-input') || '');
      if (!segmentId) return;
      state.selectedSegmentId = segmentId;
      syncSelectedBlockHighlight(editor);
      updateMarkedTextSelectionFromNode(node, segmentId);
      syncSpeakerReassignMeta();
    };

    editor.oninput = (event) => {
      const node = event.target?.closest?.('[data-text-input]');
      if (!node) return;
      const segmentId = String(node.getAttribute('data-text-input') || '');
      if (!segmentId) return;
      const index = getSegmentIndex(segmentId);
      if (index >= 0) {
        state.segments[index] = {
          ...state.segments[index],
          text: String(node.value ?? ''),
        };
      }
      autoResizeTextarea(node);
      const blockNode = node.closest('.cw-block');
      if (blockNode) {
        const blockSegmentId = String(blockNode.getAttribute('data-segment-id') || segmentId);
        const measuredHeight = Number(blockNode.getBoundingClientRect().height || blockNode.offsetHeight || 0);
        updateSegmentHeightCache(blockSegmentId, measuredHeight);
      }
      markSegmentDirty(segmentId);
      scheduleAutosave();
      syncNodeSelection(node);
    };

    editor.onfocusin = (event) => {
      const node = event.target?.closest?.('[data-text-input]');
      if (!node) return;
      const segmentId = String(node.getAttribute('data-text-input') || '');
      if (!segmentId) return;
      const previousSegmentId = String(state.selectedSegmentId || '');
      state.selectedSegmentId = segmentId;
      syncSelectedBlockHighlight(editor);
      activateSegmentForUi(segmentId, editor);
      maybeAutoSeekToSegment({ previousSegmentId, nextSegmentId: segmentId, source: 'text_focus' });
      if (!state.initializedTextareaIds.has(segmentId)) {
        autoResizeTextarea(node);
        state.initializedTextareaIds.add(segmentId);
      }
      syncSpeakerReassignMeta();
    };

    editor.onmouseup = (event) => {
      const node = event.target?.closest?.('[data-text-input]');
      if (!node) return;
      syncNodeSelection(node);
    };

    editor.onkeyup = (event) => {
      const node = event.target?.closest?.('[data-text-input]');
      if (!node) return;
      syncNodeSelection(node);
    };

    editor.onclick = (event) => {
      const jumpNode = event.target?.closest?.('[data-segment-jump]');
      if (jumpNode) {
        event.preventDefault();
        event.stopPropagation();
        const segmentId = String(jumpNode.getAttribute('data-segment-jump') || '');
        if (!segmentId) return;
        state.selectedSegmentId = segmentId;
        syncSelectedBlockHighlight(editor);
        activateSegmentForUi(segmentId, editor);
        seekMediaToSegmentStart(segmentId);
        syncSpeakerReassignMeta();
        return;
      }
      const blockNode = event.target?.closest?.('.cw-block');
      if (!blockNode) return;
      const nextSegmentId = String(blockNode.dataset.segmentId || '');
      const previousSegmentId = String(state.selectedSegmentId || '');
      state.selectedSegmentId = nextSegmentId;
      syncSelectedBlockHighlight(editor);
      activateSegmentForUi(nextSegmentId, editor);
      maybeAutoSeekToSegment({ previousSegmentId, nextSegmentId, source: 'block_click' });
      syncSpeakerReassignMeta();
    };

    let scrollRaf = null;
    editor.onscroll = () => {
      if (!state.playbackFollowPending && (state.seekForcedRange || state.seekResumePending)) {
        resetSeekWarmupState();
        state.playbackFollowPending = false;
        syncStatusMessageNodes();
      }
      state.editorScrollTop = Number(editor.scrollTop || 0);
      if (scrollRaf) return;
      scrollRaf = window.requestAnimationFrame(() => {
        scrollRaf = null;
        const nextRange = resolveVirtualRange();
        if (nextRange.start === state.virtualRange.start && nextRange.end === state.virtualRange.end) return;
        render();
        const nextEditor = document.getElementById('cw-editor');
        if (nextEditor) nextEditor.scrollTop = Math.max(0, Number(state.editorScrollTop || 0));
      });
    };
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
        const changed = await flushDirtyTextOperations('Draft-Stand gespeichert', {
          returnMode: 'changed_segments',
          renderAfter: true,
        });
        if (!changed) setStatus('Keine Aenderungen zum Speichern');
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

  const runExportAction = (action) => {
    applyExportMenuEvent({ type: 'select', action });
    exportCurrentTranscript(action);
    render();
  };

  const exportMarkdownButton = document.getElementById('cw-export-md');
  if (exportMarkdownButton) {
    exportMarkdownButton.onclick = () => runExportAction('md');
  }

  const exportPdfButton = document.getElementById('cw-export-pdf');
  if (exportPdfButton) {
    exportPdfButton.onclick = () => runExportAction('pdf');
  }

  const exportWordButton = document.getElementById('cw-export-word-docx');
  if (exportWordButton) {
    exportWordButton.onclick = () => runExportAction('word_docx');
  }

  const exportTxtButton = document.getElementById('cw-export-txt');
  if (exportTxtButton) {
    exportTxtButton.onclick = () => runExportAction('txt');
  }

  const discardButton = document.getElementById('cw-discard');
  if (discardButton) {
    discardButton.onclick = async () => {
      try {
        const result = await callApi(`/api/v1/jobs/${state.jobId}/transcript/correction-sessions/${state.sessionId}/discard`, {
          method: 'POST',
        });
        patchStateFromSession(result);
        resetDirtyState();
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
        resetDirtyState();
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
        resetDirtyState();
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
    try {
      await flushDirtyTextOperations('Lokale Aenderungen synchronisiert', {
        returnMode: 'changed_segments',
        renderAfter: true,
      });
      await applyOperations(
        [{
          type: 'replace_literal',
          query: state.replaceQuery,
          replace: state.replaceValue,
          speaker: state.searchSpeaker || undefined,
          replace_all: replaceAll,
        }],
        replaceAll ? 'Ersetzen (alle) gespeichert' : 'Ersetzen (ein Treffer) gespeichert',
        { returnMode: 'full', renderAfter: true },
      );
      clearDirtySegments([...state.dirtySegmentIds]);
      clearMarkedTextSelection();
    } catch (error) {
      if (String(error?.message || '').includes('replace_no_match')) {
        setStatus('Keine Treffer fuer Ersetzen gefunden');
        return;
      }
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

      try {
        await flushDirtyTextOperations('Lokale Aenderungen synchronisiert', {
          returnMode: 'changed_segments',
          renderAfter: true,
        });
        const operation = {
          type: 'reassign_speaker',
          segment_id: segmentId,
          speaker,
          start_char: effectiveRange.startChar,
          end_char: effectiveRange.endChar,
        };
        await applyOperations([operation], 'Sprecherumteilung gespeichert', {
          returnMode: 'full',
          renderAfter: true,
        });
        clearDirtySegments([...state.dirtySegmentIds]);
        clearMarkedTextSelection();
      } catch (error) {
        setStatus(`Sprecherumteilung fehlgeschlagen: ${error.message}`);
      }
    };
  }

  const mediaNode = getMediaElement();
  const audioRateNode = document.getElementById('cw-audio-rate');
  const mediaResizeHandle = document.getElementById('cw-media-resize-handle');

  if (audioRateNode && mediaNode) {
    audioRateNode.onchange = () => {
      mediaNode.playbackRate = Number(audioRateNode.value || '1');
    };
    mediaNode.playbackRate = Number(audioRateNode.value || '1');
  }

  if (mediaResizeHandle) {
    const setHandleValue = (valuePx) => {
      mediaResizeHandle.setAttribute('aria-valuenow', String(valuePx));
    };
    const applyDelta = (deltaPx, persist = true) => {
      const next = applyMediaStripHeightPx(state.mediaStripHeightPx + Number(deltaPx || 0), { persist });
      setHandleValue(next);
    };

    mediaResizeHandle.onkeydown = (event) => {
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        applyDelta(FOOTER_MEDIA_HEIGHT_STEP_PX, true);
        return;
      }
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        applyDelta(-FOOTER_MEDIA_HEIGHT_STEP_PX, true);
      }
    };

    mediaResizeHandle.ondblclick = (event) => {
      event.preventDefault();
      const next = applyMediaStripHeightPx(FOOTER_MEDIA_HEIGHT_DEFAULT_PX, { persist: true });
      setHandleValue(next);
    };

    mediaResizeHandle.onpointerdown = (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      const startY = Number(event.clientY || 0);
      const startHeight = Number(state.mediaStripHeightPx || FOOTER_MEDIA_HEIGHT_DEFAULT_PX);
      const pointerId = event.pointerId;

      try {
        mediaResizeHandle.setPointerCapture(pointerId);
      } catch {
        // Ignore pointer-capture support gaps.
      }

      const onPointerMove = (moveEvent) => {
        if (moveEvent.pointerId !== pointerId) return;
        const delta = startY - Number(moveEvent.clientY || startY);
        const next = applyMediaStripHeightPx(startHeight + delta, { persist: false });
        setHandleValue(next);
      };

      const stopResize = (finalEvent) => {
        if (finalEvent.pointerId !== pointerId) return;
        window.removeEventListener('pointermove', onPointerMove);
        window.removeEventListener('pointerup', stopResize);
        window.removeEventListener('pointercancel', stopResize);
        persistMediaStripHeightPx(state.mediaStripHeightPx);
        try {
          mediaResizeHandle.releasePointerCapture(pointerId);
        } catch {
          // Ignore pointer-capture support gaps.
        }
      };

      window.addEventListener('pointermove', onPointerMove);
      window.addEventListener('pointerup', stopResize);
      window.addEventListener('pointercancel', stopResize);
    };
  }

  const centerBlockInEditor = (node, editorNode = null, behavior = 'smooth') => {
    const targetEditor = editorNode || document.getElementById('cw-editor');
    if (!targetEditor || !node) return;
    const editorRect = targetEditor.getBoundingClientRect();
    const blockRect = node.getBoundingClientRect();
    const blockOffsetInEditor = blockRect.top - editorRect.top + targetEditor.scrollTop;
    const targetTop = blockOffsetInEditor - (targetEditor.clientHeight / 2) + (blockRect.height / 2);
    targetEditor.scrollTo({
      top: Math.max(0, targetTop),
      behavior,
    });
  };

  if (mediaNode) {
    let lastTimeSyncMs = 0;
    let playbackFollowRaf = null;
    const clearPlaybackFollowPending = () => {
      if (!state.playbackFollowPending) return;
      state.playbackFollowPending = false;
      syncStatusMessageNodes();
    };
    const evaluateSeekWarmupResume = ({ activeNodePresent = false, forceTimeout = false } = {}) => {
      if (!state.seekResumePending) return;
      const readiness = resolveSeekWarmupReadiness({
        rangeStart: Number(state.virtualRange.start || 0),
        rangeEnd: Number(state.virtualRange.end || 0),
        activeIndex: state.seekWarmupTargetIndex,
        totalSegments: state.segments.length,
        lookahead: SEEK_WARMUP_LOOKAHEAD,
      });
      const nowMs = forceTimeout ? Number(state.seekResumeDeadlineMs || Date.now()) : Date.now();
      const resumeDecision = resolveSeekPlaybackResumeDecision({
        wasPlaying: state.seekResumeWasPlaying,
        isWarmupReady: readiness.isReady && activeNodePresent,
        nowMs,
        resumeDeadlineMs: state.seekResumeDeadlineMs,
      });
      if (!resumeDecision.shouldFinalize) return;
      const shouldResumePlayback = resumeDecision.shouldResume;
      resetSeekWarmupState();
      clearPlaybackFollowPending();
      if (shouldResumePlayback) {
        void mediaNode.play().catch(() => {
          // Browser policies may block autoplay; keep UI responsive.
        });
      }
    };
    const scheduleSeekResumeTimeout = () => {
      if (!state.seekResumePending) return;
      clearSeekResumeTimer();
      const delay = Math.max(0, Number(state.seekResumeDeadlineMs || 0) - Date.now());
      state.seekResumeTimerId = window.setTimeout(() => {
        state.seekResumeTimerId = null;
        evaluateSeekWarmupResume({ activeNodePresent: false, forceTimeout: true });
      }, delay);
    };
    const schedulePlaybackFollowRender = (segmentId, targetScrollTop, options = {}) => {
      const mode = String(options.mode || 'tick');
      if (mode === 'seek' && options.seekRange) {
        state.seekForcedRange = options.seekRange;
      }
      state.playbackFollowPending = true;
      syncStatusMessageNodes();
      state.editorScrollTop = Math.max(0, Number(targetScrollTop || 0));
      if (playbackFollowRaf) {
        window.cancelAnimationFrame(playbackFollowRaf);
        playbackFollowRaf = null;
      }
      playbackFollowRaf = window.requestAnimationFrame(() => {
        playbackFollowRaf = null;
        render();
        const refreshedEditor = document.getElementById('cw-editor');
        if (refreshedEditor) {
          refreshedEditor.scrollTop = Math.max(0, Number(state.editorScrollTop || 0));
        }
        const activeNode = refreshedEditor?.querySelector(`[data-segment-id="${CSS.escape(String(segmentId))}"]`);
        if (activeNode) {
          centerBlockInEditor(activeNode, refreshedEditor, 'auto');
        }
        if (mode === 'seek') {
          evaluateSeekWarmupResume({ activeNodePresent: Boolean(activeNode), forceTimeout: false });
          if (state.seekResumePending) {
            scheduleSeekResumeTimeout();
            return;
          }
          state.seekForcedRange = null;
        }
        clearPlaybackFollowPending();
      });
    };
    const syncActiveFromMedia = (mode = 'tick') => {
      const seekMode = mode === 'seek';
      const detectedIndex = findActiveSegmentIndex({ segments: state.segments, currentTime: mediaNode.currentTime });
      const nextIndex = seekMode
        ? resolveGapSeekTargetIndex({
          segments: state.segments,
          currentTime: mediaNode.currentTime,
          activeIndex: detectedIndex,
        })
        : detectedIndex;
      const segmentChanged = nextIndex !== state.activeSegmentIndex;
      const activeEditor = document.getElementById('cw-editor') || editor;
      if (segmentChanged) {
        state.activeSegmentIndex = nextIndex;
        syncActiveBlockHighlight(activeEditor);
      }
      if (nextIndex < 0) {
        state.playbackFollowAnchorSegmentId = null;
        resetSeekWarmupState();
        clearPlaybackFollowPending();
        return;
      }
      const segment = state.segments[nextIndex];
      if (!segment) return;
      const segmentId = String(segment.segment_id);
      state.playbackFollowAnchorSegmentId = segmentId;
      if (seekMode && String(state.selectedSegmentId || '') !== segmentId) {
        state.selectedSegmentId = segmentId;
        syncSelectedBlockHighlight(activeEditor);
        syncSpeakerReassignMeta();
      }
      const node = activeEditor?.querySelector(`[data-segment-id="${CSS.escape(segmentId)}"]`);
      const followDecision = resolvePlaybackFollowDecision({
        activeIndex: nextIndex,
        rangeStart: Number(state.virtualRange.start || 0),
        rangeEnd: Number(state.virtualRange.end || 0),
        followPending: state.playbackFollowPending,
        nowMs: Date.now(),
        lastFollowMs: state.lastPlaybackFollowMs,
        throttleMs: 200,
        editorClientHeight: state.editorClientHeight,
        rowHeight: VIRTUAL_ROW_HEIGHT,
      });
      state.lastPlaybackFollowMs = Number(followDecision.nextFollowMs || state.lastPlaybackFollowMs || 0);

      if (seekMode) {
        state.seekWarmupTargetIndex = nextIndex;
        state.seekWarmupTargetSegmentId = segmentId;
        const warmupRange = resolveSeekWarmupRange({
          activeIndex: nextIndex,
          totalSegments: state.segments.length,
          lookahead: SEEK_WARMUP_LOOKAHEAD,
          overscan: VIRTUAL_OVERSCAN,
        });
        const warmupReadiness = resolveSeekWarmupReadiness({
          rangeStart: Number(state.virtualRange.start || 0),
          rangeEnd: Number(state.virtualRange.end || 0),
          activeIndex: nextIndex,
          totalSegments: state.segments.length,
          lookahead: SEEK_WARMUP_LOOKAHEAD,
        });
        const requiresSeekShift = !node || !warmupReadiness.isReady;
        if (requiresSeekShift && warmupRange) {
          const currentlyPlaying = !mediaNode.paused;
          if (!state.seekResumePending) {
            state.seekResumeWasPlaying = currentlyPlaying;
            state.seekResumePending = true;
          } else if (currentlyPlaying) {
            state.seekResumeWasPlaying = true;
          }
          state.seekResumeDeadlineMs = Date.now() + SEEK_WARMUP_TIMEOUT_MS;
          clearSeekResumeTimer();
          if (currentlyPlaying) {
            try {
              mediaNode.pause();
            } catch {
              // Ignore pause errors.
            }
          }
          const targetScrollTop = resolveEditorScrollTopForIndex(nextIndex);
          schedulePlaybackFollowRender(segmentId, targetScrollTop, {
            mode: 'seek',
            seekRange: warmupRange,
          });
          return;
        }
        state.seekForcedRange = null;
        evaluateSeekWarmupResume({ activeNodePresent: Boolean(node), forceTimeout: false });
        clearPlaybackFollowPending();
        if (segmentChanged && node) {
          centerBlockInEditor(node, activeEditor, 'auto');
        }
        return;
      }

      if (segmentChanged && node) {
        clearPlaybackFollowPending();
        centerBlockInEditor(node, activeEditor, 'auto');
      } else if (segmentChanged && followDecision.shouldShift) {
        schedulePlaybackFollowRender(segmentId, resolveEditorScrollTopForIndex(nextIndex), { mode: 'tick' });
      }
    };
    mediaNode.ontimeupdate = () => {
      const now = Date.now();
      if (now - lastTimeSyncMs < 120) return;
      lastTimeSyncMs = now;
      state.lastPlaybackTickMs = now;
      syncActiveFromMedia('tick');
    };
    mediaNode.onseeking = () => syncActiveFromMedia('seek');
    mediaNode.onseeked = () => syncActiveFromMedia('seek');
    mediaNode.onloadedmetadata = () => syncActiveFromMedia('seek');
  }

  const commitButton = document.getElementById('cw-commit');
  if (commitButton) {
    commitButton.onclick = async () => {
      try {
        await flushDirtyTextOperations('Draft synchronisiert', {
          returnMode: 'changed_segments',
          renderAfter: true,
        });
        const result = await callApi(`/api/v1/jobs/${state.jobId}/transcript/correction-sessions/${state.sessionId}/commit`, {
          method: 'POST',
          body: JSON.stringify({ base_version: state.baseVersion, edit_reason: 'Manueller Commit aus Korrekturmodus' }),
        });
        state.baseVersion = Number(result.version ?? state.baseVersion);
        state.workingVersion = state.baseVersion;
        resetDirtyState();
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
        await flushDirtyTextOperations('Draft gespeichert', {
          returnMode: 'changed_segments',
          renderAfter: true,
        });
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
      resetDirtyState();
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
  state.isBootstrapping = true;
  state.bootstrapError = '';
  state.bootstrapPhase = 'boot';
  const bootstrapTheme = String(bootstrap.theme || '').trim();
  let storedTheme = 'light';
  try {
    storedTheme = localStorage.getItem(THEME_STORAGE_KEY) || 'light';
  } catch {
    storedTheme = 'light';
  }
  const persistedTheme = bootstrapTheme || storedTheme;
  setTheme(persistedTheme === 'dark' ? 'dark' : 'light');
  applyMediaStripHeightPx(state.mediaStripHeightPx, { persist: false });
  render();

  try {
    let mediaLoadErrorMessage = '';
    state.bootstrapPhase = 'media';
    render();
    try {
      state.mediaSource = await callApi(`/api/v1/jobs/${state.jobId}/media-source`);
    } catch (mediaError) {
      state.mediaSource = null;
      mediaLoadErrorMessage = `Medienquelle konnte nicht geladen werden: ${mediaError.message}`;
    }

    state.bootstrapPhase = 'transcript';
    render();
    const transcript = await callApi(`/api/v1/jobs/${state.jobId}/transcript`);
    state.baseVersion = Number(transcript.version ?? 1);
    state.reviewStatus = String(transcript.review_status ?? 'in_review');
    state.isFinal = Boolean(transcript.is_final ?? false);

    state.bootstrapPhase = 'session';
    render();
    const session = await callApi(`/api/v1/jobs/${state.jobId}/transcript/correction-sessions`, {
      method: 'POST',
      body: JSON.stringify({
        base_version: state.baseVersion,
        autosave_enabled: false,
        force_reseed_from_transcript: true,
      }),
    });

    patchStateFromSession(session);
    resetDirtyState();
    state.isBootstrapping = false;
    state.bootstrapError = '';
    setStatus(mediaLoadErrorMessage || 'Korrektursitzung gestartet');
    render();
  } catch (error) {
    state.isBootstrapping = true;
    state.bootstrapError = String(error?.message || 'unknown_error');
    render();
  }
}

window.addEventListener('beforeunload', (event) => {
  if (!state.hasUnsavedChanges) return;
  event.preventDefault();
  event.returnValue = '';
});

void init();
