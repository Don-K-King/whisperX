# Data Flow – EvidoX

1. Benutzer meldet sich über Keycloak an (OIDC PKCE).
2. Frontend erstellt Job mit optionalem `retention_months`.
3. API erzeugt Jobdatensatz (`tenant_id`, `retention_until`) und Presigned Upload URL.
4. Frontend lädt Datei direkt nach MinIO (resumable/chunked).
5. API finalisiert Upload und enqueue’t Verarbeitung in RabbitMQ.
6. Worker verarbeitet asynchron (WhisperX + Diarization), speichert Artefakte + Status.
7. Frontend lädt Transkript, Benutzer editiert Versionen.
8. Export wird erzeugt (initialer Edit-Export) und als signierter Download bereitgestellt.
9. Retention-Job entfernt Artefakte/Daten nach Frist und schreibt Audit-Ereignisse.


## WP-4 Ergänzung
- Zwischen Schritt 6 und 7 gilt: Worker-Pipeline führt `ASR -> Alignment -> Diarization` aus, persistiert tenant-scoped Artefakte und klassifiziert Fehler in retryable/terminal für Queue-Governance.
- Scheduling erfolgt tenant-fair mit Backpressure-Limits (global + pro Tenant), um Starvation und Ressourcen-Monopolisierung zu vermeiden.

- Schritt-5 Ergänzung: Transcript-Edits werden versioniert gespeichert (`base_version`-Konflikterkennung), Exporte werden tenant-scoped erzeugt und nur in erlaubten Zielformaten bereitgestellt.
