# Backup & Restore

## Backup
- PostgreSQL tägliche Backups (inkl. PITR falls möglich)
- MinIO versionierte Snapshots/Backups
- Keycloak Realm-Konfiguration exportieren

## Restore
- Reihenfolge: DB → Storage-Metadatenabgleich → API/Worker Restart
- Tenant-Konsistenzprüfung nach Restore verpflichtend


## Restore-Nachweis
- Restore-Lauf muss Commit-SHA, Konfigurationsversion und verwendete Container-Digests referenzieren.
- Tenant-Konsistenzprüfung inkl. stichprobenartiger Cross-Tenant-Negativprüfung dokumentieren.


## Restore-Workflow (WP-6.2, verbindlich)
1. Tenant-Scope prüfen (`tenant_id` im Request muss Auth-Context entsprechen).
2. Tabellen in Reihenfolge wiederherstellen:
   - `jobs`
   - `transcripts`
   - `transcript_versions`
   - `export_artifacts`
   - `audit_events`
3. Storage-Objekte wiederherstellen, ausschließlich mit Präfix `tenant/<tenant_id>/...`.
4. Konsistenzprüfung ausführen (`Job ↔ Transcript ↔ Export ↔ Audit`).
5. Findings bewerten: `completed_with_findings` blockiert Freigabe bis Risikoentscheidung dokumentiert ist.

## Betriebsdrills + Freigabekriterien
- Drill-Frequenz: mindestens monatlich pro Umgebung.
- Pflichtnachweise je Drill:
  - verwendeter Backup-Stand + Commit-SHA,
  - Restore-Dauer und Fehlerquote,
  - Anzahl Konsistenz-Findings,
  - dokumentierte Cross-Tenant-Negativprüfung.
- Freigabe nur bei:
  - 0 kritischen Konsistenzfindings,
  - erfolgreichen Tenant-Guards,
  - vollständigen Audit-Events für Start/Ende.
