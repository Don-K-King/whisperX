# Decisions Log

## 2026-03-27
- ADR-0023 angenommen: Korrekturmodus-Performance wird durch Editor-Virtualisierung, Event-Delegation und Delta-Operationen (`update_text`) verbessert.
- API-Entscheidung: Operations-Endpoint unterstuetzt `return_mode` (`ack|changed_segments|full`), Default auf `changed_segments`.
- Betriebskonsequenz: Autosave/Save vermeiden Vollpayload-`set_segments` im Regelfall und reduzieren Main-Thread-/Netzwerk-Last bei grossen Transkripten.

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

## 2026-03-22 - Status-Tracking: Local Docker Runtime Slice abgeschlossen, Transcript Vertical Slice als naechster Schritt
- Aktueller Stand: lokaler Docker-Vertical-Slice ist funktional und per E2E geprueft (`create -> complete-upload -> queued -> processing -> completed`).
- Fertig: API-Factory aus ENV, Hybrid-Auth `oidc|dev`, tenant-scoped Jobs/Audit-Endpoints, Stub-Worker-Runner, lokale Compose- und Runtime-Entrypoints.
- Offen: Transcript-API-Pfad, Persistenz des Worker-Outputs als abrufbares Transcript, Frontend-Upload per Presigned-Flow und Anzeige von Transcript/Speaker-Diarization.
- Naechster TDD-Schritt: Transcript Vertical Slice bis Frontend, zuerst Red-Tests fuer API-Contract und Frontend-Detailansicht, dann Runtime-Wiring und UI-Integration.

## 2026-03-22 - Status-Tracking: Presigned Upload Orchestrator als naechster Frontend-Schritt
- Aktueller Stand: Frontend-Upload wird als testbarer Orchestrator vorbereitet (`create job -> presigned PUT -> complete-upload`).
- Grune Gates: Frontend-Utilities/Tests fuer SHA-256 und Presigned-Upload, Python-Regression, Docker-Smoke im lokalen Runtime-Setup.
- Danach: WhisperX-Worker fuer echte Live-Transkription und Speaker-Diarization als naechster funktionaler Schritt im selben Docker-Vertical-Slice.

## 2026-03-22 - Local WhisperX Runtime fuer erstes Docker-E2E (historischer Status-Eintrag)
- Entscheidung: Worker-Mode `whisperx` als naechster Vertical Slice fuer lokale End-to-End-Transkription eingefuehrt, `stub` bleibt fuer deterministische Tests erhalten.
- Entscheidung: Browser-tauglicher Uploadpfad lokal ueber MinIO Host-Port (`19000`) statt internem Container-Hostnamen, damit Presigned PUT aus dem Frontend funktioniert.
- Entscheidung: MinIO-Bucket `uploads` wird im Compose-Init-Schritt automatisiert erstellt und fuer lokalen Dev-Betrieb auf `public` gesetzt.
- Entscheidung: Diarization wird als best-effort ausgefuehrt; bei gated/inkompatiblen Modellfehlern erfolgt automatischer Fallback auf reine Transkription, damit der Job nicht terminal scheitert.
- Abgrenzung: Die verbindliche Zielbetriebs- und Preflight-Gating-Entscheidung liegt in ADR-0014; dieser Eintrag dokumentiert nur den damaligen lokalen Runtime-Status.

## 2026-03-22 - Job Lifecycle Controls + Milestone Progress (historischer Log-Titel, keine separate ADR-Datei)
- Entscheidung: Job-Lifecycle fuer lokalen/prod-nahen Betrieb um `pause`, `resume` und `delete` erweitert.
- API-Form festgelegt: `POST /pause`, `POST /resume`, `DELETE /jobs/{id}`.
- Pause-Strategie bewusst als kooperatives Stop+Resume eingefuehrt (kein Midpoint-Checkpointing in diesem Schritt).
- Retry-Strategie im Worker konkretisiert: begrenzte Auto-Retries fuer retryable Fehler, danach deterministischer Uebergang nach `failed_terminal`.
- Progress-Strategie fuer UI/API festgelegt: deterministische Milestones (`5/20/60/90/100`) statt ETA-Schaetzung.
- Konsequenz: Frontend zeigt Actions statusabhaengig und pollt mit 429-Backoff; Backend liefert konsistente Progress-Werte auch bei fehlendem Raw-Progress.
- Historische Einordnung: Die Delete-Semantik wurde spaeter auf Force-Soft-Delete konsolidiert, und die UI-Progress-Anzeige wurde 2026-03-27 durch adaptive Interpolation weiterentwickelt. Dieser Eintrag bleibt als Herkunftsstand erhalten.

## 2026-03-22 - ADR-0016 Midpoint-Checkpointing + terminaler Cancel
- Entscheidung: Pause/Resume wird auf persistentes Stage+Segment-Checkpointing erweitert (`job_checkpoints`), ASR setzt per `stage_offset` ab letztem Segment fort.
- Entscheidung: neuer Endpunkt `POST /api/v1/jobs/{id}/cancel` mit terminaler Semantik (`canceled` ist final, `resume` liefert `409 job.resume.invalid_state`).
- Entscheidung: Cancel-Pfad nutzt Zwischenzustand `cancel_requested`, Worker priorisiert Cancel gegenueber Retry-Fortsetzung.
- Entscheidung: interne Teilresultate bleiben bewusst pipeline-intern und werden nicht ueber Frontend/API exponiert.
- Referenz: ADR-0016 (`/docs/adr/ADR-0016-midpoint-checkpointing-und-terminal-cancel.md`).

## 2026-03-22 - Stabiler Lifecycle: Force-Delete + no-auto-restart
- Entscheidung: `DELETE /api/v1/jobs/{id}` wird als Force-Soft-Delete aus allen nicht-`deleted` Status erlaubt; `job.delete.active_conflict` entfällt.
- Entscheidung: Delete pruned pending Outbox-Events (`status=pending -> published/skipped`) und loescht interne Job-Reste (Checkpoint/Worker-Artefakt/Transcript-Versionen), um Re-Queue aus Altzustand zu verhindern.
- Entscheidung: WhisperX-Timeout-Default wird auf `0` gesetzt (`timeout=None`), damit lange Jobs nicht kuenstlich abgebrochen werden.
- Entscheidung: generische Worker-Exceptions sind nicht retrybar per default; sie gehen auf terminal (`failed_terminal` + DLQ), ausser explizit retryable Pfaden (`failed_retryable` bis `worker_max_retries`).
- Entscheidung: laufende ASR-Subprozesse werden kooperativ ueber Polling beendet (`pause_requested|cancel_requested|deleted`), damit Pause/Resume/Cancel/Delete verlässlich auch waehrend langer Runs funktionieren.

## 2026-03-22 - ADR-0017 GPU-First Local + Multi-GPU Compose-Worker-Pools
- Worker-Runtime Defaults auf GPU-first umgestellt (`WORKER_WHISPERX_DEVICE=cuda`, `WORKER_WHISPERX_COMPUTE_TYPE=float16`).
- Runtime-Haertung eingefuehrt: kontrollierter GPU-Preflight mit CPU-Fallback (`cpu/int8`) und auditierbarem Event `worker.runtime.gpu_fallback`.
- WhisperX CLI-Wiring erweitert: `WORKER_WHISPERX_DEVICE_INDEX` wird ueber `--device_index` durchgereicht.
- Queue-Pool-Vorbereitung umgesetzt: `WORKER_ALLOWED_QUEUES` + Outbox-Filter fuer dedizierte Worker-Rollen.
- Compose-Zielbetrieb erweitert: Standard-`worker` ist GPU-first; zusaetzliche Profile-Services `worker-gpu-0`, `worker-gpu-1`, `worker-cpu` fuer dedizierte Server-Pools.
- Referenz: ADR-0017 (`/docs/adr/ADR-0017-gpu-first-local-und-multi-gpu-compose-worker-pools.md`).

## 2026-03-22 - ADR-0018 Tenant-Admin Decoding Settings + Job-Snapshot
- Neue admin-only Endpunkte fuer tenant-scoped Decoding-Defaults eingefuehrt (`GET/PUT /api/v1/admin/transcription-settings`).
- Persistenzmodell erweitert: `tenant_transcription_settings` (Tenant-Defaults) und `jobs.transcription_options_json` (Queueing-Snapshot pro Job).
- Queue/Worker-Wiring erweitert: `job.queued` und `resume` fuehren `transcription_options` mit; Worker mappt Whitelist-Felder auf WhisperX-CLI-Flags.
- Security-Haertung: strikte Feld-Whitelist und Wertevalidierung, Audit ohne Klartext-Prompt (nur Hash/Laenge fuer `initial_prompt`).
- Referenz: ADR-0018 (`/docs/adr/ADR-0018-tenant-admin-decoding-settings-und-job-snapshot.md`).

## 2026-03-22 - ADR-0019 Speaker-Aliase + Blockbildung
- Speaker-Aliase werden versioniert pro Transcript-Snapshot gespeichert, um Reproduzierbarkeit und Mehrgeraet-Use-Cases zu erhalten.
- Task-View-Rendering gruppiert aufeinanderfolgende Segmente mit gleichem Roh-Speaker zu lesbaren Blocken.
- Neue API fuer Speaker-Alias-Updates wird tenant-scoped und optimistic-locking-basiert umgesetzt.
- Referenz: ADR-0019 (`/docs/adr/ADR-0019-transcript-speaker-alias-und-blockbildung.md`).

## 2026-03-23 - ADR-0020 WhisperX large-v3 Erzwingung + Sprachwahl + Chunk/VAD Exposition
- Entscheidung: WhisperX-Worker erzwingt large-v3 im Runtime-Pfad, um inkonsistente Modellqualitaet durch ENV-Drift zu verhindern.
- Entscheidung: Sprache wird pro Job bei create erfasst (de Default, auto optional), im Snapshot persistiert und bei Queueing/Worker priorisiert.
- Entscheidung: Tenant-Admin Decoding-Settings werden um chunk_size, vad_onset, vad_offset erweitert und strikt validiert.
- Sicherheitsentscheidung: Eingaben bleiben whitelist-/range-basiert, Snapshot-Verarbeitung bleibt fail-safe ueber safe_worker_decoding_options.
- Referenz: ADR-0020 (/docs/adr/ADR-0020-whisperx-large-v3-erzwingung-sprache-und-chunk-vad.md).

## 2026-03-24 - ADR-0021 Korrekturmodus Sessions + Statusfuehrung
- Neue Transcript-Korrekturlogik eingefuehrt: Session-basierter Draft mit `apply/undo/redo/discard/commit` statt sofortiger Versionspersistenz.
- Autosave semantisch als Draft-Sicherung umgesetzt (keine automatische Versionserzeugung).
- Transcript-Status erweitert um `review_status` und `is_final` inkl. eigener API und Audit-Events.
- Timeline-Guards fuer Korrektur-Operationen verankert (historisch noch gap-frei formuliert; ADR-0022 praezisiert spaeter auf keine Overlaps bei erlaubten Luecken, konsistente Segment-IDs).
- Frontend um dedizierten Korrektur-Workspace erweitert (`window.open` ohne In-Tab-Fallback, Suche/Ersetzen, Sprecherumteilung, Audio-Mitfuehrung, Status/Final).
- Handover-Strategie fuer den Korrekturstart auf kurzlebigen tabuebergreifenden Store umgestellt (single-use, TTL, Cleanup), um `Korrektur-Startdaten fehlen` im neuen Tab zu vermeiden.
- Neue tenant-scoped Media-Quelle fuer den Workspace eingefuehrt (`GET /api/v1/jobs/{id}/media-source`) fuer automatisches Laden der Ursprungsdatei.
- Security-Hardening nach Implementierungsreview: Session-Reads sind actor-gebunden, `forbidden` wird als `403` gemappt, Status-Updates validieren Transcript-Existenz.
- Referenz: ADR-0021 (`/docs/adr/ADR-0021-korrekturmodus-sessions-und-status.md`).

## 2026-03-25 - Korrekturmodus Legacy-Schema-Migration (Hotfix)
- Entscheidung: Session-Insert im Correction-Store wird schema-adaptiv ausgefuehrt; existiert Legacy-Spalte `expires_at`, wird sie beim `create_session` explizit befuellt.
- Grund: Laufende Runtime-Volumes enthielten ein aelteres Schema mit `expires_at NOT NULL`, wodurch Korrektur-Session-Start mit `IntegrityError` scheiterte.
- Ergebnis: Korrekturmodus-Start bleibt ohne DB-Reset kompatibel zu Bestandsdaten.

## 2026-03-26 - ADR-0022 Korrekturmodus Absolute Timeline
- Entscheidung: Seed-Kompaktierung im Korrekturmodus wurde entfernt; `start/end` bleiben beim Session-Start 1:1 auf der persistierten Transcript-Timeline.
- Entscheidung: Timeline-Invariante im Korrekturpfad wurde von "keine Luecken" auf "keine Overlaps + monotone, finite Timeline" umgestellt.
- Entscheidung: `set_segments` akzeptiert Luecken, lehnt Overlaps sowie `NaN`/`inf`/negative Zeiten weiterhin strikt ab.
- Entscheidung: Frontend merged Speaker-Bloecke nur noch bei kontiguierlichen Segmenten; in internen Luecken gibt es bewusst keinen aktiven Block.
- Referenz: ADR-0022 (`/docs/adr/ADR-0022-korrekturmodus-absolute-timeline-ohne-seed-kompaktierung.md`).
- Einordnung: Diese Entscheidung praezisiert und ersetzt die zuvor in ADR-0021 formulierte gap-freie Guard-Variante.

## 2026-03-26 - Legacy-Session-Reseed im Korrekturmodus
- Entscheidung: Beim Start einer Correction-Session kann per `force_reseed_from_transcript` ein Legacy-Resume-Fall fix-forward auf die aktuelle Transcript-Timeline reseeded werden.
- Entscheidung: Reseed ersetzt den aktiven Draft auf `history[0]` mit absoluten Segmentzeiten der aktuellen Transcript-Version und setzt `history_index=0`.
- Entscheidung: Active-Highlighting nach Segmentende wird als "kein aktiver Block" behandelt, um End-Pausen nicht als Drift des letzten Blocks darzustellen.
## 2026-03-27 - Seek/Autofokus bei Virtualisierung: Lifecycle-Hardening
- Entscheidung: Media-Reuse im Render-Pfad wird vor dem erneuten Binding abgeschlossen; Event-Handler (timeupdate/seek) werden danach auf dem finalen Media-Node registriert.
- Begruendung: verhindert stale Closures mit veraltetem Editor-Referenzkontext und stabilisiert das automatische Follow nach Seek/Render.
- Entscheidung: Bei bereits geplanter Follow-rAF wird das Pending-Frame zugunsten des neuesten Seek-Ziels ersetzt (latest-wins), statt neue Seek-Spruenge zu verwerfen.
- Entscheidung: Virtual-Scroll-Projektion basiert auf gemessenen Segmenthoehen (mit Cache + Prefix-Summen) statt nur fixer Zeilenhoehe, um Drift bei variablen Blocktexten zu reduzieren.
- Sicherheitsbewertung: keine neuen AuthN/AuthZ- oder Datenflussaenderungen; Verarbeitung bleibt tenant-scoped und input-validiert wie bisher.
## 2026-03-27 - Seek/Follow Stabilisierung bei Virtualisierung (Empty-Window + Drift)
- Entscheidung: forced Virtual-Range wird zentral sanitisiert (Clamp auf gueltige Grenzen, nie leeres Fenster, Fallback auf Zielindex), um stale Range-Zustaende bei Seek robust abzufangen.
- Entscheidung: Seek-Warmup-Pending gilt jetzt fuer Playing und Paused gleich; Finalisierung erfolgt bei Warmup-Ready oder Deadline-Timeout, Playback-Resume jedoch nur wenn zuvor tatsaechlich gespielt wurde.
- Entscheidung: automatische Playback-Nachfuehrung nutzt im Follow-Pfad unmittelbares Zentrieren (kein smooth), um bei kurzen Segmenten/haeufigen Updates Drift aus dem Sichtfenster zu vermeiden.
- Sicherheitsbewertung: keine neuen externen Schnittstellen, keine AuthN/AuthZ-Aenderung, keine Erweiterung sensibler Datenfluesse.
## 2026-03-27 - Virtual-Window Scrollbar-Verhalten entkoppelt von Selection-Pinning
- Entscheidung: Virtual-Range wird nur noch im Playback-Follow explizit an einen bevorzugten Index gepinnt; manueller Scroll bleibt source of truth.
- Entscheidung: User-Scroll bricht stale Seek-Warmup-States kontrolliert ab (reset forced range), um leere Fenster bei Slider-Spruengen zu verhindern.
- Sicherheitsbewertung: rein frontendspezifische Renderlogik, keine neuen Daten- oder Auth-Grenzen.
## 2026-03-27 - Adaptive Windowing basierend auf Segmentumfang
- Entscheidung: Rendering-Fenster wird dynamisch aus der Segmentmenge abgeleitet (<=300 full, <=600: 450, <=1200: 300, <=3000: 240, sonst 180).
- Entscheidung: Sowohl normale Scroll-Range als auch Seek-forced-Range werden auf die adaptive Zielgroesse erweitert, damit Fenster-Spruenge weniger Nachladeartefakte zeigen.
- Begruendung: erreicht den gemessenen UX-Sweet-Spot fuer Interaktivitaet bei gleichzeitig kontrollierter DOM-/Layout-Last.
- Sicherheitsbewertung: keine neuen externen APIs, keine Aenderung von AuthN/AuthZ oder Tenant-Isolation.

## 2026-03-27 - Adaptive Progress-Interpolation (Dashboard + Jobdetail)
- Entscheidung: Fortschritt vom Backend bleibt Source of Truth; die UI interpoliert nur zwischen bekannten Milestones fuer bessere Aktivitaetswahrnehmung.
- Entscheidung: Interpolation ist strikt monoton und milestone-begrenzt (kein Rueckwaertslauf, kein vorzeitiges 100% vor terminalem Status).
- Entscheidung: Interpolation stoppt bei Polling-Fehlern/stale Daten und bei terminalen Status sofort.
- Entscheidung: ETA bleibt bewusst heuristisch (Dateigroesse-basiert mit Fallback), um Komplexitaet niedrig zu halten.
- Sicherheitsbewertung: keine API-/AuthN-/AuthZ-Aenderung, rein frontendspezifisches Anzeigeverhalten.

## 2026-03-27 - Progress-Heartbeat bei unveraenderten Poll-Snapshots
- Entscheidung: Poll-Antworten gelten als Freshness-Signal, auch wenn `status/progress` unveraendert sind.
- Umsetzung: `lastServerTimestamp` wird bei frischen Server-Snapshots aktualisiert, ohne `phaseStartMs` zu resetten.
- Effekt: kein fruehes Einfrieren der UI-Interpolation in langen `processing`-Phasen; Milestone-Clamping bleibt erhalten.
- Sicherheitsbewertung: reine Frontend-Anzeigelogik, keine Aenderung von AuthN/AuthZ/API-Contracts.

## 2026-03-27 - UI-Progress-Cap fuer lange Processing-Phasen angepasst
- Entscheidung: `processing` darf UI-seitig bis 99% interpolieren (statt indirekt bei 59% zu stoppen), um Abbruch-Eindruck zu vermeiden.
- Entscheidung: Interpolationsdauer nutzt hohe Obergrenze, um verfruehtes Auflaufen auf 99% zu vermeiden.
- Sicherheitsbewertung: reine Frontend-Darstellung, keine API-/Auth-Aenderung.

## 2026-03-27 - Dokumentationsgovernance SoT + Archiv
- Entscheidung: README dient als EvidoX-Einstieg und verweist fuer normative Details auf die thematischen SoT-Dokumente unter `docs/`.
- Entscheidung: `docs/README.md` ist der zentrale Dokumentations-Navigator mit klarer Trennung von aktiven SoT-Dokumenten und Historie.
- Entscheidung: Historische Schritt-/Signoff-/Incident-Artefakte bleiben aus Auditgruenden erhalten, werden aber ueber `docs/archive/README.md` als nicht-normativ klassifiziert.
- Entscheidung: Widerspruechliche Zwischenstaende in historischen Dokumenten gelten nicht als aktive Vertragsquelle; verbindlich sind API-Spec, Data-Model, Security-Controls, ADRs und Runbooks.
