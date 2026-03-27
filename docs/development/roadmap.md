# Roadmap

## Zweck
Diese Roadmap gibt den aktuellen Umsetzungsstand auf hoher Ebene wieder.
Normative Detailentscheidungen stehen in `docs/development/decisions-log.md` und den ADRs.

## Umsetzungsstand (Stand: 2026-03-27)

### Schritt 1 bis 3
- Architektur- und Governance-Basis ist abgeschlossen.
- Auth, Upload, Complete-Upload und Status-Read sind umgesetzt und testseitig abgesichert.

### Schritt 4
- Queue-Routing, Retry/DLQ und Worker-Pipeline sind umgesetzt.
- Tenant-Fairness und Backpressure-Baseline sind verankert.

### Schritt 5
- Transcript-Versionierung, Speaker-Alias und Export-Pipeline sind umgesetzt.
- Korrekturmodus ist funktional verfuegbar und wurde auf Performance (Virtualisierung, Delta-Operationen) optimiert.

### Schritt 6
- Retention-Enforcement und Scheduler-Runtime sind umgesetzt.
- Restore-/Betriebsgovernance ist dokumentiert und in Runbooks/Testdoku verankert.

## Offene Fokuspunkte
- Weitere Konsolidierung historischer Doku-Artefakte in den Archivbereich.
- Vollstaendige UI-Screenshot-Nachweise fuer Dashboard/Jobdetail ergaenzen.
- Fortlaufende Lesbarkeits- und Konsistenzpflege entlang der SoT-Regeln.

## SoT-Verweise
- Entscheidungen: `docs/development/decisions-log.md`
- Architekturentscheidungen: `docs/adr/`
- Testevidenz: `docs/testing/regression-log.md`
- Betrieb: `docs/operations/runbooks.md`
