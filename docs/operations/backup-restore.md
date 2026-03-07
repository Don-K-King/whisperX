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
