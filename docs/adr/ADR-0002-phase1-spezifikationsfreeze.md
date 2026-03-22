# ADR-0002: Phase-1 Spezifikationsfreeze (fachlich, API/Event, Datenmodell, Security, Tests)

## Status
Accepted

## Kontext
Nach Architektur-Baseline (ADR-0001) bestand das Risiko inkonsistenter Implementierung über API, Datenmodell und Worker-Contracts hinweg. Für den Implementierungsstart war ein verbindlicher Spezifikationsfreeze notwendig.

## Entscheidung
Für Phase 1 sind die folgenden Spezifikationen verbindlich und bilden die Referenz für die Umsetzung:
1. Fachliche Spezifikation: `docs/product/phase1-fachliche-spezifikation-v1.md`
2. API-Spezifikation: `docs/architecture/api-spec-v1.md`
3. Event-Contracts: `docs/architecture/event-contracts-v1.md`
4. Datenmodell: `docs/architecture/data-model-v1.md`
5. Security-Spezifikation: `docs/security/security-spec-v1.md`
6. Test-Spezifikation: `docs/testing/test-spec-v1.md`

Zusätzlich gelten Freeze-Gates:
- Keine offenen Muss-Anforderungen.
- Jede API-Operation hat AuthZ/Tenant- und Validierungsregeln.
- Jede Entität hat Retention/Audit-Regeln.
- Kritische Security-Risiken sind mitigiert und testbar.

## Konsequenzen
- Positiv: Reduziertes Refactoring-Risiko, klare Übergabe an Umsetzungsteam.
- Positiv: Einheitliche tenant-sichere Umsetzung über alle Komponenten.
- Negativ: Höherer initialer Dokumentationsaufwand.
- Erfordert disziplinierte TDD-Umsetzung entlang der Spezifikationen.
