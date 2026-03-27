# Schnittstellen-Spezifikation v1 (OpenAPI-first)

## Geltung
Diese Spezifikation definiert die bindenden HTTP-Contracts für Phase 1.

## Sicherheits- und Scope-Regeln (global)
- AuthN: OIDC Bearer Token (Keycloak), gültige Signatur + `iss` + `aud` Pflicht.
- AuthZ: RBAC + Tenant-Scoping (`tenant_id` aus Claims).
- Default Deny: fehlende Rolle oder Tenant-Mismatch => `403`.
- Idempotenz: `POST /jobs`, `POST /jobs/{id}/complete-upload`, `POST /jobs/{id}/export` akzeptieren `Idempotency-Key` Header.
- Fehlerformat: RFC7807-ähnliches Problem-JSON.

## Normiertes Fehlerprofil (verbindlich)
- Alle Fehlerantworten enthalten mindestens: `type`, `title`, `status`, `error_code`, `correlation_id`.
- `detail` ist sanitisiert und darf keine internen Implementierungsdetails enthalten.
- Tenant-sensitive Endpunkte dürfen keine Antworttexte liefern, die Ressourcenenumeration ermöglichen.
- Für Frontend-Debugbarkeit ist `correlation_id` in jeder Fehlersituation Pflicht.

## Fehlerformat
```json
{
  "type": "https://evodox/errors/validation",
  "title": "Validation failed",
  "status": 422,
  "detail": "retention_months out of range",
  "instance": "/api/v1/jobs",
  "error_code": "EVOX-VAL-001",
  "tenant_id": "t-123",
  "correlation_id": "c-123"
}
```

## Endpunkte v1

### POST /api/v1/jobs
**AuthZ:** `user|reviewer|admin` im eigenen Tenant.

Request (Beispiel):
```json
{
  "filename": "hearing-01.mp4",
  "content_type": "video/mp4",
  "size_bytes": 1073741824,
  "language": "de",
  "retention_months": 12
}
```

Response 201:
```json
{
  "job_id": "job_01",
  "tenant_id": "t-123",
  "status": "upload_pending",
  "upload": {
    "session_id": "up_01",
    "presigned_url": "https://...",
    "expires_at": "2026-03-06T13:00:00Z"
  }
}
```

Fehlercodes: `400, 401, 403, 409, 413, 422, 429`.

### POST /api/v1/jobs/{id}/complete-upload
**AuthZ:** `user|reviewer|admin`, Zugriff nur auf eigenen Tenant.

Request:
```json
{
  "upload_session_id": "up_01",
  "object_key": "tenant/t-123/job_01/source.mp4",
  "checksum_sha256": "..."
}
```

Response 202:
```json
{
  "job_id": "job_01",
  "status": "queued",
  "queue": "gpu-standard"
}
```

Fehlercodes: `400, 401, 403, 404, 409, 422`.

### GET /api/v1/jobs/{id}
**AuthZ:** `user|reviewer|admin`, tenant-scoped read.

Response 200:
```json
{
  "job_id": "job_01",
  "status": "processing",
  "progress": 42,
  "retention_until": "2027-03-06T00:00:00Z"
}
```

Fehlercodes: `401, 403, 404`.

### GET /api/v1/jobs/{id}/media-source
**AuthZ:** `user|reviewer|admin`, tenant-scoped read.

Response 200:
```json
{
  "job_id": "job_01",
  "filename": "hearing-01.mp4",
  "content_type": "video/mp4",
  "object_key": "tenant/t-123/job_01/hearing-01.mp4",
  "media_url": "https://storage.example/uploads/tenant/t-123/job_01/hearing-01.mp4"
}
```

Fehlercodes: `401, 403, 404, 503`.

### GET /api/v1/jobs
**AuthZ:** `user|reviewer|admin`, tenant-scoped list.

Query: `status`, `created_from`, `created_to`, `limit`, `cursor`.

Fehlercodes: `400, 401, 403`.

### GET /api/v1/jobs/{id}/transcript
**AuthZ:** `user|reviewer|admin`, tenant-scoped read.

Response 200:
```json
{
  "job_id": "job_01",
  "version": 3,
  "speaker_labels": {
    "SPEAKER_01": "Patrick",
    "SPEAKER_02": "Angela"
  },
  "review_status": "in_review",
  "is_final": false,
  "final_set_by": null,
  "final_set_at": null,
  "status_updated_at": "2026-03-24T14:30:00Z",
  "segments": [
    {"segment_id": "seg_000001", "start": 0.0, "end": 3.1, "speaker": "S1", "text": "..."}
  ]
}
```

Fehlercodes: `401, 403, 404`.

### PUT /api/v1/jobs/{id}/transcript/speaker-labels
**AuthZ:** `user|reviewer|admin`, tenant-scoped write.

Request:
```json
{
  "base_version": 3,
  "speaker_labels": {
    "SPEAKER_01": "Patrick",
    "SPEAKER_02": "Angela"
  },
  "edit_reason": "Speaker-Namen pflegen"
}
```

Response 200:
```json
{
  "job_id": "job_01",
  "version": 4,
  "saved_at": "2026-03-22T12:15:00Z"
}
```

Fehlercodes: `401, 403, 404, 409, 422`.

### PUT /api/v1/jobs/{id}/transcript
**AuthZ:** `user|reviewer|admin`, tenant-scoped write.

Request:
```json
{
  "base_version": 3,
  "segments": [
    {"segment_id": "seg-1", "speaker": "S1", "text": "Korrigierter Text"}
  ],
  "edit_reason": "Korrektur Eigennamen"
}
```

Response 200:
```json
{
  "job_id": "job_01",
  "version": 4,
  "saved_at": "2026-03-06T12:15:00Z"
}
```

Fehlercodes: `401, 403, 404, 409, 422`.

### POST /api/v1/jobs/{id}/export
**AuthZ:** `user|reviewer|admin`, tenant-scoped write.

Request:
```json
{
  "format": "srt",
  "transcript_version": 4
}
```

Response 202:
```json
{
  "export_id": "exp_01",
  "status": "queued"
}
```

Fehlercodes: `400, 401, 403, 404, 409, 422`.

### GET /api/v1/audit
**AuthZ:** `admin` tenant-lokal.

Query: `action`, `from`, `to`, `actor_id`, `resource_id`.

Fehlercodes: `400, 401, 403`.

## Validierungsregeln (Pflicht)
- `retention_months`: Integer `1..36`.
- `size_bytes`: `>0 && <= 21474836480`.
- `filename`: max 255, Unicode-normalisiert, keine Steuerzeichen.
- `format`: enum `txt|json|srt|vtt`.
- `language`: ISO-639-1 sofern gesetzt.
- `speaker_labels`: Mapping von Roh-Speaker-Labels auf Anzeigenamen; Leerzeichen trimmen, Steuerzeichen und leere Werte ablehnen.
- `segments[].segment_id`: Pflicht in Update-Pfaden, stabil je Segment.
- `review_status`: `2..64` Zeichen.
- `edit_reason`: `3..255` Zeichen.
- Pfad-/Header-Injections, Nullbytes, doppelte Extensions werden verworfen.


## Verbindliche Job-Zustandsmaschine (State Machine)
### Zustände
`created` → `upload_pending` → `uploaded` → `queued` → `processing` → `completed`

Fehlerpfade:
- `processing` → `failed_retryable` → `queued` (bei Retry)
- `processing` → `failed_terminal` (nach Retry-Limit)

### Erlaubte Übergänge
- `POST /jobs`: `created`/`upload_pending`
- `POST /jobs/{id}/complete-upload`: `uploaded` → `queued`
- Worker Start: `queued` → `processing`
- Worker Erfolg: `processing` → `completed`
- Worker Fehler: `processing` → `failed_retryable|failed_terminal`

### Idempotenz- und Race-Condition-Regeln
- Requests mit identischem `Idempotency-Key` und semantisch gleichem Payload müssen dieselbe fachliche Wirkung liefern.
- Wiederholte `complete-upload`-Aufrufe dürfen keine zweite Queue-Publikation erzeugen.
- Falls Objekt im Storage fehlt, ist `complete-upload` mit konsistentem Fehler zu beantworten (`409/422` je Ursache), ohne Statuskorruption.
- DB-Statuswechsel und Event-Publikation sind so auszuführen, dass bei Teilfehlern Recovery ohne Doppelverarbeitung möglich ist (Outbox-/Reconciliation-Prinzip).

## 2026-03-22 - Addendum: Lifecycle Controls mit Midpoint-Checkpointing

### Neue/konkretisierte Endpunkte
- `POST /api/v1/jobs/{id}/pause`:
  - `queued -> paused`
  - `processing -> pause_requested -> paused` (kooperativ durch Worker)
- `POST /api/v1/jobs/{id}/resume`:
  - `paused -> queued` (Checkpoint-Fortsetzung statt kompletter Neu-Start)
  - `resume` auf `canceled` => `409 job.resume.invalid_state`
- `POST /api/v1/jobs/{id}/cancel`:
  - `queued|processing|pause_requested|paused -> cancel_requested -> canceled`
  - `canceled` ist terminal
- `DELETE /api/v1/jobs/{id}` ist Force-Soft-Delete aus allen nicht-`deleted` Status.
- Delete entfernt pending Outbox-Events und interne Job-Reste (Checkpoint/Worker-Artefakt/Transcript-Versionen), um Re-Queue aus Altzustand zu verhindern.
- `deleted` ist terminal.

### Erweiterte Zustandsmaschine
- Kontrollzustand fuer kooperatives Pausieren: `pause_requested`.
- Kontrollzustand fuer kooperatives Abbrechen: `cancel_requested`.
- Terminale Endzustaende umfassen `completed`, `failed_terminal`, `deleted`, `canceled`.

### Idempotenz- und Race-Regeln (Ergaenzung)
- Wiederholtes `cancel` auf bereits `canceled` bleibt idempotent und fuehrt zu keinem erneuten Statuswechsel.
- `resume` erzeugt je wirksamem Aufruf genau ein `job.queued` Outbox-Event.
- Worker muss `pause_requested`/`cancel_requested` zwischen ASR-Segmenten und Stage-Grenzen auswerten.

## 2026-03-24 - Addendum: Korrekturmodus-Endpunkte

### PATCH /api/v1/jobs/{id}/transcript/status
- AuthZ: `reviewer|admin`, tenant-scoped.
- Zweck: `review_status` und/oder `is_final` aktualisieren.
- Request:
```json
{
  "review_status": "reviewed",
  "is_final": true
}
```
- Response 200:
```json
{
  "job_id": "job_01",
  "review_status": "reviewed",
  "is_final": true,
  "final_set_by": "u-1",
  "final_set_at": "2026-03-24T14:32:00Z",
  "updated_at": "2026-03-24T14:32:00Z"
}
```
- Fehlercodes: `401, 403, 422, 503`.

### POST /api/v1/jobs/{id}/transcript/correction-sessions
- AuthZ: `user|reviewer|admin`, tenant-scoped.
- Zweck: Draft-Session auf Basis einer Transcript-Version starten.
- Request:
```json
{
  "base_version": 3,
  "autosave_enabled": false
}
```
- Response 200 (Auszug):
```json
{
  "session_id": "cs_abc123",
  "job_id": "job_01",
  "base_version": 3,
  "working_version": 3,
  "autosave_enabled": false,
  "history_index": 0,
  "review_status": "in_review",
  "is_final": false,
  "segments": [
    {"segment_id": "seg_000001", "start": 0.0, "end": 3.1, "speaker": "S1", "text": "..."}
  ]
}
```
- Fehlercodes: `401, 403, 404, 409, 422, 503`.

### GET /api/v1/jobs/{id}/transcript/correction-sessions/{session_id}
- AuthZ: `user|reviewer|admin`, tenant-scoped.
- Zweck: Session-Draft inkl. Historie/Operationen lesen.
- Response 200: entspricht Session-Response aus `POST .../correction-sessions`.
- Fehlercodes: `401, 403, 404, 422, 503`.

### PATCH /api/v1/jobs/{id}/transcript/correction-sessions/{session_id}
- AuthZ: `user|reviewer|admin`, tenant-scoped.
- Zweck: Session-Optionen (aktuell `autosave_enabled`) aktualisieren.
- Request:
```json
{
  "autosave_enabled": true
}
```
- Response 200: aktualisierte Session.
- Fehlercodes: `401, 403, 404, 422, 503`.

### POST /api/v1/jobs/{id}/transcript/correction-sessions/{session_id}/operations
- AuthZ: `user|reviewer|admin`, tenant-scoped.
- Zweck: Draft-Operationen anwenden (v1: `set_segments`, `replace_literal`, `reassign_speaker`, `update_text`).
- Request (Beispiele):
```json
{
  "operations": [
    {
      "type": "replace_literal",
      "query": "Herr Meier",
      "replace": "Herr Meyer",
      "speaker": "S1",
      "replace_all": true
    }
  ],
  "autosave_enabled": true
}
```
```json
{
  "operations": [
    {
      "type": "update_text",
      "segment_id": "seg_000042",
      "text": "Korrigierter Segmenttext"
    }
  ],
  "return_mode": "ack"
}
```
```json
{
  "operations": [
    {
      "type": "reassign_speaker",
      "segment_id": "seg_000042",
      "speaker": "S2",
      "start_char": 12,
      "end_char": 49
    }
  ]
}
```
- Response 200:
  - `return_mode=full`: aktualisierte Session inkl. vollstaendiger `segments`.
  - `return_mode=changed_segments` (Default): Session-Metadaten + `segments` nur fuer geaenderte Segmente + `removed_segment_ids`.
  - `return_mode=ack`: Session-Metadaten + `changed_segments_count`/`removed_segments_count` (ohne Segmentliste).
- Fehlercodes: `401, 403, 404, 409, 422, 503`.

### POST /api/v1/jobs/{id}/transcript/correction-sessions/{session_id}/undo
### POST /api/v1/jobs/{id}/transcript/correction-sessions/{session_id}/redo
### POST /api/v1/jobs/{id}/transcript/correction-sessions/{session_id}/discard
- AuthZ: `user|reviewer|admin`, tenant-scoped.
- Zweck: Draft-History steuern.
- Response 200: aktualisierte Session.
- Fehlercodes: `401, 403, 404, 422, 503`.

### POST /api/v1/jobs/{id}/transcript/correction-sessions/{session_id}/commit
- AuthZ: `user|reviewer|admin`, tenant-scoped.
- Zweck: Draft als neue persistierte Transcript-Version speichern (`version + 1`).
- Request:
```json
{
  "base_version": 3,
  "edit_reason": "Manuelle Korrektur nach Review"
}
```
- Response 200:
```json
{
  "job_id": "job_01",
  "version": 4,
  "saved_at": "2026-03-24T14:36:00Z"
}
```
- Fehlercodes: `401, 403, 404, 409, 422, 503`.

### Korrektur-Operationen (v1) - Vertragsregeln
- `set_segments`: ersetzt kompletten Draft-Stand, jedes Segment mit `segment_id`, `speaker`, `text`, `start`, `end`.
- `replace_literal`: nur literal matching (kein Regex), optional speaker-filter.
- `reassign_speaker`: ganzes Segment oder Teilbereich (`start_char`, `end_char`).
- `update_text`: aktualisiert Text eines vorhandenen Segments (`segment_id`, `text`), ohne kompletten Draft zu uebertragen.
- Timeline-Invarianten sind verpflichtend: keine Overlaps, monotone Chronologie, `start <= end`, nur finite Zeitwerte.
- Timeline-Luecken sind im Korrekturpfad zulaessig und werden nicht als Fehler gewertet.
- Audit-Pflicht fuer Session create/update/apply/undo/redo/discard/commit und Status-Updates.
