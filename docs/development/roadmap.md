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


## Schritt 4 (Umsetzungsstand 2026-03-08)
- WP-4.1 abgeschlossen: Queue Routing + Retry/DLQ Governance.
- WP-4.2 abgeschlossen: Worker Processing Chain (ASR/Alignment/Diarization) mit tenant-scoped Artefaktpersistenz und Fehlerklassifikation.
- WP-4.3 abgeschlossen: Tenant-Fairness + Backpressure-Baseline mit globalen/per-tenant Inflight-Limits und Round-Robin-Scheduling.


## Schritt 5 (Umsetzungsstand 2026-03-08)
- WP-5.1 abgeschlossen: Transcript-Versionierung mit Optimistic Locking.
- WP-5.2 abgeschlossen: Export-Pipeline (`txt|json|srt|vtt`) mit tenant-scoped Sicherheitsprüfungen.
