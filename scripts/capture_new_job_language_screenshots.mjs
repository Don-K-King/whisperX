import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, '..', 'frontend');
const outDir = path.resolve(__dirname, '..', 'docs', 'testing', 'screenshots');
fs.mkdirSync(outDir, { recursive: true });

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
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
await new Promise((resolve) => server.listen(4174, '127.0.0.1', resolve));

async function attachRoutes(page) {
  await page.route('**/api/v1/jobs**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ jobs: [] }),
    });
  });
}

async function loginAndOpenNewJob(page) {
  await page.goto('http://127.0.0.1:4174/', { waitUntil: 'networkidle' });
  await page.fill('#token-input', 'dev:tenant-a:admin:tester');
  await page.click('#signin');
  await page.click('button[data-route="new-job"]');
  await page.waitForSelector('#language-select');
}

const browser = await chromium.launch({ headless: true });

const desktop = await browser.newContext({ viewport: { width: 1366, height: 900 } });
const page = await desktop.newPage();
await attachRoutes(page);
await loginAndOpenNewJob(page);
await page.screenshot({ path: path.join(outDir, 'new-job-language-default.png'), fullPage: true });
await desktop.close();

const mobile = await browser.newContext({ viewport: { width: 390, height: 844 } });
const mobilePage = await mobile.newPage();
await attachRoutes(mobilePage);
await loginAndOpenNewJob(mobilePage);
await mobilePage.screenshot({ path: path.join(outDir, 'new-job-language-responsive.png'), fullPage: true });
await mobile.close();

await browser.close();
await new Promise((resolve) => server.close(resolve));
console.log('screenshots generated at', outDir);
