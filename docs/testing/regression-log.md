# Regression Log

## Hinweise
- Für reine Dokumentationsänderungen sind keine Regressionstests erforderlich.
- Bei Änderungen an Pipeline, Build, Architektur oder Mandantenmodell ist die vollständige Regression verpflichtend.

## Letzte Änderungen
- 2026-03-06: Teststrategie um Edge-/Abuse-Tests pro Entwicklungsschritt erweitert (Dokumentationsänderung, keine Codepfade geändert, daher keine Regression ausgeführt).
- 2026-03-06: Spezifikationsfreeze v1 (fachlich/API/Event/Datenmodell/Security/Test) dokumentiert; keine Implementierungsänderung, daher keine Runtime-Regression ausgeführt.


## Vorlage Regressionseintrag (verbindlich für pflichtige Regressionen)
- Datum/Zeit:
- Release-Kandidat / Commit SHA:
- Betroffener Änderungstyp (Pipeline/Build/Architektur/Struktur):
- Testumgebung (Versionen + Container-Digests):
- Ausgeführte Gate-Stufen:
- Ergebnis je Gate:
- Offene Risiken / Abweichungen:
- Freigabe durch (Rolle/Name):


## 2026-03-07 – Regression nach Strukturänderung (Adapter-Layer)
- Anlass: Einführung neuer Interface-/Infrastrukturmodule (`evodox.web`, `evodox.jobs.infrastructure`).
- Ausgeführt: `python -m unittest discover -s tests -p 'test_*.py'`.
- Ergebnis: Grün, 20 Tests, 1 Skip (FastAPI-Integrationstest wegen fehlender Dependency im Offline-Umfeld).
- Bewertung: Kein regressiver Bruch in bestehender Auth-/Job-Service-Logik festgestellt.


## 2026-03-07 – Regression nach WP-3.3 Strukturänderung
- Anlass: neue Module `evodox.jobs.complete_upload_service`, Outbox/Dispatcher in Infrastruktur, HTTP-Endpoint-Erweiterung.
- Ausgeführt: `python -m unittest discover -s tests -p 'test_*.py'`.
- Ergebnis: Grün, 29 Tests, 1 Skip (FastAPI-Integrationsabhängigkeit).
- Bewertung: Kein regressiver Bruch in WP-3.1/3.2; WP-3.3 Pfad durch Unit/Integration/Abuse abgesichert.


## 2026-03-07 – Regression nach WP-3.4 Read-Pfad-Erweiterung
- Anlass: neuer Status-Read-Service und FastAPI-GET-Endpoint.
- Ausgeführt: `python -m unittest discover -s tests -p 'test_*.py'`.
- Ergebnis: Grün, 34 Tests, 2 Skips (FastAPI-Dependency-abhängige Integrationstests).
- Bewertung: Keine Regression in WP-3.1/3.2/3.3; Read-Pfad tenant-sicher erweitert.


## 2026-03-08 – Regression nach WP-4.1 Queue-Governance-Erweiterung
- Anlass: strukturelle Erweiterung der Queue-Infrastruktur (Retry/DLQ/Fehlerklassifikation/RabbitMQ-Adapter).
- Ausgeführt: `python -m unittest discover -s tests -p 'test_*.py'`.
- Ergebnis: Grün, 38 Tests, 2 Skips (FastAPI-Dependency-abhängige Integrationstests).
- Bewertung: keine Regression in bestehenden WP-3.x-Flows; Queue-Failure-Pfade sind deterministisch abgedeckt.


## 2026-03-08 – Regression nach WP-4 Vollständigung (WP-4.2/WP-4.3)
- Anlass: strukturelle Erweiterung um Worker-Pipeline-Service und Fairness/Backpressure-Scheduling.
- Ausgeführt: `python -m unittest discover -s tests -p 'test_*.py'`.
- Ergebnis: Grün, 44 Tests, 2 Skips (FastAPI-Dependency-abhängige Integrationstests).
- Bewertung: keine Regression in WP-3.x/WP-4.1; Worker-Fehlerpfade und Fairnessregeln testseitig abgesichert.


## 2026-03-08 – Regression nach Schritt-5 Strukturänderung (Transcript/Export Services)
- Anlass: neue Services und HTTP-Adapter-Pfade für Transcript-Versionierung und Export-Pipeline.
- Ausgeführt: `python -m unittest discover -s tests -p 'test_*.py'`.
- Ergebnis: Grün, 52 Tests, 2 Skips (FastAPI-Dependency-abhängige Integrationstests).
- Bewertung: keine Regression in WP-3/WP-4; Schritt-5 Kernpfade inkl. Konflikt- und Abuse-Fällen abgedeckt.
