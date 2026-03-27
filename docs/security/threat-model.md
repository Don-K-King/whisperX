# Threat Model (Phase 1 verfeinert)

## Schützenswerte Assets
- Rohmedien
- Transkripte und Edit-Historie
- Tenant-Metadaten und Auditdaten
- Zugriffstokens und Exportartefakte

## Top-Bedrohungen
1. Cross-Tenant Data Leakage
2. Token-Missbrauch / Privilege Escalation
3. Denial-of-Service durch große Dateien
4. Manipulation von Exporten/Löschfristen
5. Queue Poisoning / Retry Storms
6. Error Information Disclosure (Verbose Error Messages)

## Komponentenbezogene Risiken
- **Frontend:** XSS über Transcript-Inhalte, Token-Handling.
- **API:** AuthZ-Bypass, Input-Validation-Lücken, Idempotenzfehler.
- **Queue/Worker:** Poison Messages, Duplicate Delivery.
- **DB/Storage:** fehlerhafte Tenant-Filter, Datenabfluss durch falsche Object Keys.
- **Operations:** Fehlkonfiguration von Limits/Secrets.

## Priorisierte Gegenmaßnahmen
- Striktes Tenant-Scoping + verpflichtende Isolationstests
- Signatur-/Claim-Validierung und kurzlebige Tokens
- Queue-Backpressure, Upload Limits, Worker Concurrency Caps
- Unveränderbare Audit Trails und prüfbare Retention-Jobs
- Event-Schema-Validation und idempotente Worker-Handler

## Restrisiken
- On-Prem Fehlkonfiguration bleibt möglich; wird durch Deployment-Gates und Runbooks reduziert.
- Lastspitzen bei großen Medien können Latenzen erhöhen; durch Queue-Klassen + Skalierungsregeln begrenzt.


## Threat-Traceability für Schritt 3 (Auth + Upload Vertical Slice)
| Bedrohung | Control-Referenz | Test-Nachweis (Soll) | Audit-Nachweis |
|---|---|---|---|
| Claim-Manipulation / Role Escalation | JWT-Validierung + RBAC Default-Deny | AuthN/AuthZ Abuse-Tests (`iss/aud/exp`, manipulierte Claims) | `auth.denied` mit `reason` |
| Cross-Tenant Zugriff | Tenant-Scoped Query Guards | Integration/E2E Tenant-Isolation-Tests | `access.denied` mit `tenant_id` |
| Upload MIME/Extension Spoofing | MIME+Magic-Bytes + Größenlimits | Upload-Fuzzing/Validation-Tests | `upload.rejected` mit Validierungsgrund |
| Replay auf `complete-upload` | Idempotency-Key + fachliche Idempotenzprüfung | Integrationstest wiederholte Requests | `job.queue.publish` mit idempotency_status |


## Ergänzende Bedrohung Schritt 3
| Bedrohung | Control-Referenz | Test-Nachweis (Soll) | Audit-Nachweis |
|---|---|---|---|
| Error Information Disclosure | Sicheres Fehlerprofil + Enumerationsschutz | Verbose-Error-Abuse-Tests auf 401/403/404/422 | `authz.deny`/`request.rejected` mit `correlation_id` |


## Ergänzung 2026-03-07 – Adapter-Layer Risiken
- **Threat:** Manipulation/Replay auf `POST /api/v1/jobs` durch fehlenden oder wiederverwendeten Idempotency-Key.
  - **Control:** Pflichtheader + tenant-scoped Idempotenzspeicher mit Payload-Hash-Konflikterkennung.
  - **Test:** `tests/test_job_create_service.py` (Konfliktfall), `tests/test_fastapi_http_adapter_integration.py` (HTTP-Pfad).
- **Threat:** Tenant-Leak über Objektpfadbildung im Upload-Storage.
  - **Control:** Objekt-Key-Template `tenant/<tenant_id>/<job_id>/<filename>` ausschließlich serverseitig.
  - **Test:** `tests/test_job_infra_adapters.py` (tenant-scoped key assertion).
- **Threat:** Nicht-auditierbare Sicherheitsereignisse im neuen Adapter-Layer.
  - **Control:** Append-only JSONL Audit-Logger mit Pflichtfeldern und Zeitstempel.
  - **Test:** `tests/test_job_infra_adapters.py` (Audit append verification).


## Ergänzung 2026-03-07 – WP-3.3 Risiken
- **Threat:** Doppel-Queueing/Replay bei wiederholtem `complete-upload`.
  - **Control:** tenant-scoped Idempotenzstore mit Payload-Hash-Bindung.
  - **Test:** `tests/test_complete_upload_service.py` (repeat + conflict).
- **Threat:** Inkonsistenz zwischen Statuswechsel und Queue-Publish.
  - **Control:** Outbox-Persistenz + separater Dispatcher.
  - **Test:** `tests/test_complete_upload_infrastructure.py` (dispatch + mark_published).
- **Threat:** Information Disclosure bei tenant-fremder Job-ID.
  - **Control:** tenant-scoped Lookup mit neutralem `job.not_found`.
  - **Test:** `tests/test_complete_upload_service.py` (cross-tenant deny).


## Ergänzung 2026-03-07 – WP-3.4 Risiken
- **Threat:** Enumerationsangriffe auf Job-IDs über Statusendpoint.
  - **Control:** tenant-scoped Lookup + neutrales `job.not_found`.
  - **Test:** `tests/test_job_status_service.py` (cross-tenant not found).
- **Threat:** Unklare Status-/Progress-Semantik führt zu fehlerhaften Operator-Entscheidungen.
  - **Control:** normierte Fallback-Progresslogik und explizites Response-Mapping.
  - **Test:** `tests/test_job_status_service.py`, `tests/test_job_status_http_adapter.py`.
## Ergaenzung 2026-03-22 - Tenant-Admin Decoding-Settings
- **Threat:** Privilegienmissbrauch auf transkriptionsrelevante Runtime-Parameter.
  - **Control:** `GET/PUT /api/v1/admin/transcription-settings` nur mit `admin`-Rolle.
  - **Test:** `tests/test_fastapi_http_adapter_integration.py` (`403` fuer Non-Admin, `200` fuer Admin).
- **Threat:** Cross-Tenant-Konfigurationsmanipulation.
  - **Control:** tenant-scoped Persistenz (`tenant_transcription_settings`) und tenant-gebundene API-Auswertung.
  - **Test:** Integrations-/Repository-Tests fuer tenant-sicheren Roundtrip.
- **Threat:** Schad- oder Fehlkonfiguration durch unvalidierte Decoding-Parameter.
  - **Control:** Feld-Whitelist + Range-Validation + defensive Worker-Normalisierung.
  - **Test:** `tests/test_transcription_settings_service.py`, `tests/test_worker_runner.py`.
- **Threat:** Informationsabfluss ueber Audit durch Klartext-`initial_prompt`.
  - **Control:** Audit nur mit Prompt-Hash/Laenge, ohne Klartext.
  - **Test:** Service-Tests auf audit payload ohne `initial_prompt`.

## Ergaenzung 2026-03-24 - Threats Korrekturmodus
- **Threat:** Session-Entfuehrung im Korrekturmodus.
  - **Control:** tenant-/actor-scoped Session-Validierung in allen Session-Endpunkten (inkl. Read).
  - **Test:** Session-Read/Mutation durch fremden Actor fuehrt zu `transcript.correction_session_forbidden`.
- **Threat:** Timeline-Korruption durch fehlerhafte Speaker-Teilumteilung oder falsche Gap-Interpretation.
  - **Control:** verpflichtende Timeline-Invariant-Checks bei jeder Operation; Overlaps werden blockiert, Luecken sind erlaubt und muessen im Korrekturmodus als kein aktiver Block gerendert werden.
  - **Test:** Overlap Injection wird mit `transcript.timeline_*` geblockt; Gap-Windows bleiben valide und duerfen nicht als Inkonsistenz markiert werden.
- **Threat:** Silent State Drift zwischen Draft und persistierter Version.
  - **Control:** klare Trennung Draft (Autosave) vs Commit (Version+1) mit Audit-Event.
  - **Test:** Commit ist einziger Pfad fuer neue `transcript_version`.
- **Threat:** Unautorisierte Status-/Final-Setzung.
  - **Control:** Endpoint-Rollenpruefung (`reviewer|admin`) + Audit.
  - **Test:** `user` ohne Rolle kann Status nicht setzen.

## Ergaenzung 2026-03-25 - Threats Korrekturmodus Handover
- Threat: Handover-Token-Abgriff zwischen Haupttab und neuem Korrektur-Tab.
  - Control: single-use Handover-Store mit kurzer TTL; Consume entfernt den Eintrag sofort, Cleanup entfernt abgelaufene Eintraege.
  - Test: Frontend-Unit fuer create/consume/expiry/cleanup und E2E-Start ohne In-Tab-Fallback.
- Threat: Medienquelle im Workspace nicht tenant-scoped.
  - Control: GET /api/v1/jobs/{id}/media-source nutzt tenant-scoped Job-Lookup und liefert bei Cross-Tenant neutral 404.
  - Test: Contract-/Integrationstests fuer 200/404/503 Pfade.
