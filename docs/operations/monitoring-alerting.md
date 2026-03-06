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
