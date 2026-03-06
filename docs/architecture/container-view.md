# Container View – EvidoX

## Frontend Container
- React/TypeScript SPA
- OIDC Login (PKCE)
- Upload, Jobmonitoring, Transkript-Editor, Export
- Anzeige/Übergabe von `retention_months`

## API Container
- FastAPI
- OIDC Token Validation + RBAC/Tenant AuthZ
- Job-/Transcript-/Export-API
- Presigned Upload URLs
- Audit Event Emission

## Worker Container
- Celery Worker
- Konsumiert RabbitMQ Queues
- Führt WhisperX-Pipeline aus
- Schreibt Artefakte in Storage, Status in DB

## Daten-/Infra-Container
- RabbitMQ (durable queues + DLQ)
- PostgreSQL (mandantenfähiges Datenmodell)
- MinIO (S3-kompatibel)
- Keycloak
- NGINX Reverse Proxy
