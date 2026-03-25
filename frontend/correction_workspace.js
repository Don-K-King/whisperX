import {
  applyReplaceLiteral,
  applySpeakerReassign,
  findActiveSegmentIndex,
  formatTimestamp,
  mergeConsecutiveSpeakerBlocks,
  normalizeSegments,
} from './correction_utils.js';
import { consumeCorrectionHandoff } from './correction_handoff.js';
import {
  buildSpeakerDisplayLabel,
  buildSpeakerOptionEntries,
  parseSidebarVisibility,
} from './correction_workspace_viewmodel.js';

const THEME_STORAGE_KEY = 'evodox-theme';
const SIDEBAR_VISIBILITY_STORAGE_KEY = 'evodox-correction-sidebar-visible';

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
};

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

function markUnsavedChanges() {
  state.hasUnsavedChanges = true;
}

function clearUnsavedChanges() {
  state.hasUnsavedChanges = false;
}

function getMediaElement() {
  return document.querySelector('[data-media-player]');
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
    return `
      <article class="cw-block ${activeClass} ${selectedClass}" data-segment-id="${escapeHtml(segment.segment_id)}">
        <header class="cw-block-header">
          <strong class="cw-block-speaker">${escapeHtml(speakerLabel)}</strong>
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
  const speakerOptions = getSpeakerOptions()
    .map((entry) => `<option value="${escapeHtml(entry.key)}">${escapeHtml(entry.label)}</option>`)
    .join('');
  const theme = document.body.dataset.theme === 'dark' ? 'dark' : 'light';
  const mediaNode = renderMediaNode();
  const sidebarToggleLabel = state.sidebarVisible ? 'Statusfenster ausblenden' : 'Statusfenster einblenden';
  const layoutClass = state.sidebarVisible ? 'cw-layout' : 'cw-layout cw-layout--sidebar-hidden';

  app.innerHTML = `
    <section class="cw-root">
      <header class="cw-topbar">
        <strong>Korrekturmodus</strong>
        <span class="badge">Job: ${escapeHtml(state.jobId)}</span>
        <span class="badge">Base v${state.baseVersion}</span>
        <span class="badge">Working v${state.workingVersion}</span>
        <span class="badge">Review: ${escapeHtml(state.reviewStatus)}</span>
        <span class="badge">Final: ${state.isFinal ? 'Ja' : 'Nein'}</span>
        <button id="cw-save" class="primary">Manuell speichern</button>
        <button id="cw-commit" class="primary">Version committen</button>
        <button id="cw-discard" class="danger">Verwerfen</button>
        <button id="cw-undo">Undo</button>
        <button id="cw-redo">Redo</button>
        <button id="cw-sidebar-toggle">${sidebarToggleLabel}</button>
        <button id="cw-theme-toggle">Theme: ${theme === 'dark' ? 'Dark' : 'Light'}</button>
        <button id="cw-close">Fenster schliessen</button>
        <label>
          <input id="cw-autosave" type="checkbox" ${state.autosaveEnabled ? 'checked' : ''} /> Autosave Draft
        </label>
      </header>
      <section class="${layoutClass}">
        <section class="cw-editor" id="cw-editor">${renderEditorBlocks()}</section>
        ${state.sidebarVisible ? `
        <aside class="cw-sidebar">
          <section>
            <h3>Status</h3>
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
          </section>

          <section>
            <h3>Suche & Ersetzen</h3>
            <input id="cw-search-query" placeholder="Suche" value="${escapeHtml(state.searchQuery)}" />
            <select id="cw-search-speaker">
              <option value="">Alle Sprecher</option>
              ${speakerOptions}
            </select>
            <input id="cw-replace-query" placeholder="Ersetze" value="${escapeHtml(state.replaceQuery)}" />
            <input id="cw-replace-value" placeholder="Durch" value="${escapeHtml(state.replaceValue)}" />
            <button id="cw-replace-one">Ersetze eins</button>
            <button id="cw-replace-all" class="primary">Ersetze alle</button>
          </section>

          <section>
            <h3>Sprecherumteilung</h3>
            <select id="cw-reassign-segment">
              ${state.segments.map((segment) => {
                const speakerLabel = buildSpeakerDisplayLabel({
                  speakerKey: segment.speaker,
                  speakerLabels: state.speakerLabels,
                });
                const timeRange = `${formatTimestamp(segment.start)} - ${formatTimestamp(segment.end)}`;
                return `<option value="${escapeHtml(segment.segment_id)}">${escapeHtml(`${speakerLabel} | ${timeRange}`)}</option>`;
              }).join('')}
            </select>
            <select id="cw-reassign-speaker">
              ${speakerOptions}
            </select>
            <input id="cw-reassign-start" type="number" min="0" placeholder="Start-Char (optional)" />
            <input id="cw-reassign-end" type="number" min="0" placeholder="End-Char (optional)" />
            <button id="cw-reassign-apply">Sprecher anwenden</button>
          </section>

          <section>
            <h3>Aenderungslog</h3>
            ${renderOperationLog()}
          </section>

          <p id="cw-status-message" class="cw-status">${escapeHtml(state.statusMessage)}</p>
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
  return mergeConsecutiveSpeakerBlocks(updated);
}

async function applySegments(segments, message = 'Aenderungen gespeichert') {
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
  state.segments = mergeConsecutiveSpeakerBlocks(normalizeSegments(payload.segments ?? []));
  state.operationLog = Array.isArray(payload.operation_log) ? payload.operation_log : [];
  state.reviewStatus = String(payload.review_status ?? state.reviewStatus);
  state.isFinal = Boolean(payload.is_final ?? state.isFinal);
  if (!state.segments.some((segment) => String(segment.segment_id) === String(state.selectedSegmentId))) {
    state.selectedSegmentId = state.segments[0]?.segment_id || null;
  }
}

function bindInteractions() {
  const editor = document.getElementById('cw-editor');
  if (editor) {
    editor.querySelectorAll('[data-text-input]').forEach((node) => {
      node.addEventListener('input', () => {
        scheduleAutosave();
      });
    });
    editor.querySelectorAll('.cw-block').forEach((blockNode) => {
      blockNode.addEventListener('click', () => {
        state.selectedSegmentId = String(blockNode.dataset.segmentId || '');
        editor.querySelectorAll('.cw-block.selected').forEach((node) => node.classList.remove('selected'));
        blockNode.classList.add('selected');
        const targetSelect = document.getElementById('cw-reassign-segment');
        if (targetSelect) targetSelect.value = state.selectedSegmentId;
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

  const autosaveNode = document.getElementById('cw-autosave');
  if (autosaveNode) {
    autosaveNode.onchange = async () => {
      state.autosaveEnabled = Boolean(autosaveNode.checked);
      try {
        const result = await callApi(`/api/v1/jobs/${state.jobId}/transcript/correction-sessions/${state.sessionId}`, {
          method: 'PATCH',
          body: JSON.stringify({ autosave_enabled: state.autosaveEnabled }),
        });
        patchStateFromSession(result);
        setStatus('Autosave aktualisiert');
        render();
      } catch (error) {
        setStatus(`Autosave konnte nicht gespeichert werden: ${error.message}`);
      }
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
      const segmentNode = document.getElementById('cw-reassign-segment');
      const speakerSelectNode = document.getElementById('cw-reassign-speaker');
      const startNode = document.getElementById('cw-reassign-start');
      const endNode = document.getElementById('cw-reassign-end');
      const segmentId = String(segmentNode?.value ?? '');
      const speaker = String(speakerSelectNode?.value ?? '');
      const startChar = startNode?.value === '' ? null : Number(startNode?.value);
      const endChar = endNode?.value === '' ? null : Number(endNode?.value);

      const next = applySpeakerReassign({
        segments: collectSegmentsFromDom(),
        segmentId,
        speaker,
        startChar,
        endChar,
      });
      if (!next.changed) {
        setStatus('Sprecherumteilung konnte nicht angewendet werden');
        return;
      }
      try {
        await applySegments(next.segments, 'Sprecherumteilung gespeichert');
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
    mediaNode.ontimeupdate = () => {
      const nextIndex = findActiveSegmentIndex({ segments: state.segments, currentTime: mediaNode.currentTime });
      if (nextIndex === state.activeSegmentIndex) return;
      state.activeSegmentIndex = nextIndex;
      const currentElement = document.querySelector('.cw-block.active');
      if (currentElement) currentElement.classList.remove('active');
      if (nextIndex >= 0) {
        const segment = state.segments[nextIndex];
        const node = document.querySelector(`[data-segment-id="${CSS.escape(String(segment.segment_id))}"]`);
        if (node) {
          node.classList.add('active');
          centerBlockInEditor(node);
        }
      }
    };
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

  const selectedSegmentNode = document.getElementById('cw-reassign-segment');
  if (selectedSegmentNode) {
    if (state.selectedSegmentId) {
      selectedSegmentNode.value = String(state.selectedSegmentId);
    }
    selectedSegmentNode.onchange = () => {
      state.selectedSegmentId = String(selectedSegmentNode.value || '');
      if (editor) {
        editor.querySelectorAll('.cw-block.selected').forEach((node) => node.classList.remove('selected'));
        const active = editor.querySelector(`[data-segment-id="${CSS.escape(state.selectedSegmentId)}"]`);
        if (active) active.classList.add('selected');
      }
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
      body: JSON.stringify({ base_version: state.baseVersion, autosave_enabled: false }),
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
