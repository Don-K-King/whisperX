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
