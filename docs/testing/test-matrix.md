# Test Matrix (inkl. Edge-/Abuse-Schwerpunkte)

| Anforderung | Unit | Integration | Contract | E2E | Security/Abuse | Priorität | Gate |
|---|---|---|---|---|---|---|---|
| OIDC Login + Rollen | Ja | Ja | Ja | Ja | Token Replay, Expiry, Audience/Issuer Mismatch | P0 | Muss grün |
| Tenant-Isolation | Ja | Ja | Nein | Ja | Cross-Tenant Zugriff, Claim-Manipulation | P0 | Muss grün |
| Upload großer Dateien | Ja | Ja | Ja | Ja | MIME Spoofing, Chunk-Tampering, Oversize, Rate-Limit | P0 | Muss grün |
| Queue/Retry/DLQ | Ja | Ja | Ja | Optional | Poison Messages, Duplicate Delivery, Retry-Storm | P0 | Muss grün |
| Verarbeitung (ASR+Alignment+Diarization) | Nein | Ja | Nein | Ja | Malformed Media, Worker-Restart | P0 | Muss grün |
| Transcript-Edit/Versionierung | Ja | Ja | Nein | Ja | XSS/Injection, Unicode Edge Cases | P1 | Muss grün |
| Export (TXT/JSON/SRT/VTT) | Ja | Ja | Ja | Ja | Export-AuthZ, Format-Manipulation | P1 | Muss grün |
| Retention + Audit | Ja | Ja | Nein | Optional | Manipulation `retention_months`, Audit-Vollständigkeit | P0 | Muss grün |
| Prompt-Injection-Resilienz | Ja | Ja | Nein | Optional | „Ignore instructions“-Payloads als Daten behandeln | P0 | Muss grün |
| On-Prem Docker Betrieb | Nein | Ja | Nein | Optional | Fehlkonfig, offene Ports, Secret-Leaks | P1 | Muss grün |


## Gate-Reihenfolge und Freigabenachweis
1. Lint/Schema-Validation
2. Unit
3. Integration
4. Contract
5. Security/Abuse
6. E2E/Regression (verpflichtend bei Pipeline/Build/Architektur/Strukturänderungen)

### Nachweispflicht pro Gate
- Verantwortliches Team
- Verwendete Testumgebung
- Commit SHA und Build-Artefakt
- Ergebnis (Pass/Fail) und ggf. Risikoeinschätzung


## WP-3.1 Nachweis (Auth Middleware + Tenant Context)
- Unit/Abuse: `tests/test_auth_tenant_context.py` deckt Happy Path, Claim-Fehler, Token-Ablauf, Audience-Mismatch, Rollen-/Tenant-Deny ab.
- Gate-Zuordnung: Unit + Security/Abuse (P0, Muss grün).


## WP-3.2 Nachweis (Job-Create Endpoint + Upload Session)
- Unit: Validatoren für MIME/Size/Retention/Filename/Idempotency-Key.
- Integration: Tenant-scoped Job-Persistenz, Upload-Session-Erstellung und Audit-Event.
- Security/Abuse: Oversize, unsupported MIME, Idempotency-Key-Payload-Konflikt.
- Nachweisdatei: `tests/test_job_create_service.py`.


## Adapter-Umsetzung Nachweis (HTTP + Infrastruktur)
- Integration (Infrastruktur): SQLite-Repo, SQLite-Idempotenz, Presign-Factory, JSONL-Audit (`tests/test_job_infra_adapters.py`).
- Contract/Core (HTTP): Mapping Domain→API-Contract (`tests/test_fastapi_http_adapter.py`).
- Integration (HTTP/optional): Endpunkt-Test mit FastAPI TestClient (`tests/test_fastapi_http_adapter_integration.py`, umgebungsabhängig).
- Regression: vollständiger lokaler `unittest`-Discover-Lauf nach Strukturänderung durchgeführt.


## WP-3.3 Nachweis (Complete-Upload Idempotency + Queue Publish)
- Unit/Integration: `tests/test_complete_upload_service.py` (Happy Path, State/Storage checks, tenant deny, checksum validation).
- Infrastruktur/Integration: `tests/test_complete_upload_infrastructure.py` (SQLite Outbox + Dispatcher Publish/Marking).
- Contract/Core HTTP: `tests/test_complete_upload_http_adapter.py` (Response-Mapping `queued` + `queue`).
- Regression: vollständiger lokaler `unittest`-Discover-Lauf nach Strukturänderung durchgeführt.


## WP-3.4 Nachweis (Job-Status Endpoint)
- Unit/Integration: `tests/test_job_status_service.py` (tenant-scoped read, progress fallback, not-found ohne Leak).
- Contract/Core HTTP: `tests/test_job_status_http_adapter.py` (Response-Mapping).
- Integration (HTTP/optional): `tests/test_fastapi_http_adapter_integration.py` ergänzt um GET-Status-Fall.


## WP-4.1 Nachweis (Queue Routing + Retry/DLQ Governance)
- Unit/Integration: `tests/test_complete_upload_infrastructure.py` deckt Retry/Backoff+Jitter, DLQ-Routing, Duplicate-Delivery-Handling und Dispatcher-Statusübergänge ab.
- Infrastruktur/Adapter: `tests/test_job_infra_adapters.py` prüft RabbitMQ-Adapter-Fehlerabbildung auf Retryable-Fehlerklasse.
- Regression: vollständiger `unittest`-Discover-Lauf über `tests/` nach struktureller Infrastrukturänderung durchgeführt.


## WP-4.2 Nachweis (Worker Processing Chain)
- Unit/Integration: `tests/test_worker_pipeline_service.py` prüft Happy Path, malformed-media Terminalpfad, retryable Fehlerpfad und tenant-scope Object-Key-Abuse-Fall.

## WP-4.3 Nachweis (Tenant-Fairness + Backpressure)
- Unit/Integration: `tests/test_tenant_fairness_policy.py` prüft globale/per-tenant Backpressure und starvation-armes Round-Robin-Scheduling.


## WP-5.1 Nachweis (Transcript-Versionierung)
- Unit/Integration: `tests/test_transcript_service.py` deckt Read, optimistic-lock Konflikt und Abuse-Fall (ungültige Segmenttexte) ab.
- Contract/Core HTTP: `tests/test_transcript_http_adapter.py` prüft Mapping für GET/PUT-Transcript-Responses.

## WP-5.2 Nachweis (Export-Pipeline)
- Unit/Integration: `tests/test_export_service.py` deckt Export-Queueing, SRT-Rendering und Format-Validierung ab.
- Contract/Core HTTP: `tests/test_export_http_adapter.py` prüft Mapping des Export-Responseschemas.


## WP-6.1 Nachweis (Retention Enforcement)
- Unit/Integration: `tests/test_retention_service.py` deckt Policy-Resolver (Tenant-Default + Clamp), tenant-isolierte Verarbeitung, Clock-Skew-Schutz sowie Teilfehlerfälle (Storage/DB) ab.
- Infrastruktur/Integration: `tests/test_job_infra_adapters.py` erweitert um tenant-scoped Candidate-Query und delete/anonymize-Pfad in SQLite-Adaptern.
- Security/Abuse: manipulierte Retention-Werte und Cross-Tenant-Delete-Fehlstrategie als Negativpfade getestet.


## WP-6.2 Nachweis (Restore + Konsistenzprüfung + Scheduler)
- Unit/Integration: `tests/test_restore_service.py` validiert Restore-Reihenfolge, tenant-guards und Konsistenzfindings.
- Unit/Integration: `tests/test_retention_scheduler.py` validiert Intervallsteuerung und idempotente Recovery je Teilfehlerklasse.
- Security/Abuse: Cross-Tenant-Restore und tenant-fremde Object-Keys als Negativpfade getestet.
