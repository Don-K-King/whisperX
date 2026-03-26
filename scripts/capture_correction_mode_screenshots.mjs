import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, '..', 'frontend');
const requireFromFrontend = createRequire(path.join(root, 'package.json'));
const { chromium } = requireFromFrontend('playwright');
const outDir = path.resolve(__dirname, '..', 'docs', 'testing', 'screenshots');
fs.mkdirSync(outDir, { recursive: true });

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
};

function serveFile(req, res) {
  const raw = req.url.split('?')[0];
  const rel = raw === '/' ? '/index.html' : raw;
  const filePath = path.normalize(path.join(root, rel));
  if (!filePath.startsWith(root)) {
    res.writeHead(403);
    res.end('forbidden');
    return;
  }
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end('not found');
      return;
    }
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
    res.end(data);
  });
}

const server = http.createServer(serveFile);
await new Promise((resolve) => server.listen(4175, '127.0.0.1', resolve));

let currentSession = {
  session_id: 'cs_1',
  job_id: 'job_1',
  base_version: 3,
  working_version: 3,
  autosave_enabled: false,
  history_index: 0,
  segments: [
    { segment_id: 'seg_1', start: 0, end: 3, speaker: 'SPEAKER_01', text: 'Hallo zusammen.' },
    { segment_id: 'seg_2', start: 3, end: 6, speaker: 'SPEAKER_02', text: 'Vielen Dank.' },
  ],
  speaker_labels: { SPEAKER_01: 'Alice', SPEAKER_02: 'Bob' },
  operation_log: [],
  review_status: 'in_review',
  is_final: false,
};

async function attachRoutes(page) {
  await page.route('**/api/v1/jobs/job_1/transcript', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          job_id: 'job_1',
          version: 3,
          segments: currentSession.segments,
          speaker_labels: currentSession.speaker_labels,
          review_status: currentSession.review_status,
          is_final: currentSession.is_final,
        }),
      });
      return;
    }
    await route.fallback();
  });

  await page.route('**/api/v1/jobs/job_1/transcript/correction-sessions', async (route) => {
    const req = route.request();
    if (req.method() === 'POST') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(currentSession) });
      return;
    }
    await route.fallback();
  });

  await page.route('**/api/v1/jobs/job_1/transcript/correction-sessions/cs_1', async (route) => {
    const req = route.request();
    if (req.method() === 'PATCH') {
      const body = JSON.parse(req.postData() || '{}');
      currentSession = { ...currentSession, autosave_enabled: Boolean(body.autosave_enabled) };
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(currentSession) });
      return;
    }
    await route.fallback();
  });

  await page.route('**/api/v1/jobs/job_1/transcript/correction-sessions/cs_1/operations', async (route) => {
    const req = route.request();
    if (req.method() === 'POST') {
      const body = JSON.parse(req.postData() || '{}');
      const op = body.operations?.[0] || {};
      if (op.type === 'set_segments' && Array.isArray(op.segments)) {
        currentSession = {
          ...currentSession,
          segments: op.segments,
          working_version: currentSession.working_version + 1,
          history_index: currentSession.history_index + 1,
          operation_log: [...currentSession.operation_log, { type: 'set_segments' }],
        };
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(currentSession) });
      return;
    }
    await route.fallback();
  });

  await page.route('**/api/v1/jobs/job_1/transcript/correction-sessions/cs_1/discard', async (route) => {
    currentSession = { ...currentSession, history_index: 0, operation_log: [] };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(currentSession) });
  });

  await page.route('**/api/v1/jobs/job_1/transcript/correction-sessions/cs_1/undo', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(currentSession) });
  });

  await page.route('**/api/v1/jobs/job_1/transcript/correction-sessions/cs_1/redo', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(currentSession) });
  });

  await page.route('**/api/v1/jobs/job_1/transcript/correction-sessions/cs_1/commit', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ job_id: 'job_1', version: 4, saved_at: new Date().toISOString() }) });
  });

  await page.route('**/api/v1/jobs/job_1/transcript/status', async (route) => {
    const req = route.request();
    const body = JSON.parse(req.postData() || '{}');
    currentSession = {
      ...currentSession,
      review_status: body.review_status || currentSession.review_status,
      is_final: Boolean(body.is_final),
    };
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        job_id: 'job_1',
        review_status: currentSession.review_status,
        is_final: currentSession.is_final,
      }),
    });
  });
}

async function openCorrection(page) {
  await page.goto('http://127.0.0.1:4175/correction_workspace.html?handoff=screen', { waitUntil: 'networkidle' });
  await page.evaluate(() => {
    const now = Date.now();
    localStorage.setItem('evodox-correction-handoff:screen', JSON.stringify({
      token: 'dev:tenant-a:reviewer:tester',
      jobId: 'job_1',
      tenantId: 'tenant-a',
      theme: 'light',
      createdAt: now,
      expiresAt: now + (5 * 60 * 1000),
    }));
  });
  await page.goto('http://127.0.0.1:4175/correction_workspace.html?handoff=screen', { waitUntil: 'networkidle' });
  await page.waitForSelector('#cw-save');
}

const browser = await chromium.launch({ headless: true });

const desktop = await browser.newContext({ viewport: { width: 1366, height: 900 } });
const page = await desktop.newPage();
await attachRoutes(page);
await openCorrection(page);
await page.screenshot({ path: path.join(outDir, 'correction-shell-default.png'), fullPage: true });

await page.click('summary:has-text("Suche & Ersetzen")');
await page.fill('#cw-replace-query', 'NichtVorhanden');
await page.fill('#cw-replace-value', 'X');
await page.click('#cw-replace-one');
await page.waitForTimeout(200);
await page.screenshot({ path: path.join(outDir, 'correction-editor-validation-error.png'), fullPage: true });
await desktop.close();

const mobile = await browser.newContext({ viewport: { width: 390, height: 844 } });
const mobilePage = await mobile.newPage();
await attachRoutes(mobilePage);
await openCorrection(mobilePage);
await mobilePage.screenshot({ path: path.join(outDir, 'correction-shell-responsive.png'), fullPage: true });
await mobile.close();

await browser.close();
await new Promise((resolve) => server.close(resolve));
console.log('correction screenshots generated at', outDir);
