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
