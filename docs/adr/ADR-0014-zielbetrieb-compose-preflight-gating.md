# ADR-0014: Zielbetrieb via Docker Compose mit Preflight-Gating

- Status: Accepted
- Datum: 2026-03-08

## Kontext
Für den Zielbetrieb müssen API, Worker, Retention-Runner, Datenbank, Broker, Object-Storage und Auth reproduzierbar ausrollbar sein. Bisher fehlen verbindliche Deploy-Artefakte mit Preflight-Gating für fail-fast Konfigurationsvalidierung.

## Entscheidung
1. Einführung von `deploy/docker-compose.target.yml` als verbindliches Referenzartefakt mit den Services `api`, `worker`, `retention-runner`, `db`, `broker`, `object-storage`, `auth`.
2. Ergänzung eines one-shot Preflight-Services `retention-preflight` mit `RETENTION_VALIDATE_ENV_ONLY=true`, der den Applikationsstart via `service_completed_successfully` blockiert.
3. Ergänzung einer CI-Stage `.github/workflows/deployment-preflight.yml`, die die gleiche Preflight-Validierung im Pull-Request erzwungen ausführt.
4. Standardisierung der Betriebsprofile über `.env.example` und `.env.production.example`.

## Sicherheitsauswirkungen
- Fail-fast reduziert Fehlstarts mit unsicheren/inkonsistenten ENV-Konfigurationen.
- Secret-Handling wird explizit auf Secret-Manager-Injektion ausgerichtet (keine Klartext-Secrets im Repo).
- Risiko verbleibt: Compose-Healthchecks sind weniger strikt als orchestrator-native Probes. Gegenmaßnahme: zusätzlicher CI-Preflight und explizite Runbook-Prüfschritte.

## Architekturfolgen
- Positiv: reproduzierbarer Einstiegspfad für On-Prem-Betrieb und klare Entkopplung Retention-Runner vs. API.
- Trade-off: Compose ist für Skalierung/HA begrenzt; mittelfristig sollte eine Kubernetes-Referenz mit `initContainers` und feingranularen ServiceAccounts bereitgestellt werden.

## Alternativen
- **Nur CI-Preflight, kein Compose-Gate:** verworfen, weil Runtime-Fehlkonfigurationen in Betriebsumgebung unentdeckt bleiben können.
- **Nur Compose-Preflight, kein CI-Job:** verworfen, weil PRs ohne automatischen Blocker in Mainline gelangen könnten.

## Umgesetzte Artefakte
- `deploy/docker-compose.target.yml`
- `.github/workflows/deployment-preflight.yml`
- `.env.example`
- `.env.production.example`
- `docs/operations/runbooks.md`
- `docs/operations/monitoring-alerting.md`
- `deploy/prometheus/alerts-targetbetrieb.yml`
