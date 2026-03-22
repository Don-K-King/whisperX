import {
  buildCompleteUploadPayload,
  mapTranscriptToSpeakerRows,
  parseToken,
  sanitizedError,
} from './utils.js';

const state = {
  lang: 'de',
  theme: 'light',
  auth: null,
  route: 'login',
  jobs: [],
  selectedFile: null,
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
    throw body;
  }
  return response.json();
}

function bindTopbar() {
  document.getElementById('tenant-badge').textContent = `Tenant: ${state.auth?.tenant_id ?? '-'}`;
  document.getElementById('theme-toggle').textContent = `Theme: ${state.theme === 'dark' ? t('dark') : t('light')}`;
  const auditButton = document.getElementById('audit-nav');
  auditButton.hidden = !(state.auth?.roles ?? []).includes('admin');

  document.querySelectorAll('.nav-link').forEach((button) => {
    button.onclick = () => { state.route = button.dataset.route; void loadRoute(); };
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
      render();
      void loadRoute();
    };
  }
}

function jobCard(job) {
  return `
    <article class="card">
      <h3>${job.filename ?? job.job_id.slice(0, 10)}</h3>
      <p>Status: ${job.status}</p>
      <div class="progress"><span style="width:${job.progress}%"></span></div>
      <p><small>Retention: ${job.retention_months ?? '-'}</small></p>
      <button class="btn-secondary" data-open="${job.job_id}">Open</button>
    </article>
  `;
}

async function loadRoute() {
  const app = document.getElementById('app');
  if (!state.auth) return;

  if (state.route === 'dashboard') {
    try {
      const response = await callApi('/api/v1/jobs');
      state.jobs = response.jobs ?? [];
      app.innerHTML = `<h1>${t('dashboard')}</h1><p>${t('jobsub')}</p><div class="card-grid">${state.jobs.map(jobCard).join('')}</div>`;
      document.querySelectorAll('[data-open]').forEach((button) => {
        button.onclick = async () => {
          state.route = `job:${button.dataset.open}`;
          await loadRoute();
        };
      });
    } catch (problem) {
      app.innerHTML = `<p class="error">${sanitizedError(problem)}</p>`;
    }
    return;
  }

  if (state.route === 'new-job') {
    app.innerHTML = `
      <h1>${t('newjob')}</h1>
      <div class="dropzone"><input id="file-input" type="file" accept="audio/*,video/*" /></div>
      <div class="input-row"><label>${t('retention')}</label><input value="12" readonly /></div>
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
      const created = await callApi('/api/v1/jobs', {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({
          filename: state.selectedFile.name,
          content_type: state.selectedFile.type || 'application/octet-stream',
          size_bytes: state.selectedFile.size,
          retention_months: 12,
        }),
      });
      await callApi(`/api/v1/jobs/${created.job_id}/complete-upload`, {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify(buildCompleteUploadPayload({
          tenantId: state.auth.tenant_id,
          jobId: created.job_id,
          filename: state.selectedFile.name,
          uploadSessionId: created.upload.session_id,
          checksumSha256: 'a'.repeat(64),
        })),
      });
      state.route = `job:${created.job_id}`;
      await loadRoute();
    };
    return;
  }

  if (state.route.startsWith('job:')) {
    const jobId = state.route.split(':')[1];
    try {
      const job = await callApi(`/api/v1/jobs/${jobId}`);
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
        <div class="progress"><span style="width:${job.progress}%"></span></div>
        <ol><li>created</li><li>uploaded</li><li>queued</li><li>processing</li><li>completed</li></ol>
        <details><summary>${t('errors')}</summary><p class="error" id="job-error"></p></details>
        ${transcriptPanel}
      `;
    } catch (problem) {
      app.innerHTML = `<p class="error">${sanitizedError(problem)}</p>`;
    }
    return;
  }

  if (state.route === 'audit') {
    if (!(state.auth.roles ?? []).includes('admin')) {
      app.innerHTML = `<p>${t('notauth')}</p>`;
      return;
    }
    try {
      const response = await callApi('/api/v1/audit');
      app.innerHTML = `<h1>${t('audit')}</h1><ul>${(response.events ?? []).map((event) => `<li>${event.tenant_id} · ${event.actor_id ?? 'n/a'} · ${event.correlation_id ?? 'n/a'}</li>`).join('')}</ul>`;
    } catch (problem) {
      app.innerHTML = `<p class="error">${sanitizedError(problem)}</p>`;
    }
  }
}

render();
void loadRoute();
