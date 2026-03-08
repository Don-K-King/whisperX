# ADR-0008: Retention-Scheduler mit Retry-Recovery und tenant-sicherer Restore-Workflow

## Status
Angenommen – 2026-03-08

## Kontext
WP-6.1 hat den Retention-Enforcement-Service eingeführt, aber produktive Betriebsfähigkeit verlangt zusätzlich eine periodische Ausführung mit kontrollierter Retry-Recovery für Teilfehlerklassen. Parallel fordert WP-6.2 einen tenant-gesicherten Restore-Pfad mit referenzieller Konsistenzprüfung über `Job ↔ Transcript ↔ Export ↔ Audit`.

## Entscheidung
- Ein dedizierter `RetentionScheduler` steuert periodische Läufe, Intervall-Gating und Recovery-Versuche für gespeicherte Teilfehler (`db_mark_failed`, `storage_delete_failed`) idempotent pro Failure-Record.
- Restore wird als expliziter Applikations-Workflow umgesetzt (`execute_restore`) mit:
  - fest definierter Tabellen-Reihenfolge (`jobs -> transcripts -> transcript_versions -> export_artifacts -> audit_events`),
  - tenant-scope Guards für Request und Object-Key-Präfix,
  - nachgelagerter Konsistenzprüfung (`RestoreConsistencyChecker`) gegen fehlende Job-Referenzen.
- Restore-Audit ist verpflichtend (`restore.started`, `restore.completed`) inkl. Findings-Anzahl.

## Begründung
- Scheduler-Logik außerhalb des Retention-Jobs hält die Fachlogik entkoppelt und horizontal skalierbar.
- Recovery pro Failure-Klasse verhindert Fehlstrategie „global blind retry“ und erhöht Wiederanlauf-Sicherheit.
- Restore-Reihenfolge minimiert inkonsistente Zwischenzustände.
- Tenant-scope Guards reduzieren das kritischste Risiko eines Cross-Tenant-Restores.

## Konsequenzen
- Für Produktion muss die Retry-Queue persistent statt in-memory betrieben werden (z. B. DB-Tabelle + Worker-Lease).
- Restore-Freigaben benötigen dokumentierte Betriebsdrills und definierte Abbruchkriterien bei Findings.
- Incident-Runbook muss Restore-Anomalien und Cross-Tenant-Verdacht als P1 behandeln.
