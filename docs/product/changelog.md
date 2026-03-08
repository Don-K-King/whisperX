# Changelog

## 2026-03-06
- Architektur präzisiert: Multi-Tenant, On-Prem Docker, RabbitMQ/Celery Skalierungsstrategie, lokale Modellbereitstellung.
- Produktanforderung ergänzt: Löschfristen im Frontend/Job-Kontext, Default per ENV in Monaten.
- Produktumfang Phase 1 klargestellt: initialer Edit-Export.
- Teststrategie erweitert: verpflichtende Edge-/Abuse-Tests pro Entwicklungsschritt (Prompt-Injection-Resilienz, Rate-Limiting, unkonventionelle Eingaben, Eingabevalidierung).
- Spezifikationsfreeze v1 hinzugefügt: fachliche Spezifikation, API- und Event-Contracts, Datenmodell, Security-Spezifikation und Test-Spezifikation als verbindliche Umsetzungsbasis.
- Entwicklungsplan aktualisiert: nächster optimaler Schritt ist der TDD-Implementierungsstart „Auth + Upload Vertical Slice“.
- Entwicklungsdokumentation bereinigt: `/Entwicklungs.md` als Single Point of Truth festgelegt; `/docs/development/Entwicklungs.md` enthält nur noch Referenz- und Contract-Check-Hinweise.
- Planungspräzisierung vor Realisierung: kein separates Frontend-Primärdokument, stattdessen verpflichtender Frontend/API-Contract-Check gegen API-, Security- und Test-Spezifikation v1.


## 2026-03-07
- Entwicklungsplanung um verbindliches Implementation Playbook v1 erweitert (DoR/DoD, Work-Packages, Gate-Reihenfolge, Reproduzierbarkeitsnachweise).
- Implementierungsstart Schritt 3 (WP-3.1): zentrales Auth-/Tenant-Context-Modul mit Default-Deny, Rollen-Whitelist und normierten `401/403`-Fehlercodes inkl. `correlation_id` ergänzt.
- Sicherheits- und Testdokumentation um verpflichtende Threat→Control→Test-Traceability sowie CI-Blocker-Gates pro Entwicklungsschritt ergänzt.
- Architektur-/Event-Spezifikation um normative Job-State-Machine und Duplikat-/Recovery-Regeln präzisiert.

## 2026-03-07
- Frontend/UI-Spezifikation v1 für Phase 1 ergänzt (`docs/product/frontend-ui-spec-v1.md`) mit verbindlichen Entscheidungen zu Branding, Light/Dark, Karten-Dashboard, Upload-UX, i18n-Readiness und Admin-Audit-Ansicht.
- Entwicklungsplan-Referenzen aktualisiert, damit die neue Frontend-Umsetzungsspezifikation formal eingebunden ist.
- Governance aktualisiert: Für UI/Design-Änderungen sind in der Realisierungsphase verpflichtende Screenshots im PR nachzuweisen.

## 2026-03-07
- Gap-Analyse und priorisierte Blocker-Liste dokumentiert, um Architektur-/Security-Risiken (Tenant-Leak, AuthZ-Drift, Contract-Drift) vor Implementierungsbeginn zu schließen.

- Schritt-3 Vorbereitungsdokumente auf technische Arbeitsreferenzen ohne formale Gate-Entscheidungen umgestellt.

- Implementierungsfortschritt Schritt 3 (WP-3.2): Job-Erstellung mit serverseitiger Upload-Validierung, tenant-scope Upload-Session, Audit-Eventing und Idempotenzschutz umgesetzt.

- Betreiberrelevante Erweiterung: HTTP-Adapter für Job-Erstellung sowie produktive Persistenz-/Audit-/Presign-Adapter (SQLite/JSONL/signierte Upload-URLs) ergänzt.

- Implementierungsfortschritt Schritt 3 (WP-3.3): `complete-upload` mit idempotentem Queueing, tenant-scoped Objektprüfung und Outbox-basierter Publish-Strategie ergänzt.

- Implementierungsfortschritt Schritt 3 (WP-3.4): tenant-sicherer Job-Statusabruf (`GET /jobs/{id}`) mit Progress- und Retention-Information ergänzt.

## 2026-03-08
- Implementierungsfortschritt Schritt 4 (WP-4.1): Outbox-Dispatcher um RabbitMQ-Publisher-Adapter, Retry/Backoff mit Jitter, DLQ-Routing und Duplicate-Delivery-Handling erweitert.
- Betreiberrelevante Monitoring-Erweiterung: Metrik-Hooks für Queue-Lag, Retry-Rate, DLQ-Count und Duplicate-Events in der Queue-Dispatch-Pipeline ergänzt.

- Implementierungsfortschritt Schritt 4 (WP-4.2/WP-4.3): Worker-Processing-Chain (ASR/Alignment/Diarization) mit tenant-scoped Artefaktpersistenz sowie Tenant-Fairness/Backpressure-Policy ergänzt.

- Implementierungsfortschritt Schritt 5 (WP-5.1/WP-5.2): Transkript-Versionierung mit Optimistic Locking und sichere Export-Pipeline (`txt|json|srt|vtt`) im Tenant-Kontext ergänzt.


## 2026-03-08
- Schritt 6.1 umgesetzt: Retention Enforcement Job eingeführt (Policy-Resolver + periodischer Löschlauf) inkl. Audit-Events pro Entscheidung und Ausführung.
- Sicherheitsrelevante Härtung: tenant-scoped Löschqueries, Clock-Skew-Schutz gegen verfrühte Löschung und Teilfehler-Nachweis bei Storage/DB-Inkonsistenzen.
- Infrastruktur erweitert: SQLite-Retention-Candidate/Execution-Adapter mit Anonymisierung (`filename` redacted, Status `deleted`) und tenant-spezifischem Outbox-Pruning.


## 2026-03-08
- Schritt 6.2 umgesetzt: tenant-sicherer Restore-Workflow mit fester Restore-Reihenfolge und automatischer Konsistenzprüfung (`Job↔Transcript↔Export↔Audit`) eingeführt.
- Betriebsrelevante Härtung: periodischer Retention-Scheduler mit idempotentem Retry-Recovery-Pfad für Teilfehlerklassen ergänzt.
- Sicherheitsrelevante Absicherung: Restore-Guards gegen Cross-Tenant-Scopes und verpflichtende Restore-Audit-Events (`restore.started`, `restore.completed`) ergänzt.


## 2026-03-08
- Retention-Scheduler läuft produktiv jetzt mit persistentem SQLite-Lease statt In-Memory-Zustand; Scheduler-Intervall und Recovery-Fortschritt bleiben über Prozessneustarts erhalten.
- Retry-Recovery-Queue ist persistent und idempotent pro `failure_id + failure_class`; Duplikate lösen keine Mehrfachausführung mehr aus.
- Betriebsseitig wurden neue Monitoring-/Alerting-Anforderungen für Lease-Stale und Recovery-Backlog eingeführt.


## 2026-03-08
- Ungültige/manipulierte Retention-Retry-Datensätze werden nun explizit als `invalid` quarantänisiert (statt implizit als `recovered`).
- Für lange Scheduler-Läufe wurde ein Lease-Heartbeat ergänzt, um konkurrierende Parallel-Ausführung bei Lease-Expiry zu vermeiden.


## 2026-03-08
- Retention-Scheduler verfügt jetzt über ein verbindliches Runtime-Startprofil mit fail-fast Konfigurationsvalidierung (DB-Pfad, Lock-Owner, Intervall, TTL/Heartbeat).
- Der produktive Startpfad verdrahtet den Scheduler explizit auf persistente SQLite-Adapter und vermeidet implizite In-Memory-Fallbacks.

## 2026-03-08 – Betreiberupdate: Dedizierter Retention-Scheduler-Prozess
- Neu: Retention-Scheduler wird als dedizierter Runner-Prozess betrieben statt als eingebettete Nebenfunktion.
- Auswirkungen für Betrieb:
  - eigener Startpfad mit fail-fast Konfigurationschecks,
  - strukturierte Start-/Tick-/Shutdown-Logs,
  - kontrollierter Graceful-Shutdown via `SIGTERM`/`SIGINT`.
- Erwarteter Nutzen: klare Verantwortlichkeit, bessere Skalierbarkeit und geringere Kopplung zwischen API-Lifecycle und Retention-Lifecycle.

## 2026-03-08 – Betriebsupdate: produktiver Runner-Bootstrap vervollständigt
- Der dedizierte Retention-Runner besitzt nun einen ausführbaren Entrypoint (`python -m evodox.runtime.retention_scheduler_runner`) mit produktivem Dependency-Wiring.
- Neu sind fail-fast Bootstrap-Checks für Tenant-Liste, Audit-Log-Pfad, Storage-Root und Retention-Policy-Grenzen.
- Recovery-Pfad wurde für bekannte Teilfehlerklassen (`storage_delete_failed`, `db_mark_failed`) konkretisiert; unbekannte Klassen bleiben fail-safe im Retry.

## 2026-03-08 – Betreiberupdate: S3/MinIO-Backend + Recovery-Governance + Preflight
- Retention-Runner unterstützt jetzt neben lokalem Filesystem ein dediziertes `s3`-Backend (MinIO-kompatibel) mit gleicher Prefix-Delete-Semantik.
- Recovery-Failure-Klassen werden versioniert über `RETENTION_RECOVERY_MAPPING_VERSION` gesteuert (aktuell `v1`).
- Neuer Betriebsmodus zur Deployment-Härtung: `RETENTION_VALIDATE_ENV_ONLY=true` validiert Pflicht-ENVs vor Runner-Start.
- Neue vollständige Konfigurationsvorlage: `.env.example`.

## 2026-03-08 – Frontend Phase-1 Oberfläche implementiert
- Neue browserbasierte Frontend-Oberfläche mit Login, Dashboard, Job-Erstellung (inkl. Drag&Drop/File-Picker), Job-Detail und Audit-Ansicht ergänzt.
- Light/Dark-Theme, Sprachumschalter (de/en) sowie Tenant-Badge im globalen Header eingeführt.
- Fehlerdarstellung auf `error_code` + `correlation_id` normalisiert, um debug-freundlich ohne Secret-Leakage zu bleiben.

## 2026-03-08 – Frontend UI-Refresh (Modern + Branding + Darkmode)
- Header um sichtbares EvidoX-Branding erweitert (Logo-Monogramm + Produktbeschriftung), um die markenprägende Vorgabe explizit abzubilden.
- Modernisierte UI mit Hover-Effekten für Navigation, Buttons, Karten und Dropzone umgesetzt.
- Darkmode-Darstellung und responsive Optimierung verfeinert; visuelle Zustände wurden als Screenshots nachgewiesen.
