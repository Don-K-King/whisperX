# Security Architecture – EvidoX

## Zentrale Sicherheitsprinzipien
- Default Deny + Least Privilege
- Mandantenisolation als Primärkontrolle
- Vollständige Auditierbarkeit sicherheitsrelevanter Aktionen

## Kontrollen
- OIDC Tokens: issuer/audience/signature validieren
- Tenant-Scoping bei jedem Datenzugriff (API, DB, Export)
- Upload-Härtung: MIME/Magic-Bytes, Größenlimits, optional Malware-Scan
- Verschlüsselung in Transit (TLS) und at Rest (DB/Storage)
- Secrets ausschließlich über Secret Management

## Kritische Risiken
- Cross-Tenant Data Leakage
- Überlastung durch große Uploads/Jobs
- Modell-Lieferkettenrisiken

## Gegenmaßnahmen
- Isolationstests + Audit Trails
- Queue-basierte Backpressure + Ratenlimits
- Signierte Modellartefakte + versionierter lokaler Modellcache
