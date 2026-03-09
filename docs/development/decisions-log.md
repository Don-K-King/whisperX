# Decisions Log

## 2026-03-06
- ADR-0001 angenommen: On-Prem Multi-Tenant Architektur mit RabbitMQ/Celery Pipeline, lokaler Modellbereitstellung und Retention-Konzept.
- Konsequenz: Alle neuen API-/DB-/Export-Pfade müssen `tenant_id`-gescoped umgesetzt und getestet werden.
- Konsequenz: Retention-Felder und Frontend-Anzeige sind Pflicht für Nutzer-/Compliance-Transparenz.
- Ergänzung: Edge-/Abuse-Teststrategie ist je Entwicklungsschritt verpflichtend (u. a. Prompt-Injection-Resilienz, Rate-Limiting, Input-Validation, ungewöhnliche Eingaben).

- ADR-0002 angenommen: Phase-1 Spezifikationsfreeze mit verbindlichen Fach-, API-, Event-, Datenmodell-, Security- und Test-Spezifikationen.
- Konsequenz: Implementierungsstart nur über Vertical Slice `Auth + Upload` mit TDD- und Security-Gates.


## 2026-03-07
- ADR-0003 angenommen: Verbindliches Implementation Playbook v1 als Gate zwischen Spezifikationsphase und Implementierung.
- Konsequenz: Schritt 3 startet nur bei vollständig erfüllter Definition of Ready (DoR) je Work Package.
- Konsequenz: Threat→Control→Test-Traceability sowie reproduzierbare Build-/Test-Nachweise sind verpflichtende Freigabekriterien.
- Frontend-Stack für Phase 1 festgelegt: React + TypeScript + Vite als architekturkonforme Umsetzungslinie.
- Konsequenz: UI-Spezifikation in `docs/product/frontend-ui-spec-v1.md` als ergänzende Umsetzungsspezifikation eingeführt; API/Security/Test-v1 bleiben führende Primärreferenzen.
- Governance ergänzt: Screenshot-Pflicht für UI/Design-Änderungen in `AGENTS.md` als DoD-relevantes PR-Kriterium verankert.



## 2026-03-07
- Schritt-3 Arbeitsdokumente auf neutrale technische Referenzen ohne formale Gate-/Freigabeentscheidungen umgestellt.
- Personenbezogene Sign-off-Einträge aus den Keycloak-Integrationsvorlagen entfernt; Fokus auf technische Parameter und Sicherheitsanforderungen.

## 2026-03-07 – WP-3.1 Implementierung: Auth Middleware + Tenant Context
- Minimales AuthN/AuthZ-Modul `evodox.auth.context` implementiert (Default-Deny, Tenant-Pflichtkontext, Rollenprüfung, `iss/aud/exp/iat/nbf`-Validierung).
- Normierte Fehlerklassifikation umgesetzt:
  - `401` für AuthN-Fehler (`auth.invalid_token`, `auth.expired`),
  - `403` für AuthZ/Tenant-Verletzungen (`authz.deny`).
- Korrelations-ID wird bei Erfolg/Fehler erzwungen, um Audit-/Tracing-Pflichten zu unterstützen.
- TDD-Nachweis: zunächst fehlschlagender Test (`ModuleNotFoundError`), anschließend Green mit 7 Unit-/Abuse-Fällen.


## 2026-03-07 – WP-3.2 Implementierung: Job-Create + Upload-Session
- Anwendungsschicht `evodox.jobs.create_service` eingeführt, um `POST /api/v1/jobs` als klar getrennte Business-Logik zu implementieren (vor HTTP-Adapter).
- Sicherheitsvalidierungen umgesetzt: Content-Type-Allowlist, Dateigröße-Grenze, Dateinamen-Härtung (Control-Chars/Path-Separators), Retention-Range und Idempotency-Key-Mindestanforderung.
- Tenant-Scoping wird bei Persistenz, Upload-Object-Key und Audit-Event erzwungen.
- Architekturkonflikt aktiv adressiert: Idempotenz bereits in WP-3.2 umgesetzt, um spätere Contract-Inkompatibilität zu vermeiden.
- TDD-Nachweis: Red mit fehlendem Modul, danach Green mit Unit+Integration+Abuse (7 Tests).


## 2026-03-07 – HTTP-Adapter + produktive Adapter (DB/Storage/Audit)
- FastAPI-Adapter als dedizierte Interface-Schicht ergänzt (`evodox.web.fastapi_adapter`) für `POST /api/v1/jobs` mit AuthN/AuthZ-Integration, Idempotency-Header und normierter Fehlerabbildung.
- Produktive Infrastruktur-Adapter ergänzt (`evodox.jobs.infrastructure`):
  - `SQLiteJobRepository` (persistente Job-Metadaten),
  - `SQLiteIdempotencyStore` (tenant-scoped Idempotenzpersistenz),
  - `LocalPresignUploadSessionFactory` (tenant-scoped Presign-URLs),
  - `JsonlAuditLog` (append-only Audit-Events).
- Architekturkonflikt adressiert: Offline-Umgebung ohne externe Paketinstallation; FastAPI-Laufzeitintegration ist implementiert, aber Integrationstest wird in dieser Umgebung geskippt.
- Alternative vorgeschlagen: interne Artefakt-Registry/Dependency-Mirror für reproduzierbares FastAPI-Deployment ohne Internetabhängigkeit.


## 2026-03-07 – WP-3.3 Implementierung: Complete-Upload + Outbox Queue-Publish
- `evodox.jobs.complete_upload_service` ergänzt: Upload-Finalisierung mit tenant-scoped Job-Lookup, Objektintegritätsprüfung, Statusübergang (`uploaded` -> `queued`) und idempotentem Verhalten.
- Outbox-Ansatz als Konsistenzstrategie umgesetzt (Event `job.queued` wird persistiert, Dispatch entkoppelt).
- FastAPI-Adapter um `POST /api/v1/jobs/{job_id}/complete-upload` erweitert (AuthZ + Header-/Payload-Validierung + Fehlerabbildung).
- Architekturkonflikt (schnelle Direktpublikation vs. Zustandskonsistenz) zugunsten Outbox-Pattern entschieden.
- Referenz: ADR-0004 (`/docs/adr/ADR-0004-complete-upload-outbox-idempotenz.md`).


## 2026-03-07 – WP-3.4 Implementierung: Job-Status Endpoint
- Read-Use-Case `evodox.jobs.get_job_status_service` ergänzt, um `GET /api/v1/jobs/{id}` als eigene Anwendungsschicht umzusetzen (kein direkter Endpoint-DB-Durchgriff).
- FastAPI-Adapter um tenant-scoped Statusendpoint erweitert; tenant-fremde IDs liefern neutral `job.not_found`.
- Progress-Rückgabe normiert: expliziter `progress` aus Datenquelle oder statusbasierter Fallback (`completed`=100, sonst 0).
- Retention-Information wird als `retention_until` aus `created_at` und `retention_months` abgeleitet.
- Architekturkonflikt adressiert: einfache Endpoint-Implementierung vs. wartbarer Read-Service; Entscheidung zugunsten separater Service-Schicht.


## 2026-03-08 – WP-4.1 Implementierung: Queue Routing + Retry/DLQ Governance
- Outbox-Dispatcher auf Governance-Modell erweitert: Retryable vs. Terminal Fehlerklassifikation, Backoff mit Jitter und DLQ-Routing bei Terminal-/Retry-Exhaustion-Fällen.
- Duplicate-Delivery wird als erwarteter Zustand behandelt und idempotent als bereits verarbeitet markiert (kein DLQ, kein erneuter Publish).
- Architekturkonflikt adressiert: direkte Broker-Kopplung in Business-Services wurde verworfen; stattdessen bleibt Outbox/Dispatcher als entkoppelte Reliability-Schicht bestehen.
- RabbitMQ-Anbindung über dedizierten Infrastruktur-Adapter (`RabbitMQQueuePublisher`) umgesetzt, inkl. persistenter Messages und Routing-Key-gebundenem Queue-Binding.


## 2026-03-08 – WP-4.2/4.3 Implementierung: Worker-Pipeline + Tenant-Fairness
- Worker-Verarbeitungskette (`ASR -> Alignment -> Diarization`) als separater Applikationsservice umgesetzt; Fachlogik bleibt von Broker-Implementierung entkoppelt.
- Sicherheitskontrolle ergänzt: Worker akzeptiert nur tenant-/job-scoped Objektpfade (`tenant/<tenant_id>/<job_id>/...`), Scope-Verletzungen werden terminal abgewiesen.
- Fehlerklassifikation für Worker-Lauf explizit: retryable Fehler führen zu `failed_retryable`, terminale Fehler zu `failed_terminal`.
- Tenant-Fairness + Backpressure als eigene Policy mit globalen/per-tenant Inflight-Limits und Round-Robin-Scheduling ergänzt.
- Architekturentscheidung über ADR-0005 dokumentiert (`/docs/adr/ADR-0005-worker-pipeline-fairness-backpressure.md`).


## 2026-03-08 – WP-5.1/5.2 Implementierung: Transcript-Versionierung + Export-Pipeline
- Optimistic Locking für Transcript-Edits umgesetzt (`base_version`), Konflikte führen deterministisch zu `transcript.version_conflict`.
- Architekturkonflikt adressiert: globale Locks wurden verworfen; Versionierung per compare-and-swap verbessert Skalierbarkeit und verhindert Lost Updates.
- Export-Service ergänzt mit Format-Validation (`txt|json|srt|vtt`) und tenant-scoped Transcript-Read als AuthZ-Schutz auf Datenebene.
- Security-Härtung: textbasierte Exportformate escapen untrusted Inhalte, um XSS/Markup-Injection-Risiken zu reduzieren.
- Architekturentscheidung über ADR-0006 dokumentiert (`/docs/adr/ADR-0006-transcript-versionierung-und-export-pipeline.md`).


## 2026-03-08 – WP-6.1 Implementierung: Retention Enforcement Job
- Retention-Policy als separater Resolver umgesetzt (`RetentionPolicyResolver`) mit Tenant-Default, globalen Grenzen und Clamping bei manipulierten Werten.
- Periodischer Enforcement-Service (`RetentionEnforcementJob`) eingeführt, der tenant-scoped Kandidaten verarbeitet und Lösch-/Skip-Entscheidungen auditiert.
- Harte Tenant-Isolation in Infrastrukturadaptern ergänzt: Candidate-Query und Delete/Anonymize-Update nutzen verpflichtend `(tenant_id, job_id)`.
- Architekturkonflikt adressiert: direkte Endpoint-Löschung verworfen; stattdessen entkoppelter Worker/Job-Service für skalierbaren Batch-Betrieb.
- Referenz: ADR-0007 (`/docs/adr/ADR-0007-retention-enforcement-worker.md`).


## 2026-03-08 – WP-6.2 Implementierung: Restore + Konsistenzprüfung
- Kritischer Architekturhinweis vorgezogen umgesetzt: `RetentionScheduler` ergänzt (Intervallsteuerung + idempotenter Retry-Recovery-Pfad je Teilfehlerklasse).
- Restore-Workflow als eigener Applikationsservice (`execute_restore`) implementiert, inkl. deterministischer Tabellen-Reihenfolge und tenant-scope Guards für Request/Object-Keys.
- Konsistenzprüfung nach Restore (`RestoreConsistencyChecker`) validiert Referenzen `Job ↔ Transcript ↔ Export ↔ Audit` und meldet Findings als expliziten Status.
- Architekturkonflikt adressiert: ad-hoc Restore-Skripte wurden verworfen; stattdessen strukturierter Workflow mit Audit und prüfbarem Ergebnis.
- Referenz: ADR-0008 (`/docs/adr/ADR-0008-retention-scheduler-und-tenant-restore-konsistenz.md`).


## 2026-03-08 – ADR-0009 Persistente Scheduler-Leases + idempotente Recovery-Queue
- Architekturentscheidung: `RetentionScheduler` produktiv auf persistente SQLite-Adapter umgestellt (`SQLiteSchedulerLeaseStore`, `SQLiteRetentionRetryStore`) statt In-Memory-State.
- Idempotenzhärtung: Recovery-Eindeutigkeit wird per DB-Constraint `PRIMARY KEY (failure_id, failure_class)` erzwungen.
- Skalierungsbezug: Due-Abfragen für Recovery-Backlog durch Indizes auf `tenant_id`, `status`, `next_attempt_at` abgesichert.
- Referenz: ADR-0009 (`/docs/adr/ADR-0009-retention-scheduler-sqlite-lease-und-idempotente-recovery-queue.md`).


## 2026-03-08 – ADR-0010 Quarantäne für invalid Retry-Datensätze + Lease-Heartbeat
- Sicherheitskonflikt adressiert: ungültige/manipulierte Retry-Datensätze werden nicht mehr als `recovered` klassifiziert, sondern als `invalid` quarantänisiert.
- Betriebskonflikt adressiert: Lease-Heartbeat (`renew_lock`) für lange Scheduler-Batches eingeführt, um Lease-Expiry-Races zu reduzieren.
- Referenz: ADR-0010 (`/docs/adr/ADR-0010-retention-scheduler-invalid-quarantine-und-lease-heartbeat.md`).


## 2026-03-08 – ADR-0011 Runtime-Orchestrierung Retention-Scheduler
- `RetentionSchedulerRuntimeSettings.from_env(...)` eingeführt: fail-fast Validierung für DB-Pfad, Lock-Owner, Intervalle, Batchsize, Lease-TTL und Heartbeat.
- `RetentionSchedulerRuntime` ergänzt: verbindliches produktives Wiring des Schedulers auf SQLite-Lease/Retry-Adapter ohne In-Memory-Fallback.
- Referenz: ADR-0011 (`/docs/adr/ADR-0011-retention-scheduler-runtime-orchestrierung-fail-fast-konfiguration.md`).

## 2026-03-08 – ADR-0012 Dedizierter Retention-Scheduler-Runner
- Architekturkonflikt explizit entschieden: eingebetteter API-Scheduler verworfen, dedizierter Runner eingeführt.
- Neuer Runtime-Entrypoint ergänzt: fail-fast Startvalidierung, strukturierte nicht-sensitive Startlogs, Graceful Shutdown via `SIGTERM`/`SIGINT`.
- Referenz: ADR-0012 (`/docs/adr/ADR-0012-dedizierter-retention-scheduler-runner.md`).

## 2026-03-08 – Runner-Bootstrap konkretisiert (operationalisierter Entrypoint)
- ADR-0012 in der Umsetzung vervollständigt: ausführbarer Runner-Entrypoint (`python -m ...`) baut produktive Abhängigkeiten für Retention-Job und Recovery-Executor auf.
- Sicherheitsentscheidung: Dateisystem-Löschpfad wird auf konfigurierten Root begrenzt (Path-Traversal-Guard) statt permissiver Löschpfad-Auflösung.
- Betriebsentscheidung: unbekannte Recovery-Failure-Klassen bleiben fail-safe im Retry-Pfad und werden nicht als erfolgreich markiert.

## 2026-03-08 – ADR-0013 Storage-Backend-Strategie + Recovery-Governance
- Retention-Runner um explizite Backend-Strategie erweitert: `filesystem` und `s3` (MinIO-kompatibel) mit konsistenter `delete_prefix`-Semantik.
- Recovery-Failure-Klassen versioniert (`RETENTION_RECOVERY_MAPPING_VERSION=v1`), unbekannte Klassen bleiben fail-safe im Retry.
- Deployment-Hardening ergänzt: Preflight-Validierung über `RETENTION_VALIDATE_ENV_ONLY=true` für Manifest-/Init-Checks.
- Referenz: ADR-0013 (`/docs/adr/ADR-0013-retention-runner-storage-backend-und-recovery-governance.md`).


## 2026-03-09 – Zielinstanz-Portkollision präventiv entschärft
- Betriebs-/Architekturentscheidung: interne Compose-Ports für Auth/API von `8080/8000` auf `18080/18000` verlegt, obwohl aktuell keine Host-Port-Publishes konfiguriert sind.
- Begründung: reduziert Kollisionsrisiko bei späteren Betriebsmodi (`ports:`-Freigaben, Host-Networking, Debug-Publishes) auf bereits belegten Zielinstanz-Ports.
- Security-Bewertung: keine zusätzliche Exposition, da weiterhin keine externen Port-Bindings gesetzt werden; Änderung betrifft nur interne Service-Kommunikation/Healthchecks.
- Nachweis/Analyse: `docs/operations/port-conflict-report-2026-03-09.md`.
