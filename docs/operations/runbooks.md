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
