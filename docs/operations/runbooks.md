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


## Runbook: Retention Enforcement (WP-6.1)
1. Job-Scheduler prüfen (Intervall, letzte erfolgreiche Ausführung, Laufzeit).
2. Backlog prüfen: Anzahl fälliger Retention-Kandidaten pro Tenant.
3. Fehlerquote prüfen: Teilfehler (`retention.execution.failed`) getrennt nach Ursache `storage_deleted=false` bzw. `db_marked=false`.
4. Bei anhaltenden Teilfehlern: erneute Ausführung nur tenant-scoped und mit begrenzter Batchgröße starten.
5. Audit-Stichprobe durchführen: je gelöschtem Job müssen `retention.decision` und `retention.execution` vorhanden sein.
6. Incident-Fall: Bei Cross-Tenant-Anomalie Scheduler sofort stoppen, Audit-Log sichern, betroffene Tenant-IDs isolieren und Security-Incident-Prozess starten.


## Runbook: Tenant-sicherer Restore (WP-6.2)
1. Restore nur mit Admin-Auth im Tenant-Kontext starten; `tenant_id`-Match verifizieren.
2. Restore-Reihenfolge strikt einhalten: `jobs -> transcripts -> transcript_versions -> export_artifacts -> audit_events -> storage`.
3. Nachlauf prüfen: Konsistenzcheck ausführen und Findings klassifizieren (kritisch/nicht kritisch).
4. Bei kritischen Findings: Freigabe stoppen, Incident-Prozess auslösen, keine Nutzerfreischaltung.
5. Betriebsdrill protokollieren (Dauer, Findings, Cross-Tenant-Negativtest, Freigabeentscheidung).

## Incident-Runbook final (Retention/Restore)
- Trigger: Cross-Tenant-Verdacht, wiederholte Recovery-Fehler, kritische Restore-Findings.
- Maßnahmen:
  1. Scheduler pausieren und aktive Restore-Jobs stoppen.
  2. Audit-/Backup-Artefakte unveränderlich sichern.
  3. Tenant-spezifische Eingrenzung und Auswirkungsanalyse durchführen.
  4. Hotfix + Regression + gezielter Restore-Drill vor Re-Enable.


## 2026-03-08 – Runbook-Ergänzung Retention-Scheduler (SQLite-Lease/Retry)
1. **Lease-Health prüfen:**
   - SQL: `SELECT lease_name,last_run_at,lock_owner,lock_until FROM scheduler_leases;`
   - Stale Lease liegt vor, wenn `lock_until` deutlich in der Vergangenheit und `last_run_at` nicht fortschreitet.
2. **Recovery-Backlog prüfen:**
   - SQL: `SELECT tenant_id,status,COUNT(*) FROM retention_retry_queue GROUP BY tenant_id,status;`
   - Due-Backlog: `SELECT * FROM retention_retry_queue WHERE status IN ('pending','retry_scheduled') AND datetime(next_attempt_at) <= datetime('now');`
3. **Korrekturmaßnahme bei Crash/Teilfehler:**
   - Scheduler-Prozess neu starten (Lease und Queue bleiben persistent).
   - Keine manuellen Duplikat-Inserts mit gleicher `(failure_id, failure_class)` durchführen.
4. **Sicherheitsmaßnahme:**
   - Tenant-übergreifende Recovery-Bulk-Updates sind untersagt; nur tenant-scoped Incident-Queries.


## 2026-03-08 – Betriebsupdate zu `invalid`-Status und Lease-Heartbeat
- `retention_retry_queue.status = 'invalid'` ist als Security-/Data-Quality-Fund zu behandeln (nicht auto-retryen).
- Abfrage: `SELECT failure_id, failure_class, tenant_id, invalid_reason FROM retention_retry_queue WHERE status='invalid';`
- Heartbeat-Überwachung: Wenn `lock_owner` gesetzt ist, aber `lock_until` nicht fortgeschrieben wird, Scheduler-Instanz auf Blockade/Absturz prüfen.


## 2026-03-08 – Runtime-Startprofil für Retention-Scheduler
- Pflicht-Umgebungsvariablen:
  - `RETENTION_DB_PATH`
  - `RETENTION_SCHEDULER_LOCK_OWNER`
  - `RETENTION_SCHEDULER_INTERVAL_SECONDS`
  - `RETENTION_SCHEDULER_BATCH_SIZE`
  - `RETENTION_SCHEDULER_LEASE_TTL_SECONDS`
  - `RETENTION_SCHEDULER_HEARTBEAT_SECONDS`
- Fail-fast-Check: Start muss fehlschlagen, wenn `heartbeat >= lease_ttl` oder Pflichtparameter fehlen.
- Betreiberhinweis: `lock_owner` muss pro Instanz stabil/eindeutig sein (z. B. Pod/Host + PID).

## 2026-03-08 – Runbook: Dedizierter Retention-Scheduler-Runner
### Startkommando (dedizierter Prozess)
```bash
python -m evodox.runtime.retention_scheduler_runner
```

### Pflicht-ENVs
- `RETENTION_DB_PATH` (Pfad zur produktiven SQLite-Datei, kein `:memory:`)
- `RETENTION_SCHEDULER_LOCK_OWNER` (stabiler eindeutiger Owner pro Instanz)
- `RETENTION_SCHEDULER_INTERVAL_SECONDS` (>0)
- `RETENTION_SCHEDULER_BATCH_SIZE` (>0)
- `RETENTION_SCHEDULER_LEASE_TTL_SECONDS` (>0)
- `RETENTION_SCHEDULER_HEARTBEAT_SECONDS` (>0 und `< RETENTION_SCHEDULER_LEASE_TTL_SECONDS`)

### Shutdown-/Recovery-Verhalten
1. Bei `SIGTERM`/`SIGINT` setzt der Runner einen kontrollierten Stop-Request und beendet den aktuellen Tick zuerst.
2. Es werden keine neuen Ticks gestartet, sobald Shutdown angefordert wurde.
3. Lease-Zustand bleibt konsistent, da laufende Ticks regulär über `mark_ran(...)` abschließen; Crash-Fälle werden über TTL-Recovery abgefangen.
4. Bei Startfehlern durch Konfiguration bricht der Prozess fail-fast mit Exit-Code `2` ab und schreibt strukturierte Fehl-Logs ohne Secret-Ausgabe.

### Betriebsrisiko / Architekturkonflikt
- Ein eingebetteter Scheduler im API-Prozess koppelt API-Liveness und Retention-Liveness ungewollt.
- Der dedizierte Runner entkoppelt Verantwortlichkeiten und erlaubt horizontale Skalierung mit eindeutigen Lease-Ownern.

## 2026-03-08 – Bootstrap-Runbook: Produktiver Retention-Runner-Entrypoint
### Zusätzliche Pflicht-ENVs für produktives Wiring
- `RETENTION_TENANT_IDS` (CSV erlaubter Tenant-IDs für Retention-Job)
- `RETENTION_AUDIT_LOG_PATH` (Pfad zur JSONL-Auditdatei)
- `RETENTION_OBJECT_STORAGE_ROOT` (Root-Verzeichnis für lokale Objektlöschung)
- Optional:
  - `RETENTION_POLICY_MIN_MONTHS` (Default `1`)
  - `RETENTION_POLICY_MAX_MONTHS` (Default `120`)
  - `RETENTION_POLICY_FALLBACK_MONTHS` (Default `12`)
  - `RETENTION_SCHEDULER_MAX_TICKS` (nur für kontrollierte Smoke-Starts/Testbetrieb)

### Validierungs-/Fail-Fast-Regeln
1. Start bricht mit Exit-Code `2` ab, wenn Tenant-Liste, Audit-Log-Pfad oder Storage-Root fehlen.
2. Start bricht mit Exit-Code `2` ab, wenn Policy-Grenzen inkonsistent sind (`max < min` oder `fallback` außerhalb der Grenzen).
3. Start bricht mit Exit-Code `2` ab, wenn Runtime-Settings ungültig sind (z. B. fehlender Lock-Owner, ungültige TTL/Heartbeat-Kombination).

### Security-Hinweis (Dateisystem-Löschung)
- Objektlöschung ist auf `RETENTION_OBJECT_STORAGE_ROOT` begrenzt; Prefix-Path-Traversal außerhalb des Roots wird verworfen.

## 2026-03-08 – Runbook: Storage-Backend-Strategie und Preflight
### Backend-Auswahl
- `RETENTION_OBJECT_STORAGE_BACKEND=filesystem`
  - Pflicht: `RETENTION_OBJECT_STORAGE_ROOT`
- `RETENTION_OBJECT_STORAGE_BACKEND=s3`
  - Pflicht: `RETENTION_OBJECT_STORAGE_S3_BUCKET`, `RETENTION_OBJECT_STORAGE_S3_ENDPOINT`, `RETENTION_OBJECT_STORAGE_S3_REGION`, `RETENTION_OBJECT_STORAGE_S3_ACCESS_KEY`, `RETENTION_OBJECT_STORAGE_S3_SECRET_KEY`
  - Optional: `RETENTION_OBJECT_STORAGE_S3_FORCE_PATH_STYLE=true` (für MinIO empfohlen)

### Deployment-Preflight (vor Container-Start)
```bash
RETENTION_VALIDATE_ENV_ONLY=true python -m evodox.runtime.retention_scheduler_runner
```
- Exit `0`: Konfiguration gültig.
- Exit `2`: Pflichtparameter/Regeln verletzt; Deployment abbrechen.

### Recovery-Governance
- Aktuelle Mapping-Version: `RETENTION_RECOVERY_MAPPING_VERSION=v1`.
- Unterstützte Failure-Klassen in `v1`:
  - `storage_delete_failed`
  - `db_mark_failed`
- Unbekannte Klassen werden absichtlich **nicht** als recovered markiert (fail-safe) und verbleiben im Retry-Backlog bis Governance-Update.

## 2026-03-08 – Zielbetrieb mit Docker Compose (API/Worker/Retention)
### 1) Provisioning
1. Infrastruktur vorbereiten: persistente Volumes für `db`, `broker`, `object-storage` anlegen und auf Host-Ebene verschlüsseln.
2. Zielartefakte bereitstellen:
   - `deploy/docker-compose.target.yml`
   - `.env.production.example` als Basis für produktive `.env`.
3. Service-Image pinnen (`EVODOX_IMAGE` mit release-tag statt `latest`).
4. Auth-Baseline sichern: Keycloak-Realm/Clients vor Start vorbereiten (`API_AUTH_ISSUER`, `API_AUTH_AUDIENCE`).

### 2) Secret-Handling
1. Secrets **nicht** in `.env` committen; nur über Secret-Manager/CI-Injected Environment setzen.
2. Pflicht-Secrets:
   - `POSTGRES_PASSWORD`, `RABBITMQ_DEFAULT_PASS`, `MINIO_ROOT_PASSWORD`, `KEYCLOAK_ADMIN_PASSWORD`
   - `RETENTION_OBJECT_STORAGE_S3_ACCESS_KEY`, `RETENTION_OBJECT_STORAGE_S3_SECRET_KEY`
3. Rotation:
   - Quartalsweise Rotation für Datenbank/Broker/Object-Storage.
   - Sofortrotation bei Incident oder verdächtigen Audit-Ereignissen.
4. Least-Privilege:
   - API/Worker mit separaten DB-/Broker-Credentials betreiben.
   - Retention-Runner nur Delete-Rechte im konfigurierten Bucket-Prefix.

### 3) Startreihenfolge
1. Preflight ausführen (blockierend):
   ```bash
   docker compose -f deploy/docker-compose.target.yml run --rm retention-preflight
   ```
2. Plattformdienste starten:
   ```bash
   docker compose -f deploy/docker-compose.target.yml up -d db broker object-storage auth
   ```
3. Anwendung starten:
   ```bash
   docker compose -f deploy/docker-compose.target.yml up -d api worker retention-runner
   ```
4. Sicherstellen, dass `retention-preflight` erfolgreich war; bei Exit-Code `2` Deployment abbrechen.

### 4) Healthchecks
1. Compose-Status prüfen:
   ```bash
   docker compose -f deploy/docker-compose.target.yml ps
   ```
2. Pflicht-Healthchecks:
   - `db`: `pg_isready`
   - `broker`: `rabbitmq-diagnostics check_running`
   - `object-storage`: MinIO readiness
   - `auth`: `http://localhost:8080/health/ready`
   - `api`: `http://localhost:8000/docs`
3. Runner-Validierung:
   ```bash
   docker compose -f deploy/docker-compose.target.yml logs --tail=200 retention-runner
   ```
   Erwartet wird `retention_scheduler.runner.started` ohne ConfigError.

### 5) Rollback
1. Bei fehlschlagendem Deploy sofort Traffic auf vorherigen API-Release umschalten.
2. Neue Services stoppen:
   ```bash
   docker compose -f deploy/docker-compose.target.yml down
   ```
3. Letztes stabiles Image re-pinnen (`EVODOX_IMAGE=<last-known-good>`), dann kontrolliert neu starten.
4. Nach Rollback:
   - Queue-Backlog prüfen,
   - Retention-Retry-Queue auf inkonsistente Zustände prüfen,
   - Security-Audit-Events auf auffällige AuthZ-/Tenant-Issues prüfen.

### Architekturhinweis / Konfliktanalyse
- **Konflikt:** Compose-`depends_on` garantiert nur Startreihenfolge, nicht fachliche Readiness der Anwendung.
- **Absicherung:** Harte Vorbedingung über `retention-preflight` mit `RETENTION_VALIDATE_ENV_ONLY=true` und zusätzliche Runtime-Healthchecks.
- **Alternative (für höhere Reifegrade):** Migration auf Kubernetes mit `initContainers`, `readinessProbes` und getrennten ServiceAccounts für strengere Isolation.
