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
