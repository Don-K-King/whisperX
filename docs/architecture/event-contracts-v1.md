# Event-Contracts v1 (Queue/Worker)

## Prinzipien
- Alle Events sind versioniert (`event_version`).
- Pflichtfelder: `event_id`, `event_type`, `event_version`, `tenant_id`, `job_id`, `timestamp`, `correlation_id`.
- Delivery-Semantik: at-least-once, Consumer müssen idempotent sein.
- Fehlerfälle: Retry mit Exponential Backoff, danach DLQ.

## Basis-Schema
```json
{
  "event_id": "evt_01",
  "event_type": "job.created",
  "event_version": "v1",
  "tenant_id": "t-123",
  "job_id": "job_01",
  "timestamp": "2026-03-06T12:00:00Z",
  "correlation_id": "c-123",
  "payload": {}
}
```

## Verbindliche Events

### 1) job.created
Payload:
```json
{
  "upload_session_id": "up_01",
  "size_bytes": 1073741824,
  "media_type": "video/mp4"
}
```

### 2) job.queued
Payload:
```json
{
  "queue": "gpu-standard",
  "priority": "normal"
}
```

### 3) job.processing.started
Payload:
```json
{
  "worker_id": "worker-a",
  "attempt": 1
}
```

### 4) job.processing.completed
Payload:
```json
{
  "duration_ms": 120000,
  "transcript_version": 1,
  "artifact_keys": ["...json", "...txt"]
}
```

### 5) job.processing.failed
Payload:
```json
{
  "attempt": 3,
  "error_code": "ASR_TIMEOUT",
  "retryable": false
}
```

### 6) transcript.version.created
Payload:
```json
{
  "version": 4,
  "editor_user_id": "u-1",
  "edit_reason": "Korrektur"
}
```

### 7) export.requested
Payload:
```json
{
  "export_id": "exp_01",
  "format": "srt",
  "transcript_version": 4
}
```

### 8) export.completed
Payload:
```json
{
  "export_id": "exp_01",
  "object_key": "tenant/t-123/job_01/export.srt"
}
```

### 9) retention.executed
Payload:
```json
{
  "deleted_objects": 7,
  "deleted_records": 4,
  "policy_months": 12
}
```

## Retry-/DLQ-Regeln
- Max Retries: 5 (konfigurierbar pro Queue-Klasse).
- Backoff: `2^n * base_delay` mit Jitter.
- DLQ Event enthält Original-Event + Fehlerkontext.
- DLQ-Verarbeitung nur durch Admin-Betriebsprozess, vollständig auditierbar.


## Lebenszyklus- und Duplikatregeln (verbindlich)
- `job.queued` darf pro fachlichem Upload-Abschluss nur einmal als wirksames Event verarbeitet werden.
- Consumer müssen Duplikate anhand `event_id` und idempotenter Geschäftsregeln erkennen und neutral verarbeiten.
- Bei Teilfehlern zwischen Persistenz und Publish ist ein Reconciliation-Lauf verpflichtend.
- Reihenfolgegarantie ist nicht global, daher müssen Handler zustandsbasiert gegen verfrühte/späte Events robust sein.


## Event `job.queued` – Konkretisierung für WP-3.3
Pflichtfelder:
- `event_type`: `job.queued`
- `tenant_id`
- `job_id`
- `queue`
- `object_key`
- `checksum_sha256`
- `upload_session_id`

Semantik:
- Event wird initial in Outbox persistiert und danach in Broker publiziert.
- Wiederholte `complete-upload`-Requests mit identischem Idempotency-Key erzeugen kein Duplikat-Event.

## 2026-03-22 - Addendum: Resume/Cancel Event-Governance
- `job.queued` bleibt das einzige Queue-Event fuer Upload- und Resume-Pfad.
- Resume muss idempotent bleiben: pro wirksamem Resume-Aufruf genau ein Outbox-Event mit `event_type=job.queued`.
- Bei `cancel_requested|canceled` darf kein neuer Workload gestartet werden; pending Outbox-Events fuer den Job werden als verarbeitet markiert.
- Consumer muessen `canceled` als terminal behandeln und duerfen keine Folgeverarbeitung starten.
