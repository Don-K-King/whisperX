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
- `status` (`upload_pending|uploaded|queued|processing|completed|failed_retryable|failed_terminal|pause_requested|paused|cancel_requested|canceled|retention_due|deleted`)
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
- `speaker_labels_json`
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

### job-status (kanonisch)
- `upload_pending -> uploaded -> queued -> processing -> completed`
- `processing -> failed_retryable -> queued`
- `processing -> failed_terminal`
- `queued -> paused`
- `processing -> pause_requested -> paused`
- `queued|processing|pause_requested|paused -> cancel_requested -> canceled`
- `completed|failed_retryable|failed_terminal|canceled|retention_due -> deleted`
- `DELETE` wirkt als Force-Soft-Delete auf alle nicht-`deleted` Status; `deleted` ist terminal.

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
- Die oben definierte kanonische Job-Statusmaschine ist die einzige aktive Referenz.
- Fruehere Teilmengen (z. B. nur `failed`) gelten als historisch und werden nicht mehr als normative Liste gepflegt.
- Retry- und Terminal-Pfade sind bereits in der kanonischen Statusmaschine enthalten.


## WP-5 Präzisierung
- `transcript.current_version` ist monotonic steigend und Grundlage für Optimistic Locking.
- `transcript_version.version_number` wird je erfolgreichem Edit um genau `+1` erhöht; Konflikte erzeugen keinen Schreibvorgang.
- `export_artifact.format` bleibt strikt `txt|json|srt|vtt`; nicht erlaubte Formate sind fachlich ungültig.

## 2026-03-22 - Addendum: Checkpoint-Datenmodell v1

### job_checkpoints (neu)
- `tenant_id` (PK-Anteil)
- `job_id` (PK-Anteil)
- `stage` (`downloaded|asr_started|asr_done|diarization_done`)
- `stage_offset` (Segmentoffset fuer laufende Stage, v1 granular in ASR)
- `payload_json` (interne Teilresultate fuer Resume)
- `updated_at`

### Job-Status Ergaenzung
- Die Zusatzstatus `pause_requested`, `paused`, `cancel_requested`, `canceled` sind bereits Teil der kanonischen Job-Statusmaschine oben.
- Die zugehoerigen Kontrollpfade sind dort ebenfalls dokumentiert und werden nicht mehr als konkurrierende zweite Liste gefuehrt.

## 2026-03-22 - Addendum: Transcript-Aliase als Versions-Snapshot
- `speaker_labels_json` speichert das Mapping `Roh-Speaker -> Anzeigename` zusammen mit jeder Transcript-Version.
- Alias-Aenderungen erzeugen eine neue `transcript_version`, damit vergangene Versionen und Exporte reproduzierbar bleiben.
- Das Alias-Mapping ist tenant- und job-gebunden und darf nicht zwischen Jobs oder Tenants wiederverwendet werden.
