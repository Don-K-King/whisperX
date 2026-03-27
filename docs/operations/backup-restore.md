# Backup & Restore

## Scope
- Datenbank-Backups enthalten alle Anwendungstabellen, inklusive Korrekturmodus-Sessiondaten.
- Das verpflichtende Restore-Gate deckt die langlebigen Tenant-Businessdaten ab:
  - `jobs`
  - `transcripts`
  - `transcript_versions`
  - `export_artifacts`
  - `audit_events`
- Korrekturmodus-Arbeitszustand (`transcript_correction_sessions`, Draft-History, Undo/Redo-Stack) ist aktuell kein verpflichtender Restore-Bestandteil. Er kann aus dem zugrunde liegenden Transcript neu aufgebaut werden.

## Backup
- PostgreSQL taegliche Backups (inklusive PITR, falls verfuegbar)
- MinIO versionierte Snapshots/Backups
- Keycloak Realm-Konfigurations-Export

## Restore
- Reihenfolge: Datenbank -> Storage-Metadaten-Abgleich -> API/Worker-Neustart
- Tenant-Konsistenzpruefung nach Restore ist verpflichtend

## Restore-Nachweis
- Restore-Lauf muss Commit SHA, Konfigurationsversion und verwendete Container-Digests referenzieren.
- Tenant-Konsistenzchecks inklusive Stichprobe eines Cross-Tenant-Negativtests dokumentieren.

## Restore-Workflow (WP-6.2, binding)
1. Tenant-Scope pruefen (`tenant_id` aus Anfrage muss zum Auth-Kontext passen).
2. Verbindliche Business-Tabellen in dieser Reihenfolge wiederherstellen:
   - `jobs`
   - `transcripts`
   - `transcript_versions`
   - `export_artifacts`
   - `audit_events`
3. Storage-Objekte nur unter Prefix `tenant/<tenant_id>/...` wiederherstellen.
4. Konsistenzcheck (`Job <-> Transcript <-> Export <-> Audit`) ausfuehren.
5. Findings bewerten: `completed_with_findings` blockiert Release, bis die Risikoentscheidung dokumentiert ist.
6. Restore-Gate nicht am Korrekturmodus-Sessionzustand blockieren; dieser liegt ausserhalb des verpflichtenden Restore-Vertrags.

## Betriebsdrills und Release-Kriterien
- Drill-Frequenz: mindestens monatlich pro Umgebung.
- Pflichtnachweise pro Drill:
  - Backup-Basis + Commit SHA,
  - Restore-Dauer und Fehlerquote,
  - Anzahl Konsistenz-Findings,
  - dokumentierter Cross-Tenant-Negativtest.
- Release nur wenn:
  - 0 kritische Konsistenz-Findings,
  - Tenant-Guards erfolgreich,
  - vollstaendige Audit-Events fuer Start und Ende vorhanden.
