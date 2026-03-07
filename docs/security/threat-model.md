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
