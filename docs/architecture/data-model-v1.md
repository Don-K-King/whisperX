# Datenmodell-Spezifikation v1

## Modellierungsprinzipien
- Jede fachliche Entität enthält `tenant_id` (Pflicht, nicht nullable).
- Tenant-Isolation wird durch Query-Filter, Constraints und Tests abgesichert.
- Audit-Relevanz: Erzeugung/Änderung/Löschung müssen nachvollziehbar bleiben.

## Entitäten

## tenant
- `id` (PK)
- `name`
- `status` (`active|suspended`)
- `created_at`

## job
- `id` (PK)
- `tenant_id` (FK -> tenant.id)
- `created_by_user_id`
- `status` (`upload_pending|queued|processing|completed|failed|retention_due|deleted`)
- `media_filename`
- `media_content_type`
- `size_bytes`
- `language`
- `retention_months`
- `retention_until`
- `created_at`, `updated_at`
- Indizes: `(tenant_id, created_at)`, `(tenant_id, status)`

## upload_session
- `id` (PK)
- `tenant_id` (FK)
- `job_id` (FK)
- `object_key`
- `checksum_sha256`
- `expires_at`
- `completed_at`
- Unique: `(tenant_id, job_id)`

## transcript
- `id` (PK)
- `tenant_id` (FK)
- `job_id` (FK, unique je Tenant)
- `current_version`
- `created_at`, `updated_at`

## transcript_version
- `id` (PK)
- `tenant_id` (FK)
- `transcript_id` (FK)
- `version_number`
- `segments_json`
- `created_by_user_id`
- `edit_reason`
- `created_at`
- Unique: `(tenant_id, transcript_id, version_number)`
- Historie ist immutable (kein Update/Delete einzelner Versionen im Regelbetrieb)

## export_artifact
- `id` (PK)
- `tenant_id` (FK)
- `job_id` (FK)
- `transcript_version`
- `format` (`txt|json|srt|vtt`)
- `status` (`queued|processing|completed|failed|deleted`)
- `object_key`
- `created_at`, `expires_at`
- Indizes: `(tenant_id, job_id, created_at)`

## audit_event
- `id` (PK)
- `tenant_id` (FK)
- `actor_user_id`
- `action`
- `resource_type`
- `resource_id`
- `event_data_json`
- `created_at`
- Append-only (nur Insert)

## retention_policy
- `id` (PK)
- `tenant_id` (FK)
- `default_months`
- `min_months`
- `max_months`
- `updated_by_user_id`
- `updated_at`

## Zustandsmodelle

### job-status Übergänge
- `upload_pending -> queued -> processing -> completed`
- `processing -> failed`
- `completed|failed -> retention_due -> deleted`

Ungültige Rücksprünge sind verboten (z. B. `completed -> processing`).

### export-status Übergänge
- `queued -> processing -> completed`
- `processing -> failed`
- `completed -> deleted` (durch Retention)

## Retention- und Audit-Regeln je Entität
- `job`: nach `retention_until` anonymisieren/löschen, Audit-Event Pflicht.
- `upload_session`: nach Abschluss + Sicherheitsfenster löschen, Audit-Event optional.
- `transcript/transcript_version`: löschbar erst bei Job-Retention, Audit-Event Pflicht.
- `export_artifact`: löschen nach Retention oder expliziter Löschanforderung, Audit-Event Pflicht.
- `audit_event`: nicht vor Compliance-Frist löschen (separate Policy, nicht Nutzer-überschreibbar).


## WP-4 Statuspräzisierung
- Job-Statuswerte für Worker-Lifecycle werden präzisiert auf: `upload_pending|uploaded|queued|processing|completed|failed_retryable|failed_terminal|retention_due|deleted`.
- Retry-Pfad: `processing -> failed_retryable -> queued`.
- Terminal-Pfad: `processing -> failed_terminal` (kein automatisches Requeue).


## WP-5 Präzisierung
- `transcript.current_version` ist monotonic steigend und Grundlage für Optimistic Locking.
- `transcript_version.version_number` wird je erfolgreichem Edit um genau `+1` erhöht; Konflikte erzeugen keinen Schreibvorgang.
- `export_artifact.format` bleibt strikt `txt|json|srt|vtt`; nicht erlaubte Formate sind fachlich ungültig.
