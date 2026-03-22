# Incident Response

## Sicherheitsvorfall-Klassen
- P1: Cross-Tenant Exposure / Datenabfluss
- P2: AuthZ-Bypass ohne bestätigten Datenabfluss
- P3: Verfügbarkeitseinbruch (Queue/Worker)

## Standardablauf
1. Erkennen und Einordnen
2. Eindämmen
3. Forensik und Root-Cause Analyse
4. Beheben + Regressionstests
5. Dokumentation und Maßnahmenplan


## Restore-/Retention-spezifische Eskalation (WP-6.2)
- P1 sofort, wenn Hinweise auf Cross-Tenant-Restore oder tenant-fremde Object-Keys auftreten.
- P1/P2, wenn Konsistenzprüfung nach Restore kritische Referenzbrüche meldet (`missing_job_reference`).
- Sofortmaßnahmen:
  1. Scheduler und betroffenen Restore-Flow stoppen,
  2. Audit-Events und Backup-Metadaten sichern,
  3. betroffene Tenant-Segmente isolieren,
  4. nur freigegebene Recovery-Runs tenant-scoped erneut starten.
