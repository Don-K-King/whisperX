# Monitoring & Alerting

## Kernmetriken
- Queue-Lag je Queue-Klasse
- Job-Dauer (p50/p95/p99)
- Worker-Auslastung (CPU/GPU/Memory)
- Fehlerraten API/Worker
- Retention-Job Erfolg/Fehler

## Alerts
- Queue-Lag über Schwellwert
- DLQ-Einträge > 0
- wiederholte AuthZ-Fehler (potenziell Angriff)
- ausstehende Retention-Löschungen


## Reproduzierbarkeits-Metriken
- Build-Provenance vollständig vorhanden (ja/nein)
- Drift zwischen Soll- und Ist-Versionen (Toolchain/Images)
- Wiederholbarkeit kritischer Testläufe (Passrate in Referenzumgebung)


## Queue/Dispatcher Monitoring (WP-4.1)
- Pflichtmetriken:
  - `queue_lag_seconds` (Alter von pending Events bis Publish-Versuch),
  - `queue_retry_total` (Retry-Entscheidungen),
  - `queue_dlq_total` (in DLQ verschobene Events),
  - `queue_duplicate_total` (als Duplikat neutralisierte Zustellungen).
- Alarmempfehlungen:
  - Warnung bei dauerhaft steigendem `queue_lag_seconds`-95p,
  - Kritisch bei erhöhtem `queue_dlq_total` in kurzer Zeit,
  - Warnung bei Retry-Spitzen als möglicher Broker-/Netzwerkindikator.


## Worker/Fairness Monitoring (WP-4.2/WP-4.3)
- Pflichtmetriken:
  - `worker_processing_duration_seconds` (p50/p95/p99),
  - `worker_failed_retryable_total`,
  - `worker_failed_terminal_total`,
  - `tenant_inflight_current` (pro Tenant),
  - `tenant_queue_wait_seconds` (Fairness-Indikator).
- Alarmempfehlungen:
  - Kritisch bei stark steigenden terminalen Fehlern (mögliche Medien-/Parser-Inkompatibilität),
  - Warnung bei dauerhaft hohem `tenant_queue_wait_seconds` einzelner Tenants (Starvation-/Quota-Tuning-Bedarf).


## Transcript/Export Monitoring (WP-5.1/WP-5.2)
- Pflichtmetriken:
  - `transcript_update_conflict_total` (Optimistic-Locking-Konflikte),
  - `transcript_update_reject_total` (Validation-Rejects),
  - `export_requested_total` (pro Format),
  - `export_reject_total` (invalid format/version),
  - `export_generation_latency_seconds`.
- Alarmempfehlungen:
  - Warnung bei stark steigendem `transcript_update_conflict_total` (UI/UX- oder Kollaborationsproblem),
  - Kritisch bei erhöhtem `export_reject_total` durch potenzielle Abuse-/Probe-Muster.


## Retention Monitoring (WP-6.1)
- Pflichtmetriken:
  - `retention_deleted_total` (gelöschte/anonymisierte Datensätze),
  - `retention_failed_total` (Teil-/Fehlversuche),
  - `retention_backlog_total` (fällige, noch nicht verarbeitete Kandidaten),
  - `retention_duration_seconds` (Joblaufzeit),
  - `retention_clock_skew_skipped_total` (bewusst verzögerte Löschungen).
- Alarmempfehlungen:
  - Kritisch bei `retention_failed_total > 0` über mehrere Läufe,
  - Warnung bei kontinuierlich steigendem `retention_backlog_total`,
  - Kritisch bei anomalen Tenant-Verteilungen (ein Tenant dominiert Löschrate ungewöhnlich).


## Restore/Scheduler Monitoring (WP-6.2)
- Pflichtmetriken:
  - `retention_scheduler_runs_total`,
  - `retention_recovery_recovered_total`,
  - `retention_recovery_retry_scheduled_total`,
  - `restore_runs_total`,
  - `restore_consistency_findings_total`.
- Alarmempfehlungen:
  - Kritisch bei ausbleibenden Scheduler-Runs über > 2 Intervalle,
  - Kritisch bei dauerhaft steigendem `retention_recovery_retry_scheduled_total`,
  - Kritisch bei `restore_consistency_findings_total > 0` in Produktionsrestores.
