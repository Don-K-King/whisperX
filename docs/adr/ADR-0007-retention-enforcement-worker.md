# ADR-0007: Retention Enforcement Worker mit tenant-scope Löschpfad und Audit-Entscheidungen

## Status
Angenommen – 2026-03-08

## Kontext
Retention war bisher überwiegend als Anzeige-/Berechnungslogik vorhanden. Für Compliance muss die Löschfrist technisch durchgesetzt werden, inklusive tenant-isolierter Löschausführung und auditierbarer Entscheidungs-/Ausführungsnachweise. Zusätzlich müssen Teilfehler (Storage erfolgreich, DB fehlschlägt und umgekehrt) explizit erkennbar bleiben.

## Entscheidung
- Einführung eines dedizierten `RetentionPolicyResolver` mit globalen Grenzen, Tenant-Defaults und Clamping für manipulierte Werte.
- Einführung eines periodisch aufrufbaren `RetentionEnforcementJob` als Applikationsservice.
- Harte Tenant-Isolation:
  - Candidate-Lookup ausschließlich tenant-scoped,
  - Lösch-/Anonymisierungs-Updates ausschließlich über `(tenant_id, job_id)`.
- Audit-Pflicht je Kandidat:
  - `retention.decision` für Entscheidung (delete/skip_clock_skew),
  - `retention.execution` bei Erfolg,
  - `retention.execution.failed` bei Teilfehlern.
- Clock-Skew-Toleranz wird als Schutz gegen verfrühte Löschung eingeführt.

## Begründung
- Trennung zwischen Policy-Entscheidung und Löschausführung reduziert Kopplung und erleichtert spätere Scheduler-/Worker-Integration.
- Clamping und Typvalidierung adressieren Abuse-Szenarien mit manipulierten Retention-Werten.
- Tenant-scoped Queries verhindern Cross-Tenant-Löschung als kritischstes Sicherheitsrisiko.
- Explizite Teilfehler-Audits verbessern Incident Response und Wiederanlauf-Strategien.

## Konsequenzen
- Zusätzliche Betriebsmetriken (Deletion-Rate, Fehlerquote, Backlog) werden verpflichtend.
- Restore-Workflow (WP-6.2) muss `deleted`/anonymisierte Zustände berücksichtigen.
- Für produktiven Betrieb wird ein robuster Scheduler-Trigger (z. B. Celery Beat/K8s CronJob) benötigt; der Service ist bewusst trigger-agnostisch umgesetzt.
