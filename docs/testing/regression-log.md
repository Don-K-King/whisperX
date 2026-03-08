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


## 2026-03-08 – Regression nach WP-6.1 Strukturänderung (Retention Worker + Adapter)
- Anlass: neue Retention-Service-Schicht und zusätzliche SQLite-Infrastrukturadapter für tenant-scoped Löschpfade.
- Ausgeführt: `python -m unittest discover -s tests -p 'test_*.py'`.
- Ergebnis: Grün, 61 Tests, 2 Skips (FastAPI-Dependency-abhängige Integrationstests).
- Bewertung: keine Regression in WP-3 bis WP-5; Retention-Entscheidungspfad inkl. Teilfehler-Audits ist testseitig abgedeckt.


## 2026-03-08 – Regression nach WP-6.2 Strukturänderung (Restore-Service + Scheduler)
- Anlass: neue Architekturmodule `evodox.jobs.restore_service` und `evodox.jobs.retention_scheduler`.
- Ausgeführt: `python -m unittest discover -s tests -p 'test_*.py'`.
- Ergebnis: Grün, 67 Tests, 2 Skips (FastAPI-Dependency-abhängige Integrationstests).
- Bewertung: keine Regression in WP-3 bis WP-6.1; Restore- und Recovery-Pfade sind testseitig isoliert abgesichert.

## 2026-03-08 – Regression nach Architekturänderung (persistente Retention-Scheduler-Infrastruktur)
- Anlass: neue persistente SQLite-Adapter für Scheduler-Lease und Retry-Recovery-Queue, inkl. Idempotenz-/Index-Governance.
- Ausgeführt: `python -m unittest discover -s tests -p 'test_*.py'`.
- Ergebnis: Grün, 74 Tests, 2 Skips (FastAPI-Dependency-abhängige Integrationstests).
- Bewertung: Keine Regression in WP-3 bis WP-6.2; Scheduler-/Recovery-Pfade sind restart- und konkurrenzsicher testseitig abgedeckt.


## 2026-03-08 – Regression nach Security-/Orchestrierungsanpassung (invalid Quarantine + Lease-Heartbeat)
- Anlass: Verhaltensänderung im Scheduler-Recovery-Pfad (`invalid` statt `recovered`) und Lease-Heartbeat-Erweiterung.
- Ausgeführt: `python -m unittest discover -s tests -p 'test_*.py'`.
- Ergebnis: Grün, 75 Tests, 2 Skips (FastAPI-Dependency-abhängige Integrationstests).
- Bewertung: Keine Regression in bestehenden Servicepfaden; Sicherheits- und Betriebsverhalten ist durch neue Tests abgesichert.


## 2026-03-08 – Regression nach Runtime-Orchestrierung (Scheduler-Startprofil)
- Anlass: neue Runtime-Orchestrierung und fail-fast Konfiguration für Retention-Scheduler.
- Ausgeführt: `python -m unittest discover -s tests -p 'test_*.py'`.
- Ergebnis: Grün, 78 Tests, 2 Skips (FastAPI-Dependency-abhängige Integrationstests).
- Bewertung: Kein regressiver Effekt auf bestehende Services; Runtime-Wiring und Config-Guards sind testseitig abgedeckt.

## 2026-03-08 – Regression nach Architekturänderung (dedizierter Retention-Scheduler-Runner)
- Anlass: neues Runtime-Modul `evodox.runtime.retention_scheduler_runner` inkl. fail-fast Entrypoint und Graceful-Shutdown-Orchestrierung.
- Ausgeführt: `python -m unittest discover -s tests -p 'test_*.py'`.
- Ergebnis: Grün, 82 Tests, 2 Skips (FastAPI-Dependency-abhängige Integrationstests).
- Bewertung: Keine Regression in bestehenden Servicepfaden; dedizierter Runner-Pfad inkl. Startfehler- und Shutdown-Verhalten ist testseitig abgedeckt.

## 2026-03-08 – Regression nach Runner-Bootstrap-Vervollständigung (produktives Dependency-Wiring)
- Anlass: strukturelle Erweiterung des Runtime-Entrypoints um produktives Bootstrap-Wiring (Retention-Job, Recovery-Executor, Filesystem-Storage, Policy-/Tenant-Konfiguration).
- Ausgeführt: `python -m unittest discover -s tests -p 'test_*.py'`.
- Ergebnis: Grün, 87 Tests, 2 Skips (FastAPI-Dependency-abhängige Integrationstests).
- Bewertung: Keine Regression in bestehenden Servicepfaden; Runner ist jetzt als ausführbarer Prozess mit fail-fast Bootstrap-Validierung abgesichert.

## 2026-03-08 – Regression nach Storage-Backend-/Governance-/Preflight-Erweiterung
- Anlass: strukturelle Erweiterung des Runner-Bootstraps (S3/MinIO-Adapter, versioniertes Recovery-Mapping, Deployment-Preflight).
- Ausgeführt: `python -m unittest discover -s tests -p 'test_*.py'`.
- Ergebnis: Grün, 92 Tests, 2 Skips (FastAPI-Dependency-abhängige Integrationstests).
- Bewertung: Keine Regression in bestehenden Servicepfaden; neuer Backend-/Governance-/Preflight-Pfad ist testseitig abgedeckt.

## 2026-03-08 – Regression nach Zielbetriebs-/Deploy-Artefakt-Erweiterung
- Anlass: strukturelle Betriebsänderung (Compose-Target-Stack, Preflight-Gating, CI-Preflight-Stage, Umgebungsprofile).
- Ausgeführt: `python -m unittest discover -s tests -p 'test_*.py'`.
- Ergebnis: Grün, 95 Tests, 2 Skips (FastAPI-Dependency-abhängige Integrationstests).
- Bewertung: Keine Regression in bestehenden Servicepfaden; neue Deploy-/Runbook-Artefakte und Governance-Checks sind testseitig abgesichert.
