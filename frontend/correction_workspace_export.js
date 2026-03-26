import { formatTimestamp } from './correction_utils.js';

const EXPORT_MODE_RAW = 'raw';
const EXPORT_MODE_COMPACT = 'compact';

function resolveSpeakerLabel({ speaker = 'UNKNOWN', speakerLabels = {} }) {
  const key = String(speaker ?? 'UNKNOWN').trim() || 'UNKNOWN';
  const alias = String(speakerLabels?.[key] ?? '').trim();
  if (!alias || alias === key) return key;
  return `${alias} (${key})`;
}

function normalizeMode(mode) {
  return String(mode ?? EXPORT_MODE_COMPACT).toLowerCase() === EXPORT_MODE_RAW
    ? EXPORT_MODE_RAW
    : EXPORT_MODE_COMPACT;
}

function normalizeExportSegments(segments = []) {
  if (!Array.isArray(segments)) return [];
  const normalized = [];
  for (const raw of segments) {
    if (!raw || typeof raw !== 'object') continue;
    normalized.push({
      segment_id: String(raw.segment_id ?? '').trim(),
      speaker: String(raw.speaker ?? 'UNKNOWN').trim() || 'UNKNOWN',
      text: String(raw.text ?? ''),
      start: Number(raw.start ?? 0),
      end: Number(raw.end ?? 0),
    });
  }
  return normalized;
}

function pad(value) {
  return String(value).padStart(2, '0');
}

function yesNo(value) {
  return value ? 'Ja' : 'Nein';
}

function toIsoUtc(createdAt) {
  return (createdAt instanceof Date ? createdAt : new Date(createdAt)).toISOString();
}

function buildMetadata({
  jobId = '',
  sessionId = '',
  baseVersion = null,
  workingVersion = null,
  reviewStatus = '',
  isFinal = false,
  mode = EXPORT_MODE_COMPACT,
  createdAt = new Date(),
}) {
  const exportMode = normalizeMode(mode);
  return {
    jobId: String(jobId || '-'),
    sessionId: String(sessionId || '-'),
    baseVersion: Number.isFinite(Number(baseVersion)) ? String(Number(baseVersion)) : '-',
    workingVersion: Number.isFinite(Number(workingVersion)) ? String(Number(workingVersion)) : '-',
    reviewStatus: String(reviewStatus || '-'),
    isFinal: yesNo(Boolean(isFinal)),
    mode: exportMode,
    createdAtIso: toIsoUtc(createdAt),
  };
}

function appendMarkdownMetadata(lines, metadata) {
  lines.push(`- Job-ID: ${metadata.jobId}`);
  lines.push(`- Session-ID: ${metadata.sessionId}`);
  lines.push(`- Basis-Version: ${metadata.baseVersion}`);
  lines.push(`- Arbeits-Version: ${metadata.workingVersion}`);
  lines.push(`- Review-Status: ${metadata.reviewStatus}`);
  lines.push(`- Final: ${metadata.isFinal}`);
  lines.push(`- Export-Modus: ${metadata.mode}`);
  lines.push(`- Erstellt: ${metadata.createdAtIso}`);
}

function appendPlainTextMetadata(lines, metadata) {
  lines.push(`Job-ID: ${metadata.jobId}`);
  lines.push(`Session-ID: ${metadata.sessionId}`);
  lines.push(`Basis-Version: ${metadata.baseVersion}`);
  lines.push(`Arbeits-Version: ${metadata.workingVersion}`);
  lines.push(`Review-Status: ${metadata.reviewStatus}`);
  lines.push(`Final: ${metadata.isFinal}`);
  lines.push(`Export-Modus: ${metadata.mode}`);
  lines.push(`Erstellt: ${metadata.createdAtIso}`);
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

export function buildCorrectionExportSegments({
  segments = [],
  mode = EXPORT_MODE_COMPACT,
}) {
  const normalized = normalizeExportSegments(segments);
  if (normalizeMode(mode) === EXPORT_MODE_RAW) {
    return normalized.map((segment) => ({ ...segment }));
  }
  if (normalized.length < 2) {
    return normalized.map((segment) => ({ ...segment }));
  }

  const compacted = [];
  for (const segment of normalized) {
    const last = compacted[compacted.length - 1];
    if (!last) {
      compacted.push({ ...segment });
      continue;
    }
    if (String(last.speaker) === String(segment.speaker)) {
      last.end = Number(segment.end);
      last.text = last.text ? `${last.text}\n${segment.text}` : segment.text;
      continue;
    }
    compacted.push({ ...segment });
  }
  return compacted;
}

export function buildCorrectionMarkdownExport({
  jobId = '',
  sessionId = '',
  baseVersion = null,
  workingVersion = null,
  reviewStatus = '',
  isFinal = false,
  mode = EXPORT_MODE_COMPACT,
  segments = [],
  speakerLabels = {},
  createdAt = new Date(),
}) {
  const metadata = buildMetadata({
    jobId,
    sessionId,
    baseVersion,
    workingVersion,
    reviewStatus,
    isFinal,
    mode,
    createdAt,
  });
  const renderSegments = buildCorrectionExportSegments({ segments, mode: metadata.mode });
  const lines = [
    `# Korrektur-Export Job ${metadata.jobId}`,
    '',
  ];
  appendMarkdownMetadata(lines, metadata);
  lines.push('');
  lines.push('## Transkript');
  lines.push('');
  for (let index = 0; index < renderSegments.length; index += 1) {
    const segment = renderSegments[index] || {};
    const label = resolveSpeakerLabel({ speaker: segment.speaker, speakerLabels });
    const start = formatTimestamp(segment.start);
    const end = formatTimestamp(segment.end);
    lines.push(`### ${label} | ${start} - ${end}`);
    lines.push('');
    lines.push(String(segment.text ?? ''));
    lines.push('');
  }
  return `${lines.join('\n').trimEnd()}\n`;
}

export function buildCorrectionPlainTextExport({
  jobId = '',
  sessionId = '',
  baseVersion = null,
  workingVersion = null,
  reviewStatus = '',
  isFinal = false,
  mode = EXPORT_MODE_COMPACT,
  createdAt = new Date(),
  segments = [],
  speakerLabels = {},
}) {
  const metadata = buildMetadata({
    jobId,
    sessionId,
    baseVersion,
    workingVersion,
    reviewStatus,
    isFinal,
    mode,
    createdAt,
  });
  const renderSegments = buildCorrectionExportSegments({ segments, mode: metadata.mode });
  const lines = ['Korrektur-Export'];
  appendPlainTextMetadata(lines, metadata);
  lines.push('');
  lines.push('Transkript');
  lines.push('');
  for (let index = 0; index < renderSegments.length; index += 1) {
    const segment = renderSegments[index] || {};
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
