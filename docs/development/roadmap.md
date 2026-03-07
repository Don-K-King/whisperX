# Roadmap

## Schritt 1 (abgeschlossen)
- Architektur vollständig festgelegt
- Governance und Dokumentationspflichten definiert
- Edge-/Abuse-Teststrategie pro Entwicklungsschritt als Pflicht ergänzt

## Schritt 2
- Monorepo-Struktur und ADRs operationalisieren
- Docker-Compose On-Prem Baseline bereitstellen
- Infra-Edge-Tests: Hardening, Rate-Limit, Fehlkonfigurationsprüfungen

## Schritt 2.5 (Gate)
- Implementation Playbook v1 finalisieren und freigeben
- DoR/DoD und Testqualitygates als CI-Blocker operationalisieren
- Reproduzierbare Build-/Testumgebung inkl. Nachweisschema fixieren

## Schritt 3
- Auth + Upload Skeleton TDD-implementieren
- Tenant-Isolation-Tests und Retention-Basis einführen
- Upload-Fuzzing und Input-Validation-Tests etablieren

## Schritt 4
- WhisperX-Worker Pipeline und Queue-Skalierung integrieren
- E2E Upload→Transkript→Edit→Export
- Queue-Resilience-Tests (Retry/DLQ/Poison Message/Restart Recovery)

## Schritt 5
- Edit-Export-Härtung (XSS/Injection/Unicode Edge Cases)
- Export-Autorisierung im Tenant-Kontext absichern

## Schritt 6
- Retention-/Compliance-Automation finalisieren
- Auditierbare Lösch- und Restore-Konsistenztests etablieren
