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
  "segments": [
    {"start": 0.0, "end": 3.1, "speaker": "S1", "text": "..."}
  ]
}
```

Fehlercodes: `401, 403, 404`.

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
