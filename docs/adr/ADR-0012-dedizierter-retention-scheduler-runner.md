# ADR-0012: Dedizierter Retention-Scheduler-Runner statt eingebettetem API-Scheduler

## Status
Angenommen – 2026-03-08

## Kontext
Der Retention-Scheduler war als Laufzeitbaustein vorhanden, aber ohne dedizierten Prozess-Entrypoint mit sauberem Start-/Shutdown-Verhalten. Ein eingebetteter Scheduler im API-Prozess würde Betriebszustände vermischen (API-Liveness vs. Retention-Liveness) und erhöht das Risiko inkonsistenter Steuerung bei Deployments/Restarts.

## Entscheidung
- Einführung eines dedizierten Runtime-Moduls `evodox/runtime/retention_scheduler_runner.py`.
- Entrypoint führt fail-fast Konfigurationschecks aus (`RetentionSchedulerRuntimeSettings.from_env(...)`), bricht bei `RetentionSchedulerRuntimeConfigError` mit Exit-Code `2` ab.
- Start-Logs sind strukturiert und enthalten nur nicht-sensitive Felder (`lock_owner`, `db_path`, Intervall, Batchsize, Lease-TTL, Heartbeat).
- Runner installiert `SIGTERM`/`SIGINT`-Handler für Graceful Shutdown: laufender Tick wird beendet, danach kein neuer Tick gestartet.

## Sicherheitsauswirkungen
- Reduziert Fehlkonfigurationsrisiko durch frühen Prozessabbruch statt stiller Defaults.
- Verhindert Secret-Leakage durch bewusst begrenzte Start-Logs.
- Stärkt Betriebsrobustheit durch kontrollierte Stop-Semantik und konsistentes Lease-Verhalten.

## Architekturkonflikt und Alternativen
- **Konflikt:** „flexibler eingebetteter Scheduler im API-Prozess“ vs. „dedizierter Runner mit klarer Verantwortlichkeit“.
- **Entscheidung:** dedizierter Runner.
- **Begründung:** bessere horizontale Skalierung, geringere Kopplung, klareres Monitoring/Alerting.
- **Verworfene Alternative:** API-embedded Scheduler mit Feature-Flag. Nachteil: konkurrierende Verantwortlichkeiten, erhöhte Deploy-Komplexität, schwerere Incident-Isolation.

## Konsequenzen
- Betrieb benötigt einen zusätzlichen Prozess/Container für den Scheduler.
- Deployment muss Pflicht-ENVs bereitstellen und Startfehler explizit überwachen.
- Monitoring ergänzt um Runner-Liveness-, ConfigError- und TickFailure-Alerts.
