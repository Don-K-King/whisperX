# ADR-0013: Retention-Runner Storage-Backend-Strategie und Recovery-Governance

## Status
Angenommen – 2026-03-08

## Kontext
Der dedizierte Retention-Runner war bislang primär auf lokales Filesystem-Wiring ausgerichtet. Für produktive Umgebungen mit S3/MinIO fehlte ein dedizierter Adapter mit gleichwertiger `delete_prefix`-Semantik. Zusätzlich war die Recovery-Failure-Class-Logik nur implizit im Code vorhanden und nicht versioniert governbar.

## Entscheidung
- Einführung einer expliziten Storage-Backend-Strategie im Runner-Bootstrap:
  - `filesystem` über `LocalFilesystemRetentionObjectStorage`,
  - `s3` über `S3RetentionObjectStorage` (S3/MinIO-kompatibel).
- Einheitliche Sicherheitssemantik für beide Backends:
  - nur tenant-präfixierte Objektschlüssel,
  - Path-Traversal-/Prefix-Manipulation wird abgewiesen,
  - fehlende Objekte werden idempotent als erfolgreich behandelt.
- Einführung versionierter Recovery-Governance via `RETENTION_RECOVERY_MAPPING_VERSION` (aktuell `v1`).
  - `v1` unterstützt `storage_delete_failed` und `db_mark_failed`.
  - unbekannte Klassen bleiben bewusst fail-safe im Retry-Pfad.
- Deployment-Hardening ergänzt: Preflight-Validierung (`RETENTION_VALIDATE_ENV_ONLY=true`) für Startmanifeste/Init-Checks.

## Sicherheitsauswirkungen
- Reduziert Risiko unkontrollierter Löschpfade über konsistente Prefix-Validation.
- Verhindert stilles Überspringen unbekannter Recovery-Fälle durch fail-safe Governance.
- Senkt Fehlkonfigurationsrisiko über explizite Preflight-Validierung vor Produktionsstart.

## Architekturkonflikt und Alternativen
- **Konflikt:** einfache lokale Löschimplementierung vs. produktionsfähige objekt-storage-agnostische Strategie.
- **Entscheidung:** dedizierte Adapterstrategie mit identischer Domänensemantik.
- **Verworfene Alternative:** direkte S3-Bibliotheksaufrufe im Recovery-Executor. Nachteil: stärkere Kopplung, schlechtere Testbarkeit, keine klare Backend-Abstraktion.

## Konsequenzen
- Runner benötigt je Backend unterschiedliche Pflicht-ENVs.
- Deployments müssen Preflight-Validierung in Pipeline/Init-Container aufnehmen.
- Recovery-Failure-Class-Erweiterungen müssen governance-konform versioniert erfolgen.
