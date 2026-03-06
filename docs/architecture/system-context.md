# System Context – EvidoX

## Betriebsrahmen
- Deployment on-premise in Docker-Containern.
- Zugriff ausschließlich über Reverse Proxy (TLS-Termination, Sicherheitsheader, Routing).
- Authentifizierung/Benutzerverwaltung über Keycloak.

## Externe/angrenzende Systeme
- Keycloak (OIDC, Rollen, Tenant-Claims)
- S3-kompatibles Object Storage (MinIO)
- PostgreSQL
- RabbitMQ
- Optionales internes Modell-Repository/Artefakt-Cache

## Fachlicher Scope
- Upload großer Audio-/Videodateien als Jobs
- Volltranskription via WhisperX + Diarization
- Editierbares Transkript
- Initialer Edit-Export
- Mandantenfähiger Betrieb

## Nicht-Ziele (Phase 1)
- Kein SaaS-Cloud-Mandantenbetrieb
- Keine harte Abhängigkeit von externer OpenAI-API im Runtime-Betrieb
