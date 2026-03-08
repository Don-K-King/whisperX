# ADR-0010: Quarantäne für ungültige Retry-Datensätze und Lease-Heartbeat im Retention-Scheduler

## Status
Angenommen – 2026-03-08

## Kontext
Nach ADR-0009 blieb ein Sicherheits-/Betriebskonflikt offen:
1. Ungültige/manipulierte Retry-Datensätze wurden als `recovered` finalisiert und damit forensisch nicht klar von echten Recoveries getrennt.
2. Bei langen Scheduler-Läufen konnte das Lease ohne Erneuerung auslaufen und parallele Instanzen begünstigen.

## Entscheidung
- Retry-Queue erhält einen expliziten Quarantänepfad:
  - neuer Status `invalid`,
  - optionales Feld `invalid_reason`.
- `RetentionScheduler` markiert ungültige Datensätze mit `mark_invalid(...)` statt `mark_recovered(...)`.
- Lease-Store erhält `renew_lock(now)`; Scheduler kann über konfigurierbares `lease_heartbeat_interval` das Lock während langer Läufe erneuern.

## Sicherheitsauswirkungen
- Manipulierte Datensätze werden nicht als Erfolg kaschiert; Incident-Analyse bleibt nachvollziehbar.
- Lease-Heartbeat reduziert Race-/Split-Brain-Risiko bei langen Recovery-Batches.
- Due-Abfragen bleiben geschützt, da `invalid` nicht mehr in ausführbaren Status enthalten ist.

## Architekturkonflikte und Alternativen
- **Konflikt:** Betriebsruhe (invalid als recovered) vs. Nachvollziehbarkeit/Security.
- **Entscheidung:** explizite Quarantäne priorisiert Security & Auditierbarkeit.
- **Alternative:** harte Löschung ungültiger Datensätze verworfen, da forensischer Kontext verloren geht.

## Konsequenzen
- Betrieb/Monitoring muss `invalid`-Backlog und `invalid_reason` überwachen.
- Runbooks müssen Incident-Playbook für `invalid`-Anstiege enthalten.
