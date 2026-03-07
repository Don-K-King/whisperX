# Security Controls

## Referenz
Verbindliche Security-Spezifikation: `docs/security/security-spec-v1.md`.

## Identität & Zugriff
- OIDC JWT Validation (Signatur, `iss`, `aud`, `exp`)
- RBAC + Tenant Claims
- Default Deny bei fehlendem Tenant-Kontext
- `/api/v1/audit` nur für `admin` (tenant-lokal)

## Daten- und Mandantenschutz
- `tenant_id` in allen relevanten Tabellen und APIs
- Query-Guards und Service-Layer-Prüfungen
- Export nur innerhalb Tenant Scope
- Tenant-scoped Object Keys in MinIO

## Upload- und Verarbeitungs-Sicherheit
- Dateityp-/Signaturprüfung (MIME + Magic Bytes)
- Maximalgrößen und Ratenlimits
- Queue-Isolation durch Routing-Keys und Quoten
- Retry/Backoff/DLQ mit idempotenten Consumern

## Compliance
- Retention Default: `EVIDOX_DEFAULT_RETENTION_MONTHS`
- Validierte Retention-Range: `1..36` Monate
- Audit-Log für Erstellung, Zugriff, Export, Löschung
- Audit append-only und tenant-scope Pflicht

## Verifikationsnachweise (Testgates)
- Tenant-Isolation: Unit + Integration + E2E.
- AuthN/AuthZ: Contract + Integration.
- Upload-Härtung: Edge-/Abuse-Tests.
- Retention/Audit: Unit + Integration mit Nachweisfällen.


## Control-to-Test-Mapping (verbindlich)
- Jede sicherheitsrelevante Änderung benötigt eine Zuordnung: **Control → Testfall → Audit-Ereignis**.
- Pflicht für Schritt 3:
  - JWT- und Claim-Validierung → Auth-Abuse-Tests → `auth.denied`/`auth.accepted`
  - Tenant-Isolation im Datenzugriff → Isolationstests API/DB/Export → `access.denied`
  - Upload-Validation → Edge-Fuzzing-Tests → `upload.rejected`
  - Idempotenzschutz bei Queueing → Replay-/Duplicate-Tests → `job.queue.publish`


## Ergänzende Controls für Schritt 3A/3
- Sicheres Fehlerprofil: standardisierte Fehlerobjekte mit `error_code`/`correlation_id`, ohne sensitive Interna.
- Enumerationsschutz auf tenant-sensitiven Endpunkten (`403/404`-Verhalten gemäß API-Vertrag).
- Verifikationspflicht über Abuse-Tests gegen verbose Fehlerantworten.

## WP-3.1 Kontrollkonkretisierung (Auth Middleware + Tenant Context)
- Zentrale Policy-Funktion `authorize_request(...)` als Single-Entry für Claims-Validierung (`sub`, `tenant_id`, `roles`, `iss`, `aud`, `exp`, `iat`, `nbf`).
- Default-Deny bei fehlendem `tenant_id` oder Rollen-/Tenant-Mismatch (`403 authz.deny`).
- AuthN-Verletzungen führen konsistent zu `401` (`auth.invalid_token`/`auth.expired`).
- Korrelations-ID ist verpflichtend in Fehlern und Erfolgs-Context für Audit/Forensik.
- Missbrauchsschutz: nur erlaubte Rollen (`user`, `reviewer`, `admin`) werden akzeptiert.


## WP-3.2 Kontrollkonkretisierung (Job-Create + Upload Session)
- Input-Validation serverseitig verpflichtend: MIME-Allowlist, Größenlimit (`<= 21474836480`), Retention-Range (`1..36`), Dateinamen-Härtung.
- Tenant-Isolation in Speicherpfaden: Upload-Objektpfad strikt `tenant/<tenant_id>/<job_id>/<filename>`.
- Idempotenzschutz auf `POST /jobs` verhindert doppelte Job-Erstellung und Audit-Dubletten bei Wiederholungsrequests.
- Audit-Ereignis `job.create` wird für jeden neu erzeugten Job geschrieben (`tenant_id`, `actor_id`, `job_id`, `idempotency_key`).


## HTTP-/Infrastruktur-Adapter Controls
- HTTP-Gate `POST /api/v1/jobs` erzwingt Bearer-Token-Präsenz und delegiert Claim-Prüfung zentral an `authorize_request` (Default-Deny bleibt erhalten).
- Idempotency-Key wird als Header Pflicht gemacht; fehlender Header führt zu validierungsbasiertem Reject.
- SQLite-Adapter persistiert `tenant_id` verpflichtend in Job- und Idempotenzdaten (Isolation auf Datenebene).
- Audit-Adapter schreibt JSONL append-only mit Zeitstempel für forensische Nachvollziehbarkeit.
- Presign-Adapter signiert Upload-URLs und bindet Objektpfade strikt an Tenant/Job-Kontext.


## WP-3.3 Kontrollkonkretisierung (Complete-Upload + Queueing)
- `complete-upload` akzeptiert nur tenant-/job-konsistente `object_key`-Werte und SHA256-Prüfsummenformat.
- Cross-Tenant-Zugriffe führen zu neutralem `job.not_found` ohne Existenzleck.
- Idempotenz ist tenant-scoped verpflichtend; Payload-Mismatch führt zu Konfliktablehnung.
- Queue-Publikation erfolgt über Outbox + Dispatcher zur Absicherung gegen Persist/Publish-Teilfehler.
- Auditierbarkeit: Outbox-Event `job.queued` enthält `tenant_id`, `actor_id`, `job_id`, `queue`.


## WP-3.4 Kontrollkonkretisierung (GET Job-Status)
- Tenant-Isolation im Read-Pfad: Lookup ausschließlich über `(tenant_id, job_id)`.
- Enumerationsschutz: tenant-fremde Job-IDs liefern neutralen Not-Found-Fehler ohne Existenzdetails.
- AuthN/AuthZ-Pflicht auch für Read-Operationen bleibt aktiv (Bearer + Claim-Prüfung via zentraler Auth-Policy).
- Response-Härtung: nur vertraglich definierte Felder (`job_id`, `status`, `progress`, `retention_until`).
