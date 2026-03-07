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
