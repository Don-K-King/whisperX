import {
  deriveProgress,
  jobActionsForStatus,
  mapTranscriptToSpeakerRows,
  nextPollingIntervalMs,
  parseToken,
  sanitizedError,
  uploadFileToPresignedUrl,
} from './utils.js';
import { createAndQueueJobUpload } from './upload_flow.js';

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
  },
  en: {
    login: 'Login', signin: 'Sign in', token: 'Bearer Token', dashboard: 'Dashboard', newjob: 'New Job',
    audit: 'Audit', notauth: 'Not authorized', create: 'Create job', retention: 'Retention (read-only)',
    detail: 'Job detail', errors: 'Error details', dark: 'Dark', light: 'Light', jobsub: 'Transcription jobs and progress',
  },
};

function t(key) { return i18n[state.lang][key] ?? key; }

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
  auditButton.hidden = !(state.auth?.roles ?? []).includes('admin');

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

function jobTimeline(progress) {
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
      if (job.status === 'completed') {
        try {
          const transcript = await callApi(`/api/v1/jobs/${jobId}/transcript`);
          const rows = mapTranscriptToSpeakerRows(transcript);
          transcriptPanel = `
            <section class="card">
              <h2>Transcript v${transcript.version}</h2>
              <ul class="transcript-list">
                ${rows.map((row) => `<li><strong>${row.speaker}</strong> <small>${row.timeRange}</small><p>${row.text}</p></li>`).join('')}
              </ul>
            </section>
          `;
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
        ${jobTimeline(progress)}
        <div class="action-row">
          ${actions.canPause ? '<button id="pause-job" class="btn-secondary">Pause</button>' : ''}
          ${actions.canResume ? '<button id="resume-job" class="btn-secondary">Resume</button>' : ''}
          ${actions.canDelete ? '<button id="delete-job" class="btn-danger">Delete</button>' : ''}
        </div>
        <details><summary>${t('errors')}</summary><p class="error" id="job-error"></p></details>
        ${transcriptPanel}
      `;

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
  }
}

render();
void loadRoute();
