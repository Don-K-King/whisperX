# Test Matrix (inkl. Edge-/Abuse-Schwerpunkte)

| Anforderung | Unit | Integration | Contract | E2E | Security/Abuse | PrioritÃ¤t | Gate |
|---|---|---|---|---|---|---|---|
| OIDC Login + Rollen | Ja | Ja | Ja | Ja | Token Replay, Expiry, Audience/Issuer Mismatch | P0 | Muss grÃ¼n |
| Tenant-Isolation | Ja | Ja | Nein | Ja | Cross-Tenant Zugriff, Claim-Manipulation | P0 | Muss grÃ¼n |
| Upload groÃŸer Dateien | Ja | Ja | Ja | Ja | MIME Spoofing, Chunk-Tampering, Oversize, Rate-Limit | P0 | Muss grÃ¼n |
| Queue/Retry/DLQ | Ja | Ja | Ja | Optional | Poison Messages, Duplicate Delivery, Retry-Storm | P0 | Muss grÃ¼n |
| Verarbeitung (ASR+Alignment+Diarization) | Nein | Ja | Nein | Ja | Malformed Media, Worker-Restart | P0 | Muss grÃ¼n |
| Transcript-Edit/Versionierung | Ja | Ja | Nein | Ja | XSS/Injection, Unicode Edge Cases | P1 | Muss grÃ¼n |
| Speaker-Alias + Blockbildung | Ja | Ja | Ja | Ja | Alias-Injection, Cross-Tenant, Control Characters, falsche Blockfusion | P1 | Muss grÃ¼n |
| Export (TXT/JSON/SRT/VTT) | Ja | Ja | Ja | Ja | Export-AuthZ, Format-Manipulation | P1 | Muss grÃ¼n |
| Retention + Audit | Ja | Ja | Nein | Optional | Manipulation `retention_months`, Audit-VollstÃ¤ndigkeit | P0 | Muss grÃ¼n |
| Prompt-Injection-Resilienz | Ja | Ja | Nein | Optional | â€žIgnore instructionsâ€œ-Payloads als Daten behandeln | P0 | Muss grÃ¼n |
| On-Prem Docker Betrieb | Nein | Ja | Nein | Optional | Fehlkonfig, offene Ports, Secret-Leaks | P1 | Muss grÃ¼n |


## Gate-Reihenfolge und Freigabenachweis
1. Lint/Schema-Validation
2. Unit
3. Integration
4. Contract
5. Security/Abuse
6. E2E/Regression (verpflichtend bei Pipeline/Build/Architektur/StrukturÃ¤nderungen)

### Nachweispflicht pro Gate
- Verantwortliches Team
- Verwendete Testumgebung
- Commit SHA und Build-Artefakt
- Ergebnis (Pass/Fail) und ggf. RisikoeinschÃ¤tzung


## WP-3.1 Nachweis (Auth Middleware + Tenant Context)
- Unit/Abuse: `tests/test_auth_tenant_context.py` deckt Happy Path, Claim-Fehler, Token-Ablauf, Audience-Mismatch, Rollen-/Tenant-Deny ab.
- Gate-Zuordnung: Unit + Security/Abuse (P0, Muss grÃ¼n).


## WP-3.2 Nachweis (Job-Create Endpoint + Upload Session)
- Unit: Validatoren fÃ¼r MIME/Size/Retention/Filename/Idempotency-Key.
- Integration: Tenant-scoped Job-Persistenz, Upload-Session-Erstellung und Audit-Event.
- Security/Abuse: Oversize, unsupported MIME, Idempotency-Key-Payload-Konflikt.
- Nachweisdatei: `tests/test_job_create_service.py`.


## Adapter-Umsetzung Nachweis (HTTP + Infrastruktur)
- Integration (Infrastruktur): SQLite-Repo, SQLite-Idempotenz, Presign-Factory, JSONL-Audit (`tests/test_job_infra_adapters.py`).
- Contract/Core (HTTP): Mapping Domainâ†’API-Contract (`tests/test_fastapi_http_adapter.py`).
- Integration (HTTP/optional): Endpunkt-Test mit FastAPI TestClient (`tests/test_fastapi_http_adapter_integration.py`, umgebungsabhÃ¤ngig).
- Regression: vollstÃ¤ndiger lokaler `unittest`-Discover-Lauf nach StrukturÃ¤nderung durchgefÃ¼hrt.


## WP-3.3 Nachweis (Complete-Upload Idempotency + Queue Publish)
- Unit/Integration: `tests/test_complete_upload_service.py` (Happy Path, State/Storage checks, tenant deny, checksum validation).
- Infrastruktur/Integration: `tests/test_complete_upload_infrastructure.py` (SQLite Outbox + Dispatcher Publish/Marking).
- Contract/Core HTTP: `tests/test_complete_upload_http_adapter.py` (Response-Mapping `queued` + `queue`).
- Regression: vollstÃ¤ndiger lokaler `unittest`-Discover-Lauf nach StrukturÃ¤nderung durchgefÃ¼hrt.


## WP-3.4 Nachweis (Job-Status Endpoint)
- Unit/Integration: `tests/test_job_status_service.py` (tenant-scoped read, progress fallback, not-found ohne Leak).
- Contract/Core HTTP: `tests/test_job_status_http_adapter.py` (Response-Mapping).
- Integration (HTTP/optional): `tests/test_fastapi_http_adapter_integration.py` ergÃ¤nzt um GET-Status-Fall.


## WP-4.1 Nachweis (Queue Routing + Retry/DLQ Governance)
- Unit/Integration: `tests/test_complete_upload_infrastructure.py` deckt Retry/Backoff+Jitter, DLQ-Routing, Duplicate-Delivery-Handling und Dispatcher-StatusÃ¼bergÃ¤nge ab.
- Infrastruktur/Adapter: `tests/test_job_infra_adapters.py` prÃ¼ft RabbitMQ-Adapter-Fehlerabbildung auf Retryable-Fehlerklasse.
- Regression: vollstÃ¤ndiger `unittest`-Discover-Lauf Ã¼ber `tests/` nach struktureller InfrastrukturÃ¤nderung durchgefÃ¼hrt.


## WP-4.2 Nachweis (Worker Processing Chain)
- Unit/Integration: `tests/test_worker_pipeline_service.py` prÃ¼ft Happy Path, malformed-media Terminalpfad, retryable Fehlerpfad und tenant-scope Object-Key-Abuse-Fall.

## WP-4.3 Nachweis (Tenant-Fairness + Backpressure)
- Unit/Integration: `tests/test_tenant_fairness_policy.py` prÃ¼ft globale/per-tenant Backpressure und starvation-armes Round-Robin-Scheduling.


## WP-5.1 Nachweis (Transcript-Versionierung)
- Unit/Integration: `tests/test_transcript_service.py` deckt Read, optimistic-lock Konflikt und Abuse-Fall (ungÃ¼ltige Segmenttexte) ab.
- Contract/Core HTTP: `tests/test_transcript_http_adapter.py` prÃ¼ft Mapping fÃ¼r GET/PUT-Transcript-Responses.
- Zusatz: Speaker-Alias-Update und Blockbildung werden als eigener Nachweis im gleichen Schritt gefordert.

## WP-5.2 Nachweis (Export-Pipeline)
- Unit/Integration: `tests/test_export_service.py` deckt Export-Queueing, SRT-Rendering und Format-Validierung ab.
- Contract/Core HTTP: `tests/test_export_http_adapter.py` prÃ¼ft Mapping des Export-Responseschemas.


## WP-6.1 Nachweis (Retention Enforcement)
- Unit/Integration: `tests/test_retention_service.py` deckt Policy-Resolver (Tenant-Default + Clamp), tenant-isolierte Verarbeitung, Clock-Skew-Schutz sowie TeilfehlerfÃ¤lle (Storage/DB) ab.
- Infrastruktur/Integration: `tests/test_job_infra_adapters.py` erweitert um tenant-scoped Candidate-Query und delete/anonymize-Pfad in SQLite-Adaptern.
- Security/Abuse: manipulierte Retention-Werte und Cross-Tenant-Delete-Fehlstrategie als Negativpfade getestet.


## WP-6.2 Nachweis (Restore + KonsistenzprÃ¼fung + Scheduler)
- Unit/Integration: `tests/test_restore_service.py` validiert Restore-Reihenfolge, tenant-guards und Konsistenzfindings.
- Unit/Integration: `tests/test_retention_scheduler.py` validiert Intervallsteuerung und idempotente Recovery je Teilfehlerklasse.
- Security/Abuse: Cross-Tenant-Restore und tenant-fremde Object-Keys als Negativpfade getestet.

## E2E-Nachweis (Job Lifecycle Kernfluss)
- E2E/Integration: `tests/test_job_lifecycle_e2e.py` deckt den tenant-scoped End-to-End-Kernfluss `create_job` â†’ `complete_upload` â†’ `OutboxQueueDispatcher.dispatch_pending` â†’ `get_job_status` in einer realen SQLite-Infrastrukturkette ab.
- Security-Fokus: Objektpfad bleibt tenant/job-gebunden, Queue-Message enthÃ¤lt Tenant-Kontext, Statusabfrage erfolgt weiterhin tenant-isoliert.


## 2026-03-24 - Matrix-Ergaenzung Korrekturmodus
| Anforderung | Unit | Integration | Contract | E2E | Security/Abuse | Prioritaet | Gate |
|---|---|---|---|---|---|---|---|
| Correction Sessions (Draft/Undo/Redo/Discard/Commit) | Ja | Ja | Ja | Ja | Session-Hijack, stale base_version, actor mismatch | P0 | Muss gruen |
| Timeline-Integritaet bei Korrekturen | Ja | Ja | Nein | Ja | Overlap/Gap Injection, invalid Char-Ranges | P0 | Muss gruen |
| Transcript-Status (`review_status`, `is_final`) | Ja | Ja | Ja | Ja | Unautorisierte Statusaenderung, Audit-Luecken | P1 | Muss gruen |
| Korrektur-Workspace (Popup/New-Tab, kein Fallback) | Ja | Ja | Nein | Ja | Popup-Blocker, handoff expiry/single-use misuse | P1 | Muss gruen |
| Suche/Ersetzen + Sprecherfilter | Ja | Ja | Nein | Ja | Replace-Missbrauch, no-match Fehlpfade | P1 | Muss gruen |
