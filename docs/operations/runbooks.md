# Runbooks

## Betrieb (On-Prem Docker)
- Startreihenfolge: Keycloak, PostgreSQL, MinIO, RabbitMQ, API, Worker, Frontend, NGINX
- Healthchecks für API/Worker/Broker/DB/Storage verpflichtend

## Incident: Queue-Stau
1. Queue-Lag prüfen
2. Worker-Skalierung erhöhen (zusätzliche Container)
3. Priorisierung auf kritische Queues anpassen
4. DLQ analysieren

## Incident: Tenant-Isolation Alert
1. Betroffene Tenant-Scopes identifizieren
2. Zugriffslogs und Audit Events sichern
3. betroffene Endpunkte temporär drosseln/abschalten
4. Security Hotfix mit Isolationstests ausrollen


## Reproduzierbarer Build-/Release-Runbook
1. Commit SHA und Branch fixieren
2. Container mit gepinnten Basisimages bauen (Tag + Digest)
3. Build-Provenance erfassen (SHA, Digests, Build-Zeitpunkt, SBOM-Referenz)
4. Pflicht-Gates in Reihenfolge ausführen
5. Release nur bei vollständig grünen Blocker-Gates
