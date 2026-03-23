import {
  deriveProgress,
  jobActionsForStatus,
  mapTranscriptToSpeakerAliases,
  mapTranscriptToSpeakerBlocks,
  nextPollingIntervalMs,
  parseToken,
  sanitizedError,
  uploadFileToPresignedUrl,
} from './utils.js';
import { createAndQueueJobUpload } from './upload_flow.js';
import {
  loadTranscriptionSettings,
  saveTranscriptionSettings,
} from './transcription_settings_flow.js';

const TERMINAL_JOB_STATUSES = new Set(['completed', 'failed_terminal', 'deleted', 'canceled']);

const state = {
  lang: 'de',
  theme: 'light',
  auth: null,
  route: 'login',
  jobs: [],
  selectedFile: null,
  uploadProgress: 0,
  pollTimer: null,
  pollIntervalMs: 5000,
};

const i18n = {
  de: {
    login: 'Anmeldung', signin: 'Anmelden', token: 'Bearer Token', dashboard: 'Dashboard', newjob: 'Neuer Job',
    audit: 'Audit', notauth: 'Nicht berechtigt', create: 'Job erstellen', retention: 'Retention (read-only)',
    detail: 'Job-Detail', errors: 'Fehlerdetails', dark: 'Dark', light: 'Light', jobsub: 'Transkriptionsjobs und Fortschritt',
    transcriptionsettings: 'Transcription Settings',
  },
  en: {
    login: 'Login', signin: 'Sign in', token: 'Bearer Token', dashboard: 'Dashboard', newjob: 'New Job',
    audit: 'Audit', notauth: 'Not authorized', create: 'Create job', retention: 'Retention (read-only)',
    detail: 'Job detail', errors: 'Error details', dark: 'Dark', light: 'Light', jobsub: 'Transcription jobs and progress',
    transcriptionsettings: 'Transcription Settings',
  },
};

function t(key) { return i18n[state.lang][key] ?? key; }

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

async function callApi(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${state.auth.token}`,
      ...(options.headers ?? {}),
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw {
      status_code: response.status,
      ...(body ?? {}),
    };
  }

  if (response.status === 204) {
    return {};
  }
  return response.json();
}

function stopPolling() {
  if (state.pollTimer) {
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
}

function isPollableRoute() {
  if (!state.auth) return false;
  return state.route === 'dashboard' || state.route.startsWith('job:');
}

function scheduleNextPoll(statusCode = 200) {
  stopPolling();
  if (!isPollableRoute()) return;

  state.pollIntervalMs = nextPollingIntervalMs({
    currentMs: state.pollIntervalMs,
    statusCode,
  });
  state.pollTimer = setTimeout(() => {
    void loadRoute({ fromPoll: true });
  }, state.pollIntervalMs);
}

function bindTopbar() {
  document.getElementById('tenant-badge').textContent = `Tenant: ${state.auth?.tenant_id ?? '-'}`;
  document.getElementById('theme-toggle').textContent = `Theme: ${state.theme === 'dark' ? t('dark') : t('light')}`;
  const auditButton = document.getElementById('audit-nav');
  const settingsButton = document.getElementById('transcription-settings-nav');
  const isAdmin = (state.auth?.roles ?? []).includes('admin');
  auditButton.hidden = !isAdmin;
  settingsButton.hidden = !isAdmin;

  document.querySelectorAll('.nav-link').forEach((button) => {
    button.onclick = () => {
      state.route = button.dataset.route;
      void loadRoute();
    };
  });
  document.getElementById('theme-toggle').onclick = () => {
    state.theme = state.theme === 'light' ? 'dark' : 'light';
    render();
    void loadRoute();
  };
  document.getElementById('lang-toggle').onclick = () => {
    state.lang = state.lang === 'de' ? 'en' : 'de';
    render();
    void loadRoute();
  };
  document.getElementById('logout').onclick = () => {
    stopPolling();
    state.auth = null;
    state.route = 'login';
    render();
    void loadRoute();
  };
}

function render() {
  document.body.dataset.theme = state.theme;
  bindTopbar();

  if (!state.auth) {
    state.route = 'login';
    document.getElementById('app').innerHTML = `
      <section class="login-card">
        <h1>${t('login')}</h1>
        <div class="input-row">
          <label for="token-input">${t('token')}</label>
          <input id="token-input" placeholder="eyJhbGciOi..." />
        </div>
        <button id="signin">${t('signin')}</button>
        <p id="login-error" class="error"></p>
      </section>
    `;
    document.getElementById('signin').onclick = () => {
      const token = document.getElementById('token-input').value.trim();
      if (!token) {
        document.getElementById('login-error').textContent = 'auth.invalid_token';
        return;
      }
      state.auth = parseToken(token);
      state.route = 'dashboard';
      state.pollIntervalMs = 5000;
      render();
      void loadRoute();
    };
  }
}

function jobCard(job) {
  const progress = deriveProgress(job);
  return `
    <article class="card">
      <h3>${job.filename ?? String(job.job_id ?? '').slice(0, 10)}</h3>
      <p>Status: ${job.status}</p>
      <p><small>Progress: ${progress}%</small></p>
      <div class="progress"><span style="width:${progress}%"></span></div>
      <p><small>Retention: ${job.retention_months ?? '-'}</small></p>
      <button class="btn-secondary" data-open="${job.job_id}">Open</button>
    </article>
  `;
}

function jobTimeline(progress, status) {
  const canceled = status === 'canceled' || status === 'cancel_requested';
  const items = [
    { key: 'queued', label: 'queued', pct: 5 },
    { key: 'processing', label: 'processing', pct: 20 },
    { key: 'asr', label: 'asr-finished', pct: 60 },
    { key: 'diarization', label: 'diarization-finished', pct: 90 },
    { key: 'completed', label: 'completed', pct: 100 },
  ];
  return `
    <ol class="timeline">
      ${items.map((item) => `<li class="${progress >= item.pct ? 'done' : ''}">${item.label} (${item.pct}%)</li>`).join('')}
      <li class="${canceled ? 'done' : ''}">canceled (100%)</li>
    </ol>
  `;
}

function updateUploadProgress(progress) {
  state.uploadProgress = Math.max(0, Math.min(100, Number(progress || 0)));
  const label = document.getElementById('upload-progress');
  const bar = document.getElementById('upload-progress-bar');
  const value = document.getElementById('upload-progress-value');
  if (!label || !bar || !value) return;
  label.textContent = `Upload progress: ${state.uploadProgress}%`;
  bar.hidden = false;
  value.style.width = `${state.uploadProgress}%`;
}

async function loadRoute({ fromPoll = false } = {}) {
  const app = document.getElementById('app');
  if (!state.auth) {
    stopPolling();
    return;
  }
  if (!fromPoll) {
    state.pollIntervalMs = 5000;
    stopPolling();
  }

  if (state.route === 'dashboard') {
    try {
      const response = await callApi('/api/v1/jobs');
      state.jobs = (response.jobs ?? []).map((job) => ({ ...job, progress: deriveProgress(job) }));
      app.innerHTML = `<h1>${t('dashboard')}</h1><p>${t('jobsub')}</p><div class="card-grid">${state.jobs.map(jobCard).join('')}</div>`;
      document.querySelectorAll('[data-open]').forEach((button) => {
        button.onclick = async () => {
          state.route = `job:${button.dataset.open}`;
          await loadRoute();
        };
      });
      scheduleNextPoll(200);
    } catch (problem) {
      app.innerHTML = `<p class="error">${sanitizedError(problem)}</p>`;
      scheduleNextPoll(problem?.status_code ?? 500);
    }
    return;
  }

  if (state.route === 'new-job') {
    stopPolling();
    state.uploadProgress = 0;
    app.innerHTML = `
      <h1>${t('newjob')}</h1>
      <div class="dropzone"><input id="file-input" type="file" accept="audio/*,video/*" /></div>
      <div class="input-row">
        <label for="language-select">Sprache</label>
        <select id="language-select">
          <option value="de" selected>Deutsch (de)</option>
          <option value="auto">Auto</option>
          <option value="en">English (en)</option>
          <option value="fr">Français (fr)</option>
          <option value="es">Español (es)</option>
          <option value="it">Italiano (it)</option>
        </select>
      </div>
      <div class="input-row"><label>${t('retention')}</label><input value="12" readonly /></div>
      <p id="upload-progress">Upload progress: 0%</p>
      <div class="progress" id="upload-progress-bar" hidden><span id="upload-progress-value" style="width:0%"></span></div>
      <button id="create-job">${t('create')}</button>
      <p id="newjob-error" class="error"></p>
    `;
    document.getElementById('file-input').onchange = (event) => {
      state.selectedFile = event.target.files?.[0] ?? null;
      if (state.selectedFile && state.selectedFile.size > 21474836480) {
        state.selectedFile = null;
        document.getElementById('newjob-error').textContent = 'job.validation.size_bytes';
      }
    };
    document.getElementById('create-job').onclick = async () => {
      if (!state.selectedFile) {
        document.getElementById('newjob-error').textContent = 'job.validation.file_missing';
        return;
      }
      const createButton = document.getElementById('create-job');
      createButton.disabled = true;
      document.getElementById('newjob-error').textContent = '';
      try {
        const queued = await createAndQueueJobUpload({
          callApi,
          uploadFileToPresignedUrl,
          tenantId: state.auth.tenant_id,
          file: state.selectedFile,
          language: String(document.getElementById('language-select')?.value ?? 'de'),
          retentionMonths: 12,
          idempotencyKeyFactory: () => crypto.randomUUID(),
          onUploadProgress: (progress) => updateUploadProgress(progress),
        });
        updateUploadProgress(100);
        state.route = `job:${queued.jobId}`;
        await loadRoute();
      } catch (problem) {
        document.getElementById('newjob-error').textContent = sanitizedError(problem);
      } finally {
        createButton.disabled = false;
      }
    };
    return;
  }

  if (state.route.startsWith('job:')) {
    const jobId = state.route.split(':')[1];
    try {
      const job = await callApi(`/api/v1/jobs/${jobId}`);
      const progress = deriveProgress(job);
      const actions = jobActionsForStatus(job.status);
      let transcriptPanel = '';
      let bindTranscriptInteractions = () => {};
      if (job.status === 'completed') {
        try {
          const transcript = await callApi(`/api/v1/jobs/${jobId}/transcript`);
          const blocks = mapTranscriptToSpeakerBlocks(transcript);
          const aliases = mapTranscriptToSpeakerAliases(transcript);
          const transcriptVersion = Number(transcript?.version ?? 1);
          transcriptPanel = `
            <section class="card">
              <h2>Transcript v${transcriptVersion}</h2>
              <div class="card">
                <h3>Speaker labels</h3>
                ${aliases.map((entry, index) => `
                  <div class="input-row">
                    <label for="speaker-alias-${index}">${escapeHtml(entry.speakerKey)}</label>
                    <input id="speaker-alias-${index}" value="${escapeHtml(entry.alias)}" />
                  </div>
                `).join('')}
                <button id="save-speaker-labels" class="btn-secondary">Save speaker labels</button>
                <p id="speaker-labels-status"></p>
              </div>
              <ul class="transcript-list">
                ${blocks.map((block) => `
                  <li>
                    <strong>${escapeHtml(block.speaker)}</strong>
                    <small>${escapeHtml(block.timeRange)}</small>
                    <p>${escapeHtml(block.text).replaceAll('\n', '<br />')}</p>
                  </li>
                `).join('')}
              </ul>
            </section>
          `;
          bindTranscriptInteractions = () => {
            const saveSpeakerLabels = async () => {
              const payload = {};
              aliases.forEach((entry, index) => {
                const inputNode = document.getElementById(`speaker-alias-${index}`);
                if (!inputNode) return;
                const value = String(inputNode.value ?? '').trim();
                if (value.length === 0) return;
                payload[entry.speakerKey] = value;
              });
              try {
                await callApi(`/api/v1/jobs/${jobId}/transcript/speaker-labels`, {
                  method: 'PUT',
                  body: JSON.stringify({
                    base_version: transcriptVersion,
                    speaker_labels: payload,
                    edit_reason: 'Speaker labels updated',
                  }),
                });
                const statusNode = document.getElementById('speaker-labels-status');
                if (statusNode) statusNode.textContent = 'saved';
                await loadRoute();
              } catch (problem) {
                const statusNode = document.getElementById('speaker-labels-status');
                if (statusNode) statusNode.textContent = sanitizedError(problem);
                if (problem?.status_code === 409) {
                  await loadRoute();
                }
              }
            };

            const button = document.getElementById('save-speaker-labels');
            if (button) {
              button.onclick = () => {
                void saveSpeakerLabels();
              };
            }
          };
        } catch (problem) {
          transcriptPanel = `<p class="error">${sanitizedError(problem)}</p>`;
        }
      }

      app.innerHTML = `
        <h1>${t('detail')}</h1>
        <p>${jobId}</p>
        <p><strong>Status:</strong> ${job.status}</p>
        <p><strong>Progress:</strong> ${progress}%</p>
        <div class="progress"><span style="width:${progress}%"></span></div>
        ${jobTimeline(progress, job.status)}
        <div class="action-row">
          ${actions.canPause ? '<button id="pause-job" class="btn-secondary">Pause</button>' : ''}
          ${actions.canResume ? '<button id="resume-job" class="btn-secondary">Resume</button>' : ''}
          ${actions.canCancel ? '<button id="cancel-job" class="btn-danger">Cancel</button>' : ''}
          ${actions.canDelete ? '<button id="delete-job" class="btn-danger">Delete</button>' : ''}
        </div>
        <details><summary>${t('errors')}</summary><p class="error" id="job-error"></p></details>
        ${transcriptPanel}
      `;
      bindTranscriptInteractions();

      const setJobError = (problem) => {
        const errorNode = document.getElementById('job-error');
        if (errorNode) {
          errorNode.textContent = sanitizedError(problem);
        }
      };

      const pauseButton = document.getElementById('pause-job');
      if (pauseButton) {
        pauseButton.onclick = async () => {
          try {
            await callApi(`/api/v1/jobs/${jobId}/pause`, { method: 'POST' });
            await loadRoute();
          } catch (problem) {
            setJobError(problem);
          }
        };
      }

      const resumeButton = document.getElementById('resume-job');
      if (resumeButton) {
        resumeButton.onclick = async () => {
          try {
            await callApi(`/api/v1/jobs/${jobId}/resume`, { method: 'POST' });
            await loadRoute();
          } catch (problem) {
            setJobError(problem);
          }
        };
      }

      const deleteButton = document.getElementById('delete-job');
      if (deleteButton) {
        deleteButton.onclick = async () => {
          if (!window.confirm(`Delete job ${jobId}?`)) return;
          try {
            await callApi(`/api/v1/jobs/${jobId}`, { method: 'DELETE' });
            state.route = 'dashboard';
            await loadRoute();
          } catch (problem) {
            setJobError(problem);
          }
        };
      }

      const cancelButton = document.getElementById('cancel-job');
      if (cancelButton) {
        cancelButton.onclick = async () => {
          if (!window.confirm(`Cancel job ${jobId}?`)) return;
          try {
            await callApi(`/api/v1/jobs/${jobId}/cancel`, { method: 'POST' });
            await loadRoute();
          } catch (problem) {
            setJobError(problem);
          }
        };
      }

      if (TERMINAL_JOB_STATUSES.has(job.status)) {
        stopPolling();
      } else {
        scheduleNextPoll(200);
      }
    } catch (problem) {
      app.innerHTML = `<p class="error">${sanitizedError(problem)}</p>`;
      scheduleNextPoll(problem?.status_code ?? 500);
    }
    return;
  }

  if (state.route === 'audit') {
    stopPolling();
    if (!(state.auth.roles ?? []).includes('admin')) {
      app.innerHTML = `<p>${t('notauth')}</p>`;
      return;
    }
    try {
      const response = await callApi('/api/v1/audit');
      app.innerHTML = `<h1>${t('audit')}</h1><ul>${(response.events ?? []).map((event) => `<li>${event.tenant_id} | ${event.actor_id ?? 'n/a'} | ${event.correlation_id ?? 'n/a'}</li>`).join('')}</ul>`;
    } catch (problem) {
      app.innerHTML = `<p class="error">${sanitizedError(problem)}</p>`;
    }
    return;
  }

  if (state.route === 'transcription-settings') {
    stopPolling();
    if (!(state.auth.roles ?? []).includes('admin')) {
      app.innerHTML = `<p>${t('notauth')}</p>`;
      return;
    }
    try {
      const response = await loadTranscriptionSettings({ callApi });
      const options = response.decoding_options;
      app.innerHTML = `
        <h1>${t('transcriptionsettings')}</h1>
        <div class="card">
          <div class="input-row"><label>temperature</label><input id="ts-temperature" type="number" step="0.01" /></div>
          <div class="input-row"><label>beam_size</label><input id="ts-beam-size" type="number" step="1" /></div>
          <div class="input-row"><label>patience</label><input id="ts-patience" type="number" step="0.01" /></div>
          <div class="input-row"><label>length_penalty</label><input id="ts-length-penalty" type="number" step="0.01" /></div>
          <div class="input-row"><label>compression_ratio_threshold</label><input id="ts-compression-ratio-threshold" type="number" step="0.01" /></div>
          <div class="input-row"><label>logprob_threshold</label><input id="ts-logprob-threshold" type="number" step="0.01" /></div>
          <div class="input-row"><label>no_speech_threshold</label><input id="ts-no-speech-threshold" type="number" step="0.01" /></div>
          <div class="input-row"><label>suppress_tokens</label><input id="ts-suppress-tokens" /></div>
          <div class="input-row"><label>initial_prompt</label><input id="ts-initial-prompt" /></div>
          <div class="input-row"><label>condition_on_previous_text</label><input id="ts-condition-on-previous-text" type="checkbox" /></div>
          <div class="input-row"><label>chunk_size</label><input id="ts-chunk-size" type="number" step="1" /></div>
          <div class="input-row"><label>vad_onset</label><input id="ts-vad-onset" type="number" step="0.001" /></div>
          <div class="input-row"><label>vad_offset</label><input id="ts-vad-offset" type="number" step="0.001" /></div>
          <button id="save-transcription-settings">${t('create')}</button>
          <p id="transcription-settings-status"></p>
        </div>
      `;
      document.getElementById('ts-temperature').value = String(options.temperature);
      document.getElementById('ts-beam-size').value = String(options.beam_size);
      document.getElementById('ts-patience').value = String(options.patience);
      document.getElementById('ts-length-penalty').value = String(options.length_penalty);
      document.getElementById('ts-compression-ratio-threshold').value = String(options.compression_ratio_threshold);
      document.getElementById('ts-logprob-threshold').value = String(options.logprob_threshold);
      document.getElementById('ts-no-speech-threshold').value = String(options.no_speech_threshold);
      document.getElementById('ts-suppress-tokens').value = String(options.suppress_tokens ?? '');
      document.getElementById('ts-initial-prompt').value = String(options.initial_prompt ?? '');
      document.getElementById('ts-condition-on-previous-text').checked = Boolean(options.condition_on_previous_text);
      document.getElementById('ts-chunk-size').value = String(options.chunk_size);
      document.getElementById('ts-vad-onset').value = String(options.vad_onset);
      document.getElementById('ts-vad-offset').value = String(options.vad_offset);

      document.getElementById('save-transcription-settings').onclick = async () => {
        const payload = {
          temperature: document.getElementById('ts-temperature').value,
          beam_size: document.getElementById('ts-beam-size').value,
          patience: document.getElementById('ts-patience').value,
          length_penalty: document.getElementById('ts-length-penalty').value,
          compression_ratio_threshold: document.getElementById('ts-compression-ratio-threshold').value,
          logprob_threshold: document.getElementById('ts-logprob-threshold').value,
          no_speech_threshold: document.getElementById('ts-no-speech-threshold').value,
          suppress_tokens: document.getElementById('ts-suppress-tokens').value,
          initial_prompt: document.getElementById('ts-initial-prompt').value,
          condition_on_previous_text: document.getElementById('ts-condition-on-previous-text').checked,
          chunk_size: document.getElementById('ts-chunk-size').value,
          vad_onset: document.getElementById('ts-vad-onset').value,
          vad_offset: document.getElementById('ts-vad-offset').value,
        };
        try {
          await saveTranscriptionSettings({ callApi, decodingOptions: payload });
          document.getElementById('transcription-settings-status').textContent = 'saved';
        } catch (problem) {
          document.getElementById('transcription-settings-status').textContent = sanitizedError(problem);
        }
      };
    } catch (problem) {
      app.innerHTML = `<p class="error">${sanitizedError(problem)}</p>`;
    }
  }
}

render();
void loadRoute();
