# ADR-0003: Verbindliches Implementation Playbook, Gate-Operationalisierung und Reproduzierbarkeit

- **Status:** Accepted
- **Datum:** 2026-03-07

## Kontext
Nach dem Spezifikationsfreeze (ADR-0002) bestand weiterhin das Risiko uneinheitlicher Umsetzungsauslegung zwischen Teams (API, Security, QA, Ops).

## Entscheidung
1. Einführung eines verbindlichen `docs/development/implementation-playbook-v1.md` als Gate zwischen Planung und Implementierung.
2. DoR/DoD je Arbeitspaket als verpflichtender Start-/Abschlussnachweis.
3. CI/CD-Gate-Reihenfolge (Lint → Unit → Integration → Contract → Security/Abuse → E2E/Regression) als Blocker.
4. Reproduzierbarkeitsnachweise (Versionen, Digests, Provenance) als Freigabekriterium.
5. Threat→Control→Test-Traceability als Pflicht für sicherheitskritische Arbeitspakete.

## Begründung
- Verbessert Architekturkonsistenz und reduziert spätere Refactorings.
- Reduziert Security-Risiken durch frühere, nachweisbare Kontrollen.
- Erhöht Betriebsstabilität und Auditierbarkeit durch reproduzierbare Artefakte.

## Konsequenzen
- Höherer initialer Dokumentationsaufwand, dafür weniger Integrations- und Sicherheitsfehler in der Realisierungsphase.
- QA/Ops müssen Build- und Testnachweise standardisiert erfassen.

## Risiken und Gegenmaßnahmen
- **Risiko:** Prozessüberlastung in frühen Sprints.
  - **Gegenmaßnahme:** Arbeitspakete klein schneiden, Gate-Automation schrittweise erhöhen.
- **Risiko:** Umgehung der Gates aus Zeitdruck.
  - **Gegenmaßnahme:** Merge-Blocker in CI verpflichtend und keine manuelle Umgehung ohne dokumentierte Ausnahmeentscheidung.
