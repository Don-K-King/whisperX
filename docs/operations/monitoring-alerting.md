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


## 2026-03-08 – Alerts für Scheduler-Lease und Recovery-Queue
- **Alert: retention_scheduler_lease_stale**
  - Bedingung: `last_run_at` älter als 2x Intervall und Queue hat due Einträge.
  - Schweregrad: High.
- **Alert: retention_recovery_backlog_high**
  - Bedingung: `status in (pending,retry_scheduled)` > Schwellwert pro Tenant.
  - Schweregrad: Medium/High (tenantabhängig).
- **Alert: retention_recovery_attempt_spike**
  - Bedingung: starke Zunahme `attempts` innerhalb kurzer Zeit.
  - Schweregrad: Medium; Hinweis auf persistente Teilfehler oder Misskonfiguration.
- **Security Alert: retry_dataset_invalid**
  - Bedingung: ungültige Datensätze (negative Attempts/leere IDs) erkannt.
  - Schweregrad: High; potenzieller Manipulationsversuch.


## 2026-03-08 – Alert-Ergänzung für invalid Quarantine
- **Alert: retention_recovery_invalid_backlog_high**
  - Bedingung: `status='invalid'` über Schwellwert (gesamt oder tenant-spezifisch).
  - Schweregrad: High (potenzieller Manipulations- oder Datenintegritätsvorfall).
- **Alert: retention_scheduler_heartbeat_stalled**
  - Bedingung: `lock_owner` aktiv, `lock_until` wird innerhalb Heartbeat-Fenster nicht erneuert.
  - Schweregrad: High.


## 2026-03-08 – Runtime-Konfigurationsalerts
- **Alert: retention_scheduler_config_invalid**
  - Bedingung: Scheduler startet wegen Runtime-Konfigurationsfehler nicht.
  - Schweregrad: High.
- **Alert: retention_scheduler_lock_owner_missing**
  - Bedingung: Start ohne expliziten `lock_owner` versucht.
  - Schweregrad: High (Deployment-Fehlkonfiguration).

## 2026-03-08 – Monitoring: Dedizierter Retention-Scheduler-Runner
### Runner-Liveness
- Metrik/Signal: periodisches Log-Event `retention_scheduler.runner.tick_completed`.
- Alert (kritisch): Kein Tick-Event innerhalb von `2 * RETENTION_SCHEDULER_INTERVAL_SECONDS`.
- Alert (warnend): Wiederholte `executed=false`-Ticks bei gleichzeitig steigendem Due-Backlog.

### Config-Startfehler
- Metrik/Signal: Log-Event `retention_scheduler.runner.config_error` + Prozess-Exit-Code `2`.
- Alert (kritisch): Runner-Prozess startet nicht oder restartet in CrashLoop mit ConfigError.
- Gegenmaßnahme: Pflicht-ENV-Validierung im Deployment-Template, vor Start syntaktisch prüfen.

### Tick-Ausfälle
- Metrik/Signal: Log-Event `retention_scheduler.runner.tick_failed`.
- Alert (kritisch): >= 3 Tick-Fehler in Folge.
- Alert (warnend): anhaltend erhöhte Tick-Fehlerrate bei konstantem Backlog.
- Security-Hinweis: Fehlermeldungen dürfen keine Secrets enthalten; nur nicht-sensitive Runtime-Parameter loggen.

## 2026-03-08 – Bootstrap-Observability für produktives Runner-Wiring
- Pflicht-Startsignal:
  - `retention_scheduler.runner.started` mit nicht-sensitiven Feldern inkl. `lock_owner`, `db_path`, Intervalle/TTL/Heartbeat.
- Bootstrap-Fehlersignal:
  - `retention_scheduler.runner.config_error` bei fehlender Tenant-Liste/Audit-Log-/Storage-Root-Config oder ungültigen Policy-Parametern.
- Security-Alert-Empfehlung:
  - Erhöhte Rate fehlgeschlagener Recovery-Ticks (`tick_failed`) zusammen mit persistentem Retry-Backlog als Indikator für Daten-/Storage-Inkonsistenz.

## 2026-03-08 – Alerts für Storage-Backend und Recovery-Governance
- **Alert: retention_runner_preflight_failed**
  - Bedingung: Preflight-Job (`RETENTION_VALIDATE_ENV_ONLY=true`) endet mit Exit-Code `2`.
  - Schweregrad: High (Deployment blockieren).
- **Alert: retention_recovery_failure_class_unknown**
  - Bedingung: Log-Event `retention_scheduler.runner.recovery_failure_class_unknown` tritt auf.
  - Schweregrad: Medium/High (Governance-Lücke in Failure-Class-Mapping).
- **Alert: retention_storage_backend_misconfig**
  - Bedingung: Runner-Startfehler bei `RETENTION_OBJECT_STORAGE_BACKEND` oder backend-spezifischen Pflichtparametern.
  - Schweregrad: High.

## 2026-03-08 – Deploy-Objekt-Zuordnung (Compose Zielbetrieb)
### Service-Mapping
- docker compose service `api`
  - Probe: HTTP-Healthcheck `GET /docs` (container-internal).
  - Alerts:
    - `api_healthcheck_failing` bei `unhealthy` > 3 Intervalle.
    - `api_authz_error_spike` bei anomalen 401/403-Raten.
- docker compose service `worker`
  - Probe: Prozess-Healthcheck (`python -c ...`).
  - Alerts:
    - `worker_job_failures_high` bei dauerhaft steigenden terminalen Fehlern.
    - `worker_queue_starvation` bei hohem `tenant_queue_wait_seconds`.
- docker compose service `retention-runner`
  - Probe: Runner-Liveness via Tick-Logs + Compose-Healthcheck.
  - Alerts:
    - Alert-Rule `retention_runner_preflight_failed` (aus CI/Preflight-Job).
    - Alert-Rule `retention_scheduler_config_invalid` (CrashLoop/Exit-Code `2`).
    - Alert-Rule `retention_scheduler_heartbeat_stalled` (Lease wird nicht erneuert).
- docker compose service `db`
  - Probe: `pg_isready`.
  - Alerts: `postgres_unavailable`, `postgres_replication_lag_high` (falls Replikation aktiv).
- docker compose service `broker`
  - Probe: `rabbitmq-diagnostics check_running`.
  - Alerts: `rabbitmq_queue_lag_high`, `rabbitmq_dlq_entries_detected`.
- docker compose service `object-storage`
  - Probe: MinIO readiness.
  - Alerts: `object_storage_unavailable`, `retention_storage_backend_misconfig`.
- docker compose service `auth`
  - Probe: Keycloak readiness endpoint.
  - Alerts: `auth_realm_unavailable`, `auth_token_issuance_failures_high`.

### Job-Mapping
- Preflight-Job: `retention-preflight` (one-shot Container mit `RETENTION_VALIDATE_ENV_ONLY=true`).
  - Blockiert `api`, `worker` und `retention-runner` via `service_completed_successfully`.
- CI-Stage: `.github/workflows/deployment-preflight.yml` / Job `retention-preflight`.
  - Muss vor produktivem Rollout grün sein.

### Alert-Rules-Quelle
- Referenzregeln liegen in `deploy/prometheus/alerts-targetbetrieb.yml` und müssen in die zentrale Alertmanager-Pipeline importiert werden.

## 2026-03-22 - Monitoring-Erweiterung: GPU-First Runtime und dedizierte Pools
- Neue Pflichtsignale:
  - Log/Audit-Event `worker.runtime.gpu_fallback` (Zaehler pro Worker-Instanz).
  - Effektiver Device-Modus aus `worker.runner.started`-Event (`whisperx_device`, `whisperx_compute_type`, `whisperx_device_index`), bevorzugt aus strukturierter Event-Auswertung statt reinem Message-String.
  - Queue-Lag getrennt nach Klassen `cpu-short`, `gpu-standard`, `gpu-long`.
- Alarmempfehlungen:
  - **Alert: worker_gpu_fallback_spike**
    - Bedingung: > N Fallbacks innerhalb 15 Minuten.
    - Schweregrad: High (GPU-Instabilitaet oder Runtime-Misconfig).
  - **Alert: worker_gpu_queue_lag_high**
    - Bedingung: p95 Queue-Lag fuer `gpu-*` ueber Schwellwert.
    - Schweregrad: High.
  - **Alert: worker_gpu_pool_imbalance**
    - Bedingung: ein GPU-Worker permanent ausgelastet, andere idle.
    - Schweregrad: Medium (Routing/Batch/Queue-Tuning erforderlich).

## 2026-03-22 - Monitoring-Erweiterung: Frontend `unknown_error` / API-Proxy
- Neue Pflichtsignale:
  - Frontend-Proxy-5xx-Rate fuer `/api/*`.
  - NGINX-Upstream-Connect-Fehler (`connect() failed`, `upstream prematurely closed connection`).
  - API-Health `GET /docs` (container-internal) und korrelierte Restart-Rate von `frontend`/`api`.
- Alarmempfehlungen:
  - **Alert: frontend_api_proxy_5xx_high**
    - Bedingung: > 5% `5xx` auf `/api/*` fuer > 5 Minuten.
    - Schweregrad: High (UI zeigt typischerweise `unknown_error`).
  - **Alert: frontend_upstream_connect_failures**
    - Bedingung: wiederholte Upstream-Connect-Fehler im Frontend-Log.
    - Schweregrad: High.
