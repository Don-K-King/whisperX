import { formatTimestamp } from './correction_utils.js';

function resolveSpeakerLabel({ speaker = 'UNKNOWN', speakerLabels = {} }) {
  const key = String(speaker ?? 'UNKNOWN').trim() || 'UNKNOWN';
  const alias = String(speakerLabels?.[key] ?? '').trim();
  if (!alias || alias === key) return key;
  return `${alias} (${key})`;
}

function pad(value) {
  return String(value).padStart(2, '0');
}

export function buildCorrectionExportBaseName({ jobId = 'job', createdAt = new Date() }) {
  const date = createdAt instanceof Date ? createdAt : new Date(createdAt);
  const year = date.getUTCFullYear();
  const month = pad(date.getUTCMonth() + 1);
  const day = pad(date.getUTCDate());
  const hours = pad(date.getUTCHours());
  const minutes = pad(date.getUTCMinutes());
  const safeJob = String(jobId || 'job')
    .replaceAll(/[^a-zA-Z0-9_-]/g, '_')
    .slice(0, 60) || 'job';
  return `transcript_${safeJob}_${year}${month}${day}_${hours}${minutes}`;
}

export function buildCorrectionMarkdownExport({
  jobId = '',
  segments = [],
  speakerLabels = {},
  createdAt = new Date(),
}) {
  const iso = (createdAt instanceof Date ? createdAt : new Date(createdAt)).toISOString();
  const lines = [
    `# Korrektur-Export Job ${String(jobId || '-')}`,
    '',
    `- Erstellt: ${iso}`,
    '',
    '## Transkript',
    '',
  ];
  for (let index = 0; index < segments.length; index += 1) {
    const segment = segments[index] || {};
    const label = resolveSpeakerLabel({ speaker: segment.speaker, speakerLabels });
    const start = formatTimestamp(segment.start);
    const end = formatTimestamp(segment.end);
    lines.push(`### Block ${index + 1} - ${label}`);
    lines.push(`- Zeit: ${start} - ${end}`);
    lines.push('');
    lines.push(String(segment.text ?? ''));
    lines.push('');
  }
  return `${lines.join('\n').trimEnd()}\n`;
}

export function buildCorrectionPlainTextExport({
  segments = [],
  speakerLabels = {},
}) {
  const lines = [];
  for (let index = 0; index < segments.length; index += 1) {
    const segment = segments[index] || {};
    const label = resolveSpeakerLabel({ speaker: segment.speaker, speakerLabels });
    const start = formatTimestamp(segment.start);
    const end = formatTimestamp(segment.end);
    lines.push(`[${start} - ${end}] ${label}`);
    lines.push(String(segment.text ?? ''));
    lines.push('');
  }
  return `${lines.join('\n').trimEnd()}\n`;
}

function escapeRtf(value) {
  const input = String(value ?? '');
  let output = '';
  for (const char of input) {
    if (char === '\\') {
      output += '\\\\';
      continue;
    }
    if (char === '{') {
      output += '\\{';
      continue;
    }
    if (char === '}') {
      output += '\\}';
      continue;
    }
    const code = char.codePointAt(0) || 0;
    if (code <= 0x7f) {
      output += char;
      continue;
    }
    output += `\\u${code}?`;
  }
  return output;
}

export function buildCorrectionWordDocument({ title = 'Korrektur-Export', text = '' }) {
  const safeTitle = escapeRtf(title);
  const body = escapeRtf(String(text ?? '')).replaceAll('\n', '\\par ');
  return `{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Calibri;}}\\fs22\\b ${safeTitle}\\b0\\par ${body}}`;
}

function splitWrappedLines(input, width = 92) {
  const lines = [];
  const sourceLines = String(input ?? '').replaceAll('\r\n', '\n').split('\n');
  for (const sourceLine of sourceLines) {
    if (!sourceLine) {
      lines.push('');
      continue;
    }
    const words = sourceLine.split(/\s+/).filter(Boolean);
    let current = '';
    for (const word of words) {
      if (!current) {
        current = word;
        continue;
      }
      const next = `${current} ${word}`;
      if (next.length <= width) {
        current = next;
      } else {
        lines.push(current);
        current = word;
      }
    }
    if (current) lines.push(current);
  }
  return lines;
}

function escapePdfText(value) {
  const normalized = String(value ?? '')
    .replaceAll('\\', '\\\\')
    .replaceAll('(', '\\(')
    .replaceAll(')', '\\)');
  let output = '';
  for (const char of normalized) {
    const code = char.charCodeAt(0);
    output += code >= 32 && code <= 126 ? char : '?';
  }
  return output;
}

export function buildSimplePdfFromPlainText(text) {
  const wrapped = splitWrappedLines(text, 92);
  const linesPerPage = 52;
  const pageChunks = [];
  for (let cursor = 0; cursor < wrapped.length; cursor += linesPerPage) {
    pageChunks.push(wrapped.slice(cursor, cursor + linesPerPage));
  }
  if (pageChunks.length === 0) pageChunks.push(['']);

  const objects = new Map();
  const catalogObj = 1;
  const pagesObj = 2;
  const fontObj = 3 + (pageChunks.length * 2);

  const pageRefs = [];
  for (let index = 0; index < pageChunks.length; index += 1) {
    const pageObj = 3 + (index * 2);
    const contentObj = pageObj + 1;
    pageRefs.push(`${pageObj} 0 R`);
    const contentLines = pageChunks[index]
      .map((line, lineIndex) => {
        if (lineIndex === 0) {
          return `40 800 Td (${escapePdfText(line)}) Tj`;
        }
        return `0 -14 Td (${escapePdfText(line)}) Tj`;
      })
      .join('\n');
    const stream = `BT\n/F1 11 Tf\n${contentLines}\nET`;
    objects.set(contentObj, `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
    objects.set(pageObj, `<< /Type /Page /Parent ${pagesObj} 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 ${fontObj} 0 R >> >> /Contents ${contentObj} 0 R >>`);
  }

  objects.set(fontObj, '<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>');
  objects.set(pagesObj, `<< /Type /Pages /Kids [${pageRefs.join(' ')}] /Count ${pageRefs.length} >>`);
  objects.set(catalogObj, `<< /Type /Catalog /Pages ${pagesObj} 0 R >>`);

  const orderedKeys = [...objects.keys()].sort((a, b) => a - b);
  let pdf = '%PDF-1.4\n';
  const offsets = new Map();
  for (const objNumber of orderedKeys) {
    offsets.set(objNumber, pdf.length);
    pdf += `${objNumber} 0 obj\n${objects.get(objNumber)}\nendobj\n`;
  }
  const xrefStart = pdf.length;
  const maxObj = orderedKeys[orderedKeys.length - 1] || 0;
  pdf += `xref\n0 ${maxObj + 1}\n`;
  pdf += '0000000000 65535 f \n';
  for (let obj = 1; obj <= maxObj; obj += 1) {
    const offset = offsets.get(obj) || 0;
    pdf += `${String(offset).padStart(10, '0')} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size ${maxObj + 1} /Root ${catalogObj} 0 R >>\nstartxref\n${xrefStart}\n%%EOF`;
  return new TextEncoder().encode(pdf);
}
