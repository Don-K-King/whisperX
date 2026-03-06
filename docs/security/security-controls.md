# Security Controls

## Identität & Zugriff
- OIDC JWT Validation (signaturbasiert)
- RBAC + Tenant Claims
- Default Deny bei fehlendem Tenant-Kontext

## Daten- und Mandantenschutz
- `tenant_id` in allen relevanten Tabellen und APIs
- Query-Guards und Service-Layer-Prüfungen
- Export nur innerhalb Tenant Scope

## Upload- und Verarbeitungs-Sicherheit
- Dateityp-/Signaturprüfung
- Maximalgrößen und Ratenlimits
- Queue-Isolation durch Routing-Keys und Quoten

## Compliance
- Retention Default: `EVIDOX_DEFAULT_RETENTION_MONTHS`
- Audit-Log für Erstellung, Zugriff, Export, Löschung
