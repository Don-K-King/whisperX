import { chromium } from '../frontend/node_modules/playwright/index.mjs';

const UX_THRESHOLDS_MS = Object.freeze({
  instant: 100,
  noticeable: 250,
});

function percentile(sortedValues, p) {
  if (!Array.isArray(sortedValues) || sortedValues.length === 0) return 0;
  const clamped = Math.min(1, Math.max(0, p));
  const index = Math.floor((sortedValues.length - 1) * clamped);
  return sortedValues[index];
}

function summarizeDurations(durations) {
  const sorted = [...durations].sort((a, b) => a - b);
  const sum = sorted.reduce((acc, value) => acc + value, 0);
  return {
    avgMs: sum / Math.max(1, sorted.length),
    p50Ms: percentile(sorted, 0.5),
    p95Ms: percentile(sorted, 0.95),
    p99Ms: percentile(sorted, 0.99),
    maxMs: sorted[sorted.length - 1] || 0,
    over50Count: sorted.filter((value) => value > 50).length,
    over100Count: sorted.filter((value) => value > 100).length,
    over250Count: sorted.filter((value) => value > 250).length,
    samples: sorted.length,
  };
}

function classifyLatency(p95Ms) {
  if (p95Ms <= UX_THRESHOLDS_MS.instant) return 'instant';
  if (p95Ms <= UX_THRESHOLDS_MS.noticeable) return 'noticeable';
  return 'disturbing';
}

function resolveSweetSpot(measurements) {
  const instant = measurements
    .filter((entry) => entry.summary.p95Ms <= UX_THRESHOLDS_MS.instant)
    .sort((a, b) => b.windowSize - a.windowSize)[0];
  if (instant) return instant.windowSize;
  const noticeable = measurements
    .filter((entry) => entry.summary.p95Ms <= UX_THRESHOLDS_MS.noticeable)
    .sort((a, b) => b.windowSize - a.windowSize)[0];
  return noticeable ? noticeable.windowSize : null;
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.setContent(`
    <main style="padding:24px; background:#f5f6f8;">
      <section id="editor" style="height:760px; overflow:auto; border:1px solid #d3d7df; background:#fff;"></section>
    </main>
  `);

  const profileConfig = [
    { id: '15m-normal', totalSegments: 300, textLength: 140 },
    { id: '30m-normal', totalSegments: 600, textLength: 140 },
    { id: '30m-heavy', totalSegments: 600, textLength: 420 },
    { id: '60m-normal', totalSegments: 1200, textLength: 140 },
  ];
  const windowSizes = [20, 30, 40, 50, 60, 80, 100, 120, 160, 220, 300, 450, 600];
  const iterations = 80;

  const rawResults = [];

  for (const profile of profileConfig) {
    const applicableWindowSizes = windowSizes.filter((size) => size <= profile.totalSegments);
    for (const windowSize of applicableWindowSizes) {
      const durations = await page.evaluate(
        ({ totalSegments, textLength, windowSize, iterations }) => {
          const editor = document.getElementById('editor');
          if (!editor) return [];

          const baseWords = 'lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et dolore magna aliqua';
          const segments = Array.from({ length: totalSegments }, (_, index) => {
            const repeated = Math.max(1, Math.ceil(textLength / baseWords.length));
            const text = `${baseWords} `.repeat(repeated).slice(0, textLength + (index % 17));
            return {
              id: `seg_${String(index + 1).padStart(6, '0')}`,
              text,
              start: index * 3,
              end: (index * 3) + 3,
            };
          });

          const avgRowHeight = 156;
          const durationsLocal = [];
          let cursor = 0;

          for (let i = 0; i < iterations; i += 1) {
            cursor = (cursor + 97) % Math.max(1, totalSegments - windowSize + 1);
            const start = Math.max(0, Math.min(totalSegments - 1, cursor));
            const end = Math.min(totalSegments, start + windowSize);
            const topSpacer = start * avgRowHeight;
            const bottomSpacer = Math.max(0, (totalSegments - end) * avgRowHeight);

            const rows = [];
            for (let row = start; row < end; row += 1) {
              const segment = segments[row];
              rows.push(`
                <article class="cw-block" data-segment-id="${segment.id}" style="padding:8px 10px; border-bottom:1px solid #e4e8ef;">
                  <header style="font-size:12px; margin-bottom:6px;">${segment.start.toFixed(2)} - ${segment.end.toFixed(2)}</header>
                  <textarea data-text-input="${segment.id}" style="width:100%; min-height:72px; resize:none;">${segment.text}</textarea>
                </article>
              `);
            }

            const html = `
              <div style="height:${topSpacer}px"></div>
              ${rows.join('')}
              <div style="height:${bottomSpacer}px"></div>
            `;

            const t0 = performance.now();
            editor.innerHTML = html;
            const textareas = editor.querySelectorAll('textarea[data-text-input]');
            textareas.forEach((node) => {
              node.style.height = 'auto';
              node.style.height = `${Math.max(72, node.scrollHeight)}px`;
            });
            const blocks = editor.querySelectorAll('.cw-block');
            blocks.forEach((node) => {
              void node.getBoundingClientRect().height;
            });
            void editor.scrollHeight;
            durationsLocal.push(performance.now() - t0);
          }
          return durationsLocal;
        },
        {
          totalSegments: profile.totalSegments,
          textLength: profile.textLength,
          windowSize,
          iterations,
        },
      );

      rawResults.push({
        profileId: profile.id,
        totalSegments: profile.totalSegments,
        textLength: profile.textLength,
        windowSize,
        summary: summarizeDurations(durations),
      });
    }
  }

  await browser.close();

  const grouped = new Map();
  for (const entry of rawResults) {
    const key = entry.profileId;
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(entry);
  }

  const report = [];
  for (const [profileId, entries] of grouped.entries()) {
    const sortedEntries = [...entries].sort((a, b) => a.windowSize - b.windowSize);
    const sweetSpot = resolveSweetSpot(sortedEntries);
    report.push({
      profileId,
      totalSegments: sortedEntries[0]?.totalSegments || 0,
      textLength: sortedEntries[0]?.textLength || 0,
      sweetSpotWindowSize: sweetSpot,
      rows: sortedEntries.map((entry) => ({
        windowSize: entry.windowSize,
        p95Ms: Number(entry.summary.p95Ms.toFixed(2)),
        p99Ms: Number(entry.summary.p99Ms.toFixed(2)),
        avgMs: Number(entry.summary.avgMs.toFixed(2)),
        class: classifyLatency(entry.summary.p95Ms),
      })),
    });
  }

  console.log(JSON.stringify({
    generatedAt: new Date().toISOString(),
    iterations,
    thresholdsMs: UX_THRESHOLDS_MS,
    report,
  }, null, 2));
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
