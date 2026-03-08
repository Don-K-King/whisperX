# ADR-0011: Runtime-Orchestrierung für Retention-Scheduler mit fail-fast Konfiguration

## Status
Angenommen – 2026-03-08

## Kontext
Die Retention-Scheduler-Logik war bereits als Bibliothek mit persistenten SQLite-Adaptern vorhanden, aber es fehlte ein verbindlicher Runtime-Orchestrierungsbaustein für den produktiven Startpfad inklusive einheitlicher, sicherer Konfiguration.

## Entscheidung
- Einführung von `RetentionSchedulerRuntimeSettings.from_env(...)` mit verpflichtenden, validierten Runtime-Variablen:
  - `RETENTION_DB_PATH`
  - `RETENTION_SCHEDULER_LOCK_OWNER`
  - `RETENTION_SCHEDULER_INTERVAL_SECONDS`
  - `RETENTION_SCHEDULER_BATCH_SIZE`
  - `RETENTION_SCHEDULER_LEASE_TTL_SECONDS`
  - `RETENTION_SCHEDULER_HEARTBEAT_SECONDS`
- Einführung von `RetentionSchedulerRuntime`, das den produktiven Scheduler deterministisch mit `SQLiteSchedulerLeaseStore` und `SQLiteRetentionRetryStore` verdrahtet.
- Fail-fast-Regel: Heartbeat muss kleiner als Lease-TTL sein; ungültige Runtime-Konfiguration bricht den Start explizit ab.

## Sicherheitsauswirkungen
- Reduziert Fehlkonfigurationen mit potenzieller Parallel-Ausführung (TTL/Heartbeat-Missverhältnis).
- Erzwingt eindeutige Instanzidentität (`lock_owner`) statt stiller Default-Owner.
- Verhindert implizite In-Memory-Fallbacks im produktiven Runtime-Pfad.

## Architekturkonflikte und Alternativen
- **Konflikt:** flexible Auto-Konfiguration vs. reproduzierbare, sichere Betriebsparameter.
- **Entscheidung:** fail-fast Konfigurationsvalidierung priorisiert Sicherheit und Betriebsklarheit.
- **Alternative:** permissive Defaults mit stiller Korrektur verworfen, da Fehlerbilder im Betrieb schwerer detektierbar wären.

## Konsequenzen
- Betriebsumgebung muss Runtime-Variablen vollständig bereitstellen.
- Runbooks/Monitoring müssen Konfigurations- und Heartbeat-Fehler als P1/P2 klassifizieren.
