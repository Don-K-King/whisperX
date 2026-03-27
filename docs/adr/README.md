# ADR-Verzeichnis

Nutze das Format `ADR-XXXX-kurztitel.md`.

Jede signifikante Architekturentscheidung muss hier dokumentiert und in `docs/development/decisions-log.md` referenziert werden.

- [ADR-0001: EvidoX Architektur-Baseline](ADR-0001-evodox-architektur-baseline.md)
- [ADR-0002: Phase-1 Spezifikationsfreeze](ADR-0002-phase1-spezifikationsfreeze.md)
- [ADR-0003: Verbindliches Implementation Playbook, Gate-Operationalisierung und Reproduzierbarkeit](ADR-0003-implementation-playbook-gates-und-reproduzierbarkeit.md)
- [ADR-0004: Complete-Upload, Outbox und Idempotenz](ADR-0004-complete-upload-outbox-idempotenz.md)
- [ADR-0005: Worker-Pipeline, Fairness und Backpressure](ADR-0005-worker-pipeline-fairness-backpressure.md)
- [ADR-0006: Transcript-Versionierung und Export-Pipeline](ADR-0006-transcript-versionierung-und-export-pipeline.md)
- [ADR-0007: Retention-Enforcement-Worker](ADR-0007-retention-enforcement-worker.md)
- [ADR-0008: Retention-Scheduler und Tenant-Restore-Konsistenz](ADR-0008-retention-scheduler-und-tenant-restore-konsistenz.md)
- [ADR-0009: Retention-Scheduler, SQLite-Leases und idempotente Recovery-Queue](ADR-0009-retention-scheduler-sqlite-lease-und-idempotente-recovery-queue.md)
- [ADR-0010: Invalid-Quarantine und Lease-Heartbeat im Retention-Scheduler](ADR-0010-retention-scheduler-invalid-quarantine-und-lease-heartbeat.md)
- [ADR-0011: Runtime-Orchestrierung mit Fail-Fast-Konfiguration](ADR-0011-retention-scheduler-runtime-orchestrierung-fail-fast-konfiguration.md)
- [ADR-0012: Dedizierter Retention-Scheduler-Runner](ADR-0012-dedizierter-retention-scheduler-runner.md)
- [ADR-0013: Storage-Backend und Recovery-Governance fuer den Retention-Runner](ADR-0013-retention-runner-storage-backend-und-recovery-governance.md)
- [ADR-0014: Zielbetrieb via Docker Compose mit Preflight-Gating](ADR-0014-zielbetrieb-compose-preflight-gating.md)
- [ADR-0016: Midpoint-Checkpointing und terminaler Cancel-Endpunkt](ADR-0016-midpoint-checkpointing-und-terminal-cancel.md)
- [ADR-0017: GPU-First Local Runtime und vorbereitete Multi-GPU Worker-Pools (Compose)](ADR-0017-gpu-first-local-und-multi-gpu-compose-worker-pools.md)
- [ADR-0018: Tenant-Admin Decoding Settings und Job-Snapshot](ADR-0018-tenant-admin-decoding-settings-und-job-snapshot.md)
- [ADR-0019: Speaker-Aliase und Blockbildung](ADR-0019-transcript-speaker-alias-und-blockbildung.md)
- [ADR-0020: WhisperX large-v3 Erzwingung, Sprachwahl pro Job und Chunk/VAD Exposition](ADR-0020-whisperx-large-v3-erzwingung-sprache-und-chunk-vad.md)
- [ADR-0021: Korrekturmodus Sessions und Statusfuehrung](ADR-0021-korrekturmodus-sessions-und-status.md)
- [ADR-0022: Korrekturmodus mit absoluter Timeline ohne Seed-Kompaktierung](ADR-0022-korrekturmodus-absolute-timeline-ohne-seed-kompaktierung.md) (praezisiert Timeline-Invarianten gegenueber ADR-0021)
- [ADR-0023: Korrekturmodus-Performance durch Virtualisierung und Delta-Operationen](ADR-0023-korrekturmodus-performance-virtualisierung-und-delta-operationen.md)

Hinweis: Eine ADR-Datei `ADR-0015` existiert im Verzeichnis aktuell nicht. Der historische Log-Titel bleibt nur in `docs/development/decisions-log.md` erhalten und ist kein aktiver ADR-Dateiverweis.
