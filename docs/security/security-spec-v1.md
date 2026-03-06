# Security-Spezifikation v1

## Ziel
Verbindliche Sicherheitskontrollen für Phase 1 mit Zuordnung zu Systemkomponenten.

## Bedrohungen und Kontrollen (komponentenbezogen)

| Risiko | Komponente | Maßnahme | Verifikation |
|---|---|---|---|
| Cross-Tenant Data Leakage | API, DB, Worker, Export | Tenant-Claim-Prüfung, Query-Filter auf `tenant_id`, tenant-scoped object keys | Unit/Integration-Isolationstests |
| Token-Missbrauch | API | OIDC Signaturprüfung, `iss/aud/exp`-Validierung, kurze TTL | AuthN/Contract-Tests |
| Upload Abuse/DoS | Proxy, API, Storage | Rate-Limits, Größenlimits, Chunk-Validierung, MIME+Magic-Byte-Prüfung | Edge-/Abuse-Tests |
| Malicious Content in Transcript | Frontend, Export | Output-Encoding, keine Ausführung eingebetteter Instruktionen, Sanitization | XSS/Injection-Tests |
| Queue Poisoning | Queue, Worker | Signierte/validierte Event-Schemata, Retry/DLQ, idempotente Consumer | Integration/Chaos-Tests |
| Retention-Manipulation | API, DB, Scheduler | Bereichsvalidierung, Rollenprüfung, auditierte Policy-Änderung | Unit/Integration-Tests |
| Secret Leakage | Runtime/Operations | Secrets nur via Secret Store/Env Mounts, keine Logs mit Secrets | Betriebschecks + SAST |

## AuthN/AuthZ Mindestregeln
- AuthN ist für alle API-Endpunkte verpflichtend außer Healthchecks.
- AuthZ entscheidet immer über Kombination aus Rolle + Tenant.
- `admin` ist tenant-lokal, kein globaler Root-Operator in Phase 1.
- `/api/v1/audit` nur für `admin`.

## Input-Validation Mindestregeln
- Upload: Dateiendung, MIME, Magic Bytes, Größe, Chunk-Sequenz.
- API JSON: striktes Schema, Feldlängen, enum-Whitelists.
- Textfelder: Unicode normalisieren, Steuerzeichen und Nullbytes ablehnen.

## Logging und Audit
- Sicherheitsrelevante Ereignisse sind auditpflichtig (`auth_fail`, `authz_deny`, `retention_change`, `dlq_event`).
- Audit-Events enthalten `tenant_id`, `actor`, `correlation_id`.
- Audit-Logs sind append-only und manipulationsresistent.

## Restrisiken und Behandlung
1. **Restrisiko:** Fehlkonfiguration von Proxy-Limits in On-Prem Deployments.
   - **Behandlung:** Konfigurations-Tests als Deployment-Gate.
2. **Restrisiko:** GPU-Ressourcenengpässe unter Last.
   - **Behandlung:** Queue-Isolation, Worker-Concurrency-Caps, Monitoring-Alerts.
