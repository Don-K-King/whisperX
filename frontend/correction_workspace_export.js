import { formatTimestamp } from './correction_utils.js';

const EXPORT_MODE_RAW = 'raw';
const EXPORT_MODE_COMPACT = 'compact';

function resolveSpeakerLabel({ speaker = 'UNKNOWN', speakerLabels = {} }) {
  const key = String(speaker ?? 'UNKNOWN').trim() || 'UNKNOWN';
  const alias = String(speakerLabels?.[key] ?? '').trim();
  if (!alias || alias === key) return key;
  return alias;
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

function appendProtocolMetadata(lines, metadata) {
  lines.push(`Job-ID: ${metadata.jobId}`);
  lines.push(`Session-ID: ${metadata.sessionId}`);
  lines.push(`Basis-Version: ${metadata.baseVersion}`);
  lines.push(`Arbeits-Version: ${metadata.workingVersion}`);
  lines.push(`Review-Status: ${metadata.reviewStatus}`);
  lines.push(`Final: ${metadata.isFinal}`);
  lines.push(`Exportzeitpunkt (UTC): ${metadata.createdAtIso}`);
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
    '# Einvernahmeprotokoll',
    '',
  ];
  appendProtocolMetadata(lines, metadata);
  lines.push('');
  lines.push('------------------------------------------------------------');
  lines.push('');
  for (let index = 0; index < renderSegments.length; index += 1) {
    const segment = renderSegments[index] || {};
    const label = resolveSpeakerLabel({ speaker: segment.speaker, speakerLabels });
    const start = formatTimestamp(segment.start);
    const end = formatTimestamp(segment.end);
    lines.push(`[${start} - ${end}] ${label}:`);
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
  const lines = ['Einvernahmeprotokoll'];
  appendProtocolMetadata(lines, metadata);
  lines.push('');
  lines.push('------------------------------------------------------------');
  lines.push('');
  for (let index = 0; index < renderSegments.length; index += 1) {
    const segment = renderSegments[index] || {};
    const label = resolveSpeakerLabel({ speaker: segment.speaker, speakerLabels });
    const start = formatTimestamp(segment.start);
    const end = formatTimestamp(segment.end);
    lines.push(`[${start} - ${end}] ${label}:`);
    lines.push(String(segment.text ?? ''));
    lines.push('');
  }
  return `${lines.join('\n').trimEnd()}\n`;
}

function escapeXml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&apos;');
}

function createCrc32Table() {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) {
      c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
    }
    table[n] = c >>> 0;
  }
  return table;
}

const CRC32_TABLE = createCrc32Table();

function crc32(bytes) {
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i += 1) {
    crc = CRC32_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function concatUint8(parts) {
  let size = 0;
  for (const part of parts) size += part.length;
  const merged = new Uint8Array(size);
  let offset = 0;
  for (const part of parts) {
    merged.set(part, offset);
    offset += part.length;
  }
  return merged;
}

function u16(value) {
  const out = new Uint8Array(2);
  new DataView(out.buffer).setUint16(0, Number(value) & 0xffff, true);
  return out;
}

function u32(value) {
  const out = new Uint8Array(4);
  new DataView(out.buffer).setUint32(0, Number(value) >>> 0, true);
  return out;
}

function buildZipStored(entries) {
  const enc = new TextEncoder();
  const localParts = [];
  const centralParts = [];
  let offset = 0;

  for (const entry of entries) {
    const nameBytes = enc.encode(String(entry.name || 'file.txt'));
    const dataBytes = entry.data instanceof Uint8Array
      ? entry.data
      : enc.encode(String(entry.data ?? ''));
    const checksum = crc32(dataBytes);
    const size = dataBytes.length;

    const localHeader = concatUint8([
      u32(0x04034b50),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(checksum),
      u32(size),
      u32(size),
      u16(nameBytes.length),
      u16(0),
      nameBytes,
    ]);
    localParts.push(localHeader, dataBytes);

    const centralHeader = concatUint8([
      u32(0x02014b50),
      u16(20),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(checksum),
      u32(size),
      u32(size),
      u16(nameBytes.length),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(0),
      u32(offset),
      nameBytes,
    ]);
    centralParts.push(centralHeader);

    offset += localHeader.length + dataBytes.length;
  }

  const centralDirectory = concatUint8(centralParts);
  const localData = concatUint8(localParts);
  const endRecord = concatUint8([
    u32(0x06054b50),
    u16(0),
    u16(0),
    u16(entries.length),
    u16(entries.length),
    u32(centralDirectory.length),
    u32(localData.length),
    u16(0),
  ]);

  return concatUint8([localData, centralDirectory, endRecord]);
}

function buildDocxParagraphs(text = '') {
  const lines = String(text ?? '').replaceAll('\r\n', '\n').replaceAll('\r', '\n').split('\n');
  return lines
    .map((line) => {
      const escaped = escapeXml(line);
      if (!escaped) return '<w:p />';
      return `<w:p><w:r><w:t xml:space="preserve">${escaped}</w:t></w:r></w:p>`;
    })
    .join('');
}

export function buildSimpleDocxFromPlainText(text = '') {
  const paragraphs = buildDocxParagraphs(text);
  const documentXml = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    + '<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
    + 'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    + 'xmlns:o="urn:schemas-microsoft-com:office:office" '
    + 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    + 'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
    + 'xmlns:v="urn:schemas-microsoft-com:vml" '
    + 'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" '
    + 'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    + 'xmlns:w10="urn:schemas-microsoft-com:office:word" '
    + 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    + 'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
    + 'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
    + 'xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" '
    + 'xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml" '
    + 'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
    + 'mc:Ignorable="w14 wp14">'
    + `<w:body>${paragraphs}<w:sectPr><w:pgSz w:w="11906" w:h="16838" />`
    + '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
    + 'w:header="708" w:footer="708" w:gutter="0" />'
    + '<w:cols w:space="708" /><w:docGrid w:linePitch="360" /></w:sectPr></w:body></w:document>'
  );
  const contentTypesXml = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />'
    + '<Default Extension="xml" ContentType="application/xml" />'
    + '<Override PartName="/word/document.xml" '
    + 'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml" />'
    + '</Types>'
  );
  const relsXml = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    + '<Relationship Id="rId1" '
    + 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    + 'Target="word/document.xml" />'
    + '</Relationships>'
  );

  return buildZipStored([
    { name: '[Content_Types].xml', data: contentTypesXml },
    { name: '_rels/.rels', data: relsXml },
    { name: 'word/document.xml', data: documentXml },
  ]);
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
