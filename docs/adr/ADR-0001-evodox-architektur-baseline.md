# ADR-0001: EvidoX Architektur-Baseline (On-Prem, Multi-Tenant, Queue-Processing)

## Status
Accepted

## Kontext
EvidoX muss große Audio-/Videodateien transkribieren, mandantenfähig betrieben werden und on-premise ohne externe Runtime-Abhängigkeit von OpenAI funktionieren.

## Entscheidung
1. Multi-Tenant-Architektur mit logischer Isolation (`tenant_id` durchgängig)
2. On-Prem Betrieb in Docker-Containern
3. FastAPI + React + Celery + RabbitMQ + PostgreSQL + MinIO + Keycloak + NGINX
4. Asynchrone queue-basierte Verarbeitung mit horizontal skalierbaren Workern
5. Laufzeitbetrieb mit lokalem Modellcache/Repository (kein externer OpenAI-API-Zwang)
6. Standard-Löschfrist per ENV (`EVIDOX_DEFAULT_RETENTION_MONTHS`)

## Konsequenzen
- Positiv: gute Skalierbarkeit, hohe Wartbarkeit, entkoppelte Verarbeitung
- Positiv: bessere Kostenkontrolle und Compliance im On-Prem-Betrieb
- Negativ: höhere Komplexität bei Tenant-Isolation, Monitoring und Queue-Tuning
- Erfordert verpflichtende Isolationstests und Security-Audits
