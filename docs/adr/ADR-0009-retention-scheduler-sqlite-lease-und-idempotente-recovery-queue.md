# ADR-0009: Persistente SQLite-Leases und idempotente Recovery-Queue für Retention-Scheduler

## Status
Angenommen – 2026-03-08

## Kontext
`RetentionScheduler` nutzte bisher In-Memory-Lease- und Retry-Stores. Damit gehen bei Prozessneustarts Run-/Recovery-Zustände verloren; konkurrierende Instanzen können Läufe doppelt starten. Zusätzlich war die Idempotenz bei Recovery-Einträgen nicht über eine persistente Constraint erzwungen.

## Entscheidung
- Persistenter Lease-Adapter `SQLiteSchedulerLeaseStore` mit Schema:
  - `last_run_at`, `lock_owner`, `lock_until`.
- Persistente Recovery-Queue `SQLiteRetentionRetryStore` mit Schema:
  - `failure_id`, `tenant_id`, `job_id`, `failure_class`, `attempts`, `next_attempt_at`, `status`, `first_failed_at`.
- Idempotenz wird auf DB-Ebene erzwungen über `PRIMARY KEY (failure_id, failure_class)`.
- Due-Abfragen werden über Indizes skaliert:
  - `tenant_id`,
  - `(status, next_attempt_at)`,
  - `next_attempt_at`.
- Produktive Bindung erfolgt über `build_sqlite_retention_scheduler(...)`; In-Memory-Stores bleiben nur für Unit-Tests.

## Sicherheitsauswirkungen
- Lease-Kollisionen werden per atomarem `UPDATE ... WHERE lock_until <= now OR lock_owner = ?` verhindert.
- Retry-Recovery bleibt tenant-scoped (Tenant-ID wird persistiert und für Auswertungen/Audits erhalten).
- Manipulierte oder unvollständige Retry-Datensätze werden nicht ausgeführt, sondern finalisiert (`recovered`) um Replay-/Poison-Risiken zu reduzieren.

## Architekturkonflikte und Alternativen
- **Konflikt:** Einfache In-Memory-Implementierung vs. betriebssichere Horizontal-Skalierung.
- **Entscheidung:** SQLite-persistente Adapter als minimal-invasive, architekturkonforme Persistenz.
- **Alternative (zukünftig):** Dedizierter Scheduler-Koordinator (z. B. Postgres advisory lock oder Queue-basiertes Leader-Election) für verteilte Multi-Node-Deployments.

## Konsequenzen
- Scheduler-Läufe und Recovery-Fortschritt überleben Prozessneustarts.
- Duplicate-Recovery pro `failure_id + failure_class` wird technisch unterbunden.
- Betrieb benötigt Monitoring auf Lease-Stale-Zustände und wachsende Retry-Backlogs.
