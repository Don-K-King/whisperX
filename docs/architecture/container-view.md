# Container View - EvidoX

## Istbetrieb (lokale Runtime)
- Frontend: React/TypeScript SPA mit OIDC-Login (PKCE).
- API: FastAPI mit tenant-scoped AuthZ, Upload-/Job-/Transcript-/Export-API.
- Worker: Celery Worker fuer WhisperX-Pipeline, lokale Runtime-Adapter und Objektverarbeitung.
- Persistenz: SQLite-basierte Runtime-Pfade fuer lokale Entwicklung und Tests.
- Infrastruktur: RabbitMQ, MinIO, Keycloak und NGINX.

## Zielbetrieb (produktiver Referenz-Stack)
- Frontend: gleiche SPA, gleiche UI-Vertraege.
- API: FastAPI mit OIDC Token Validation, RBAC und Tenant-AuthZ.
- Worker: horizontal skalierbare Worker-Pools mit Queue-Isolation.
- Persistenz: PostgreSQL als Ziel-Datenbank fuer das mandantenfaehige Datenmodell.
- Infrastruktur: RabbitMQ, PostgreSQL, MinIO, Keycloak und NGINX.

## Architekturhinweise
- Der Istbetrieb darf sich in der lokalen Laufzeit von der Zielarchitektur unterscheiden, solange Contracts, Tenant-Isolation und Auditierbarkeit konsistent bleiben.
- Der Zielbetrieb ist die normative Referenz fuer Skalierung, Betrieb und Deployment.
- SQLite im Istbetrieb ist ein Laufzeitdetail, kein Widerspruch zur PostgreSQL-Zielarchitektur.
