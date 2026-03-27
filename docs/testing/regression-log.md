# Regression Log

## Hinweise
- Für reine Dokumentationsänderungen sind keine Regressionstests erforderlich.
- Bei Änderungen an Pipeline, Build, Architektur oder Mandantenmodell ist die vollständige Regression verpflichtend.

## Letzte Änderungen
- 2026-03-27: Korrekturmodus-Performance-Refactor (Virtualisierung/Event-Delegation/Delta-Operationen) implementiert.
  - Ausgefuehrt: node --test frontend/tests/*.test.js (69/69 gruen).
  - Nicht ausfuehrbar in dieser Umgebung: Python-Regression (python/py/uv nicht verfuegbar im PATH).
  - Offenes Risiko: Backend-Tests fuer neue update_text-/return_mode-Pfade muessen in CI bzw. Python-Runtime nachgezogen werden.
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



## 2026-03-22 - Regression nach Midpoint-Checkpointing + Cancel-Lifecycle
- Anlass: Architektur-/Lifecycle-Erweiterung um persistente Job-Checkpoints (`job_checkpoints`), terminalen Cancel-Endpunkt und Worker-Cancel-Prioritaet.
- Ausgefuehrt (Backend Regression): `docker run --rm -v <repo>:/work -w /work python:3.12-slim python -m unittest discover -s tests -p "test_*.py"`.
- Ergebnis (Backend Regression): Gruen, 139 Tests, 16 Skips.
- Ausgefuehrt (Frontend Regression): `node --test frontend/tests/*.test.js`.
- Ergebnis (Frontend Regression): Gruen, 14 Tests.
- Ausgefuehrt (Smoke mit FastAPI): `docker run --rm -v <repo>:/work -w /work python:3.12-slim sh -lc "pip install -q fastapi pydantic uvicorn httpx && python -m unittest tests.test_local_runtime_smoke"`.
- Ergebnis (Smoke): Gruen, 3 Tests (`create->complete->worker`, `pause->resume(checkpoint)`, `cancel->canceled`).
- Bewertung: Keine Regression in bestehender Queue-/Worker-/Frontend-Logik; neue Cancel- und Checkpoint-Pfade sind testseitig abgedeckt.

## 2026-03-22 - Regression Stabiler Job-Lifecycle (Force-Delete + no-auto-restart)
- Anlass: Delete fuer aktive Status, harte Timeout-Deaktivierung (`WORKER_WHISPERX_TIMEOUT_SECONDS=0`) und Worker-Exception-Handling ohne Retry-Loop.
- Ausgefuehrt (Backend Vollsuite): `docker run --rm -v C:\\Users\\patrick\\Evidowhisperx:/work -w /work evodox-local:dev sh -lc "python -m pip install --quiet httpx && python -m unittest discover -s tests -p 'test_*.py'"`.
- Ergebnis (Backend Vollsuite): Gruen, 147 Tests.
- Ausgefuehrt (Frontend): `node --test frontend/tests/*.test.js`.
- Ergebnis (Frontend): Gruen, 14 Tests.
- Ausgefuehrt (gezieltes Red->Green): `docker run --rm -v C:\\Users\\patrick\\Evidowhisperx:/work -w /work evodox-local:dev sh -lc "python -m pip install --quiet httpx && python -m unittest tests.test_worker_pipeline_service tests.test_job_lifecycle_service"`.
- Ergebnis (gezielt): Erst Red im neuen Resume-Dedupe-Test (6 statt 4 Segmente), danach Green mit Fix.
- Bewertung: Force-Delete- und Anti-Restart-Semantik sind regressionsseitig abgesichert; Pause/Resume bleibt auch bei nicht offset-faehiger ASR-Engine ohne Segmentduplikate konsistent.

## 2026-03-22 - Regression nach GPU-First Runtime + Multi-GPU Pool-Vorbereitung
- Anlass: Architektur-/Deployment-Aenderung fuer GPU-Default, CUDA-Fallback, Device-Index-Wiring und queue-basierte Worker-Pool-Vorbereitung.
- Ausgefuehrt (gezielte TDD-Red/Green):
  - `docker run --rm -v C:\Users\patrick\Evidowhisperx:/work -w /work python:3.11-slim bash -lc "pip install --no-cache-dir . fastapi uvicorn pydantic boto3 && python -m unittest tests.test_worker_runner tests.test_complete_upload_infrastructure tests.test_target_deployment_artifacts"`
- Ergebnis (gezielt): zuerst Red (neue GPU-/Queue-Tests), danach Green (25 Tests, OK).
- Ausgefuehrt (Backend Vollsuite):
  - `docker run --rm -v C:\Users\patrick\Evidowhisperx:/work -w /work python:3.11-slim bash -lc "pip install --no-cache-dir . fastapi uvicorn pydantic boto3 httpx && python -m unittest discover -s tests -p 'test_*.py'"`
- Ergebnis (Backend Vollsuite): Gruen, 156 Tests, 0 Failures.
- Ausgefuehrt (Frontend Regression):
  - `node --test frontend/tests/*.test.js`
- Ergebnis (Frontend): Gruen, 14 Tests.
- Bewertung: Keine Regression in API/Worker/Queue/Frontend-Flows; GPU-Fallback und Multi-Pool-Vorbereitung sind testseitig abgesichert.

## 2026-03-22 - Regression nach Tenant-Admin Decoding Settings + Job-Snapshot
- Anlass: neue admin-only API fuer Decoding-Defaults, neue Persistenz (`tenant_transcription_settings`, Job-Snapshot), Queue/Resume/Worker-Wiring und Frontend-Admin-Route.
- Ausgefuehrt (gezielte TDD-Suite):
  - `docker run --rm -v C:\Users\patrick\Evidowhisperx:/work -w /work python:3.11-slim bash -lc "pip install --no-cache-dir . && python -m unittest tests.test_transcription_settings_service tests.test_complete_upload_service tests.test_job_lifecycle_service tests.test_worker_runner tests.test_job_infra_adapters"`
- Ergebnis (gezielt): Gruen, 57 Tests.
- Ausgefuehrt (FastAPI-Integrationssuite):
  - `docker run --rm -v C:\Users\patrick\Evidowhisperx:/work -w /work python:3.11-slim bash -lc "pip install --no-cache-dir . fastapi pydantic httpx && python -m unittest tests.test_fastapi_http_adapter_integration"`
- Ergebnis (FastAPI): Gruen, 16 Tests.
- Ausgefuehrt (Backend Vollsuite):
  - `docker run --rm -v C:\Users\patrick\Evidowhisperx:/work -w /work python:3.11-slim bash -lc "pip install --no-cache-dir . fastapi pydantic boto3 httpx && python -m unittest discover -s tests -p 'test_*.py'"`
- Ergebnis (Backend Vollsuite): Gruen, 170 Tests.
- Ausgefuehrt (Frontend Regression):
  - `node --test frontend/tests/*.test.js`
- Ergebnis (Frontend): Gruen, 18 Tests.
- Bewertung: Keine Regression in bestehenden Lifecycle-/Queue-/Worker-Pfaden; neue Admin-Settings und Snapshot-Semantik sind integriert und abgesichert.

## 2026-03-22 - UI Screenshot-Nachweis (Transcription Settings)
- Anlass: UI-Aenderung an neuer Admin-Route `transcription-settings`.
- Ausgefuehrt: `node scripts/capture_transcription_settings_screenshots.mjs`.
- Ergebnis:
  - `docs/testing/screenshots/transcription-settings-default.png`
  - `docs/testing/screenshots/transcription-settings-validation-error.png`
  - `docs/testing/screenshots/transcription-settings-responsive.png`
- Bewertung: Screenshot-Pflicht fuer Default-, Validierungs-/Fehler- und Responsive-Zustand erfuellt.

## 2026-03-23 - Regression nach WhisperX large-v3 Erzwingung + Sprachwahl + Chunk/VAD
- Anlass: Runtime-/API-/UI-Aenderung fuer harte Modellwahl (large-v3), Sprachwahl pro Job und neue Decoding-Parameter (chunk_size, vad_onset, vad_offset).
- Ausgefuehrt (gezielte Frontend-Tests): node --test frontend/tests/upload_flow.test.js frontend/tests/transcription_settings_flow.test.js.
- Ergebnis (gezielt Frontend): Gruen.
- Ausgefuehrt (Frontend Regression): node --test frontend/tests/*.test.js.
- Ergebnis (Frontend Regression): Gruen, 23 Tests.
- Ausgefuehrt (gezielte Backend-Tests): docker run --rm -v C:\Users\patrick\Evidowhisperx:/work -w /work python:3.11-slim sh -lc "pip install --quiet . fastapi pydantic httpx && python -m unittest tests.test_job_create_service tests.test_complete_upload_service tests.test_transcription_settings_service tests.test_worker_runner tests.test_fastapi_http_adapter_integration".
- Ergebnis (gezielt Backend): Gruen, 65 Tests.
- Ausgefuehrt (Backend Vollsuite): docker run --rm -v C:\Users\patrick\Evidowhisperx:/work -w /work python:3.11-slim sh -lc "pip install --quiet . fastapi pydantic boto3 httpx && python -m unittest discover -s tests -p 'test_*.py'".
- Ergebnis (Backend Vollsuite): Gruen, 187 Tests.
- Bewertung: Keine Regression in bestehenden Lifecycle-/Queue-/Worker-Pfaden; neue Spracheinstellungen und Chunk/VAD-Wiring sind testseitig abgesichert.
## 2026-03-23 - UI Screenshot-Nachweis (New Job Sprache + Transcription Settings)
- Anlass: UI-Aenderungen in New-Job-View (Sprach-Dropdown) und Admin-Transcription-Settings (chunk_size, vad_onset, vad_offset).
- Ausgefuehrt: node scripts/capture_new_job_language_screenshots.mjs.
- Ausgefuehrt: node scripts/capture_transcription_settings_screenshots.mjs.
- Ergebnis:
  - docs/testing/screenshots/new-job-language-default.png
  - docs/testing/screenshots/new-job-language-responsive.png
  - docs/testing/screenshots/transcription-settings-default.png
  - docs/testing/screenshots/transcription-settings-validation-error.png
  - docs/testing/screenshots/transcription-settings-responsive.png
- Bewertung: Screenshot-Pflicht fuer betroffene Hauptscreens und relevante Zustaende ist erfuellt.

## 2026-03-24 - Korrekturmodus
- Frontend-Unit-Suite (`node --test frontend/tests/*.test.js`) erfolgreich ausgefuehrt: 28/28 gruen.
- Backend-Korrekturtests via Docker ausgefuehrt:
  - `docker run --rm -v C:\Users\patrick\Evidowhisperx:/work -w /work python:3.11-slim sh -lc "pip install --quiet . fastapi pydantic httpx && python -m unittest tests.test_transcript_correction_service tests.test_transcript_correction_store tests.test_transcript_correction_http_adapter tests.test_transcript_correction_fastapi_integration"`
  - Ergebnis: gruen, 17 Tests.
- Screenshot-Automation fuer Korrekturmodus ausgefuehrt: `node scripts/capture_correction_mode_screenshots.mjs`.
- Screenshot-Artefakte:
  - `docs/testing/screenshots/correction-shell-default.png`
  - `docs/testing/screenshots/correction-editor-validation-error.png`
  - `docs/testing/screenshots/correction-shell-responsive.png`

## 2026-03-25 - Regression Korrekturmodus Stabilisierung + UX/Audio
- Anlass: Start-Handover auf tabuebergreifenden TTL-Store, neue Media-Source-API, UI-Layout-/Close-Flow-/Audio-Scroll-Anpassungen.
- Ausgefuehrt (Frontend Unit): `cmd /c npm test` in `frontend/`.
- Ergebnis (Frontend Unit): Gruen, 32 Tests.
- Ausgefuehrt (Backend Correction-Suite): `docker run --rm -v C:\Users\patrick\Evidowhisperx:/workspace -w /workspace evodox-local:dev sh -lc "pip install --quiet httpx && python -m unittest tests.test_transcript_correction_fastapi_integration tests.test_transcript_correction_http_adapter tests.test_transcript_correction_service tests.test_transcript_correction_store"`.
- Ergebnis (Backend Correction-Suite): Gruen, 20 Tests.
- Ausgefuehrt (UI-Screenshot-Nachweis): `node scripts/capture_correction_mode_screenshots.mjs`.
- Ergebnis (Screenshots): aktualisiert (`correction-shell-default`, `correction-editor-validation-error`, `correction-shell-responsive`).
- Docker Smoke: `docker build -f deploy/Dockerfile.runtime -t evodox-local:dev .` und `docker compose -f deploy/docker-compose.target.yml --env-file .env up -d api worker retention-runner frontend`; alle Services healthy.

## 2026-03-26 - Regression Korrekturmodus Absolute Timeline (ADR-0022)
- Anlass: Entfernung der Seed-Kompaktierung, Zulassen von Timeline-Luecken, finite Timeline-Validation und Frontend-Sync fuer interne Pausen.
- Ausgefuehrt (Backend Red/Green): `python -m unittest tests.test_transcript_correction_service tests.test_transcript_correction_fastapi_integration`.
- Ergebnis (Backend Red/Green): zuerst Red (Gap-Reject, Seed-Kompaktierung, fehlende NaN/inf-Pruefung), danach Green.
- Ausgefuehrt (Backend Green-Recheck): `python -m unittest tests.test_transcript_correction_service tests.test_transcript_correction_fastapi_integration`.
- Ergebnis (Backend Green-Recheck): Gruen, 18 Tests, 7 Skips.
- Hinweis (Store-Suite auf Windows): `tests.test_transcript_correction_store` zeigt in dieser Umgebung intermittierende Temp-File-Locks (`WinError 32`) beim Cleanup; nicht durch ADR-0022 verursacht.
- Frontend-Unit-/Screenshot-Checks in dieser Umgebung nicht ausfuehrbar, da `node`/`npm` nicht installiert sind.
- Reproduktion fuer Zielumgebung:
  - Frontend Tests: `node --test frontend/tests/*.test.js`
  - Screenshot-Nachweis: `node scripts/capture_correction_mode_screenshots.mjs`

## 2026-03-26 - Regression Legacy-Reseed + End-Pause-Active-Block
- Anlass: Additive Timeline-Drift in Legacy-Resumes und aktiver Block nach letztem Segmentende.
- Ausgefuehrt (Backend Red/Green): `python -m unittest tests.test_transcript_correction_service tests.test_transcript_correction_fastapi_integration tests.test_transcript_correction_http_adapter`.
- Ergebnis (Backend Red/Green): zuerst Red (fehlendes `force_reseed_from_transcript`), danach Green (24 Tests, 9 Skips).
- Frontend-Tests in dieser Umgebung nicht ausfuehrbar (`node` nicht installiert).
- Erwartete Reproduktion im Zielsystem: `node --test frontend/tests/correction_utils.test.js`.

## 2026-03-26 - Regression nach Korrektur-Export-Umstellung (raw/compact)
- Anlass: Frontend-Exportlogik erweitert (kompaktierter Lesemodus + Rohdatenmodus + Export-Metadatenheader).
- Ausgefuehrt:
  - `docker run --rm -v C:\Users\Patrick\EvidoX:/work -w /work node:22-alpine node --test frontend/tests/correction_workspace_export.test.js`
  - `docker run --rm -v C:\Users\Patrick\EvidoX:/work -w /work node:22-alpine node --test frontend/tests/*.test.js`
  - `python -m unittest tests.test_transcript_correction_service tests.test_transcript_correction_fastapi_integration`
- Ergebnis: Gruen (Frontend 63/63, Export-spezifisch 9/9, Python 22 Tests OK / 9 Skips).
- Bewertung: Keine Regression im Timeline-Sync; Aenderung wirkt nur im Korrektur-Exportpfad.


## 2026-03-26 - Regression Korrekturmodus Seed-Overlap Hotfix
- Anlass: `POST /transcript/correction-sessions` konnte bei bestehenden Transcripts mit minimalen Rundungs-Overlaps mit `422 transcript.timeline_overlap` fehlschlagen.
- Ausgefuehrt: `docker run --rm -v C:\Users\Patrick\EvidoX:/work -w /work python:3.11-slim python -m unittest tests.test_transcript_correction_service tests.test_job_infra_adapters`.
- Ergebnis: Gruen, 33 Tests.
- Bewertung: Korrekturmodus startet wieder fuer betroffene Jobs; grosse Overlaps bleiben weiterhin geblockt.

## 2026-03-26 - Regression nach Korrekturmodus UI-Modernisierung
- Anlass: Header-Redesign (3 Zonen), neues Export-Submenue, Toggle-Umstellung und dezente Speaker-Farbkodierung im Korrekturmodus.
- Ausgefuehrt (Frontend Regression): `node --test frontend/tests/*.test.js`.
- Ergebnis (Frontend Regression): Gruen, 66 Tests.
- Ausgefuehrt (UI Screenshot-Nachweis): `node scripts/capture_correction_mode_screenshots.mjs`.
- Ergebnis (Screenshots):
  - `docs/testing/screenshots/correction-shell-default.png`
  - `docs/testing/screenshots/correction-editor-validation-error.png`
  - `docs/testing/screenshots/correction-shell-responsive.png`
- Bewertung: Keine Regression in Export-/Toggle-/Workspace-Logik; Screenshot-Pflicht fuer Default-, Validierungs- und Responsive-Zustand erfuellt.

## 2026-03-26 - Regression nach Korrekturmodus UI-Feinschliff (Header/Buttons/Media/Sidebar)
- Anlass: Header-Rounding und einheitliche Button-Groessen, Light-Mode-Button-Kontrast, dezent verstaerkte Speaker-Tints, Media-State-Persistenz ueber UI-Render sowie eingeklappter Sidebar-Default.
- Ausgefuehrt (Frontend Regression): `node --test frontend/tests/*.test.js`.
- Ergebnis (Frontend Regression): Gruen, 67 Tests.
- Ausgefuehrt (UI Screenshot-Nachweis): `node scripts/capture_correction_mode_screenshots.mjs`.
- Ergebnis (Screenshots aktualisiert):
  - `docs/testing/screenshots/correction-shell-default.png`
  - `docs/testing/screenshots/correction-editor-validation-error.png`
  - `docs/testing/screenshots/correction-shell-responsive.png`
- Bewertung: Keine Regression in Korrektur-Export-/Toggle-/Media-Sync-Pfaden; UI-Anforderungen umgesetzt.

## 2026-03-26 - Regression nach Header-Kompaktlayout + Icon-Toolbar
- Anlass: Header um 3-Spalten-Grid reduziert, neue kompakte Toolbar-Anordnung mit Icon-Buttons (Save/Print/Undo/Redo), angepasste Button-/Toggle-Proportionen.
- Ausgefuehrt (Frontend Regression): `node --test frontend/tests/*.test.js`.
- Ergebnis (Frontend Regression): Gruen, 67 Tests.
- Ausgefuehrt (UI Screenshot-Nachweis): `node scripts/capture_correction_mode_screenshots.mjs`.
- Ergebnis (Screenshots aktualisiert):
  - `docs/testing/screenshots/correction-shell-default.png`
  - `docs/testing/screenshots/correction-editor-validation-error.png`
  - `docs/testing/screenshots/correction-shell-responsive.png`
- Bewertung: Keine Regression in Korrekturmodus-Funktionen; Header-Verhalten und Bedienflaeche bleiben stabil.

## 2026-03-26 - Regression nach Header-Reflow + staerkere Speaker-Rahmen
- Anlass: Header auf 2-Zonen-Layout umgestellt (vollbreite Buttonzeile + Statuszeile), neue Rot/Gruen-Semantik fuer `Autosave`/`Auto-Sprung`, kraeftigere Sprecherfarben bei Transcript-Bloecken.
- Ausgefuehrt (Frontend Regression): `node --test frontend/tests/*.test.js`.
- Ergebnis (Frontend Regression): Gruen, 67 Tests.
- Ausgefuehrt (UI Screenshot-Nachweis): `node scripts/capture_correction_mode_screenshots.mjs`.
- Ergebnis (Screenshots aktualisiert):
  - `docs/testing/screenshots/correction-shell-default.png`
  - `docs/testing/screenshots/correction-editor-validation-error.png`
  - `docs/testing/screenshots/correction-shell-responsive.png`
- Bewertung: Keine Regression in Export-/Toggle-/Media-/Korrektur-Logik; neue Header- und Farbsemantik stabil.

## 2026-03-26 - Regression nach Fokus-Hervorhebung (Active/Selected Block)
- Anlass: aktive und selektierte Transcript-Bloecke waren visuell zu schwach; Hervorhebung fuer Klick- und Media-Fokus wurde verstaerkt.
- Ausgefuehrt (Frontend Regression): `node --test frontend/tests/*.test.js`.
- Ergebnis (Frontend Regression): Gruen, 67 Tests.
- Ausgefuehrt (UI Screenshot-Nachweis): `node scripts/capture_correction_mode_screenshots.mjs`.
- Ergebnis (Screenshots aktualisiert):
  - `docs/testing/screenshots/correction-shell-default.png`
  - `docs/testing/screenshots/correction-editor-validation-error.png`
  - `docs/testing/screenshots/correction-shell-responsive.png`
- Bewertung: Keine Regression in Playback-/Selection-Logik; Fokuszustand ist visuell klarer erkennbar.

## 2026-03-27 - Regression Korrekturmodus-Performance (Virtualisierung + Delta-Ops)
- Anlass: Performance-Optimierung fuer grosse Transkripte im Korrekturmodus (Windowing, Delegation, Delta-Operationen `update_text`, `return_mode`).
- Ausgefuehrt (Frontend Regression): `node --check frontend/correction_workspace.js` und `node --test frontend/tests/*.test.js`.
- Ergebnis (Frontend Regression): Gruen, 69/69 Tests.
- Ausgefuehrt (Backend gezielte Regression via Docker): `docker run --rm -v C:\Users\patrick\Evidowhisperx:/work -w /work python:3.11-slim sh -lc "pip install --quiet . fastapi pydantic httpx && python -m unittest tests.test_transcript_correction_service.TranscriptCorrectionServiceTests.test_update_text_operation_updates_target_segment_and_diff_metadata tests.test_transcript_correction_service.TranscriptCorrectionServiceTests.test_update_text_rejects_empty_text tests.test_transcript_correction_http_adapter.TranscriptCorrectionHttpAdapterTests.test_maps_correction_session_response_changed_segments_mode tests.test_transcript_correction_http_adapter.TranscriptCorrectionHttpAdapterTests.test_maps_correction_session_response_ack_mode tests.test_transcript_correction_fastapi_integration.TranscriptCorrectionFastAPIIntegrationTests.test_correction_session_roundtrip_and_commit tests.test_transcript_correction_fastapi_integration.TranscriptCorrectionFastAPIIntegrationTests.test_correction_operations_ack_mode_with_update_text"`.
- Ergebnis (Backend gezielte Regression): Gruen, 6/6 Tests.
- Zusatzlauf (Backend Full-Suite Correction via Docker): 31 Tests, 1 Fehler in Legacy-Migrationspfad (`sqlite3.OperationalError: Cannot add a column with non-constant default` bei `test_legacy_session_open_reseeds_and_removes_additive_drift`); nicht im Scope der Delta-/Virtualisierungsänderung.
- Screenshot-Nachweis (UI-Pflicht): `node scripts/capture_correction_mode_screenshots.mjs` in dieser Umgebung fehlgeschlagen, weil Modul `playwright` fehlt.
- Reproduktion Screenshot-Nachweis (sobald Abhaengigkeit installiert): `npm --prefix frontend install` und danach `node scripts/capture_correction_mode_screenshots.mjs`.


## 2026-03-27 - Regression Playback Autofocus Follow (Virtualized Editor)
- Anlass: Nach Virtualisierung folgte der sichtbare Editor beim laufenden Media-Playback nicht mehr stabil dem aktiven Segment.
- Ausgefuehrt (Red): `node --test frontend/tests/correction_workspace_viewmodel.test.js` vor Implementierung, erwarteter Fehler wegen fehlender Exporte (`resolvePlaybackFollowDecision`/`resolveVirtualWindowPreferredIndex`).
- Ausgefuehrt (Green): `node --check frontend/correction_workspace_viewmodel.js`, `node --check frontend/correction_workspace.js`, `node --test frontend/tests/correction_workspace_viewmodel.test.js`.
- Ergebnis (Green): Gruen, 29/29 Tests.
- Ausgefuehrt (Frontend Regression): `node --test frontend/tests/*.test.js`.
- Ergebnis (Frontend Regression): Gruen, 74/74 Tests.
- Screenshot-Nachweis (UI-Interaktion): `node scripts/capture_correction_mode_screenshots.mjs` in dieser Umgebung fehlgeschlagen (`Cannot find module 'playwright'`).
- Reproduktion fuer Screenshot-Nachweis: `npm --prefix frontend install` und danach `node scripts/capture_correction_mode_screenshots.mjs`.

## 2026-03-27 - Regression Seek ausserhalb Virtual-Window (Warmup + Resume)
- Anlass: Slider-Seek auf Positionen ausserhalb des gerenderten Windows lieferte keinen zuverlaessigen Nachzug des Zielblocks.
- Ausgefuehrt (Syntax): `node --check frontend/correction_workspace_viewmodel.js` und `node --check frontend/correction_workspace.js`.
- Ausgefuehrt (Unit): `node --test frontend/tests/correction_workspace_viewmodel.test.js`.
- Ergebnis (Unit): Gruen, 36/36 Tests.
- Ausgefuehrt (Frontend Regression): `node --test frontend/tests/*.test.js`.
- Ergebnis (Frontend Regression): Gruen, 81/81 Tests.
- Screenshot-Nachweis (UI-Interaktion): `node scripts/capture_correction_mode_screenshots.mjs` in dieser Umgebung fehlgeschlagen (`Cannot find module 'playwright'`).
- Reproduktion fuer Screenshot-Nachweis: `npm --prefix frontend install` und danach `node scripts/capture_correction_mode_screenshots.mjs`.
## 2026-03-27 - Regression Seek/Autofokus Lifecycle-Hardening (Media-Reuse + Variable Hoehen)
- Anlass: Bei Seek ausserhalb des Virtual-Windows wurden teils leere Bereiche fokussiert; anschliessend brach Auto-Follow nach Media-Fortschritt sporadisch ab.
- Ausgefuehrt (Syntax): node --check frontend/correction_workspace_viewmodel.js und node --check frontend/correction_workspace.js.
- Ergebnis (Syntax): Gruen.
- Ausgefuehrt (Viewmodel Unit): node --test frontend/tests/correction_workspace_viewmodel.test.js.
- Ergebnis (Viewmodel Unit): Gruen, 38/38 Tests.
- Ausgefuehrt (Frontend Regression): node --test frontend/tests/*.test.js.
- Ergebnis (Frontend Regression): Gruen, 83/83 Tests.
- Ausgefuehrt (UI Screenshot-Nachweis): node scripts/capture_correction_mode_screenshots.mjs.
- Ergebnis (UI Screenshot-Nachweis): Fehlgeschlagen, Abhaengigkeit playwright fehlt (Cannot find module 'playwright').
- Reproduktion Screenshot-Nachweis: npm --prefix frontend install und danach node scripts/capture_correction_mode_screenshots.mjs.
## 2026-03-27 - Regression Seek/Autofokus: Empty-Window + Drift
- Anlass: Bei Seek auf weit entfernte Zeitpunkte wurden teils keine relevanten Bloecke gerendert; bei laufender Wiedergabe driftete der aktive Fokusblock aus dem Sichtfeld.
- Ausgefuehrt (Red): node --test frontend/tests/correction_workspace_viewmodel.test.js (fehlender Export `resolveForcedVirtualRange` -> erwarteter Red-Start).
- Ausgefuehrt (Green): node --check frontend/correction_workspace_viewmodel.js, node --check frontend/correction_workspace.js, node --test frontend/tests/correction_workspace_viewmodel.test.js.
- Ergebnis (Green): Gruen, 41/41 Tests.
- Ausgefuehrt (Frontend Regression): node --test frontend/tests/*.test.js.
- Ergebnis (Frontend Regression): Gruen, 86/86 Tests.
- Screenshot-Nachweis (UI-Interaktion): node scripts/capture_correction_mode_screenshots.mjs in dieser Umgebung nicht ausfuehrbar (Cannot find module 'playwright').
- Reproduktion Screenshot-Nachweis: npm --prefix frontend install und danach node scripts/capture_correction_mode_screenshots.mjs.
## 2026-03-27 - Regression Editor-Scrollbar Empty-Window
- Anlass: Scrollbar-Spruenge im Editor konnten leere Bereiche zeigen, weil Selection-Pinning die Scroll-range ueberschrieb.
- Ausgefuehrt: node --check frontend/correction_workspace_viewmodel.js, node --check frontend/correction_workspace.js.
- Ergebnis: Gruen.
- Ausgefuehrt: node --test frontend/tests/correction_workspace_viewmodel.test.js.
- Ergebnis: Gruen, 43/43 Tests.
- Ausgefuehrt: node --test frontend/tests/*.test.js.
- Ergebnis: Gruen, 88/88 Tests.
## 2026-03-27 - Benchmark Virtual-Window Blockanzahl (Human-Latency Sweet Spot)
- Anlass: Bestimmung der maximalen Blockanzahl pro Renderfenster ohne fuer Nutzer stoerende Latenz.
- Tooling: scripts/benchmark_correction_virtual_window.mjs (Playwright Chromium, 80 Iterationen je Fenstergroesse).
- Ausgefuehrt: node scripts/benchmark_correction_virtual_window.mjs.
- Kernergebnis: Bei 30m-Profil (600 Segmente) bleibt p95 bis ca. 450 Bloecke im instant-Bereich (<100ms); 600 Bloecke liegen im noticeable-Bereich (p95 ~113-147ms).
- Empfehlung: dynamischer Zielbereich 300-450 Bloecke fuer interaktive Spruenge; Voll-Laden bis 300 Segmente unkritisch, bei 600 Segmenten progressiv/idle nachladen statt sofort voll.
## 2026-03-27 - Regression Adaptive Virtual-Window
- Anlass: Umsetzung der empfohlenen Sweet-Spot-Strategie fuer Blockanzahl pro Renderfenster.
- Ausgefuehrt (Syntax): node --check frontend/correction_workspace_viewmodel.js, node --check frontend/correction_workspace.js.
- Ergebnis (Syntax): Gruen.
- Ausgefuehrt (Unit): node --test frontend/tests/correction_workspace_viewmodel.test.js.
- Ergebnis (Unit): Gruen, 46/46 Tests.
- Ausgefuehrt (Frontend Regression): node --test frontend/tests/*.test.js.
- Ergebnis (Frontend Regression): Gruen, 91/91 Tests.

## 2026-03-27 - Regression Adaptive Progress-UI (Dashboard + Jobdetail)
- Anlass: sichtbarer Zwischenfortschritt zwischen Milestones ohne Backend-Contract-Aenderung.
- Ausgefuehrt (Syntax): `node --check frontend/utils.js`, `node --check frontend/app.js`.
- Ergebnis (Syntax): Gruen.
- Ausgefuehrt (Unit): `node --test frontend/tests/utils.test.js`.
- Ergebnis (Unit): Gruen, 20/20 Tests.
- Ausgefuehrt (Frontend Regression): `node --test frontend/tests/*.test.js`.
- Ergebnis (Frontend Regression): Gruen, 97/97 Tests.
- UI-Screenshot-Nachweis: in dieser Umgebung nicht automatisiert durchgefuehrt (kein passender Dashboard/Jobdetail Capture-Runner vorhanden).

## 2026-03-27 - Regression Progress Freeze (Jobdetail bei ~28%)
- Anlass: Jobdetail-Interpolation stoppte in langen `processing`-Phasen trotz erfolgreicher Poll-Responses frueh.
- Log-Analyse: wiederholte `GET /api/v1/jobs/{id}` mit `200` alle ~5s, gleichzeitig UI-Stillstand => Freshness-Timestamp wurde nicht aktualisiert.
- Root Cause: Interpolations-Stale-Check basierte auf `lastServerTimestamp`, der nur bei geaendertem `status/progress` erneuert wurde.
- Ausgefuehrt (Syntax): `node --check frontend/utils.js`, `node --check frontend/app.js`.
- Ergebnis (Syntax): Gruen.
- Ausgefuehrt (Unit): `node --test frontend/tests/utils.test.js`.
- Ergebnis (Unit): Gruen, 21/21 Tests.
- Ausgefuehrt (Frontend Regression): `node --test frontend/tests/*.test.js`.
- Ergebnis (Frontend Regression): Gruen, 98/98 Tests.
- Zusatzverifikation (Simulation): konstantes Server-Progress `20%` mit frischen Poll-Snapshots zeigt Anstieg bis Milestone-Cap (`59%`) statt Freeze bei ~28%.

## 2026-03-27 - Regression Progresskurve >59% (kein 59%-Freeze, kein fruehes 99%)
- Anlass: nach erstem Freeze-Fix blieb Anzeige nicht mehr bei 59%, lief aber in Tests zu schnell auf 99%.
- Ausgefuehrt (Simulation): konstantes `processing` mit frischen Poll-Snapshots; Verlauf validiert (z. B. 60s=28, 300s=64, 420s=82).
- Ausgefuehrt (Unit): `node --test frontend/tests/utils.test.js`.
- Ergebnis (Unit): Gruen, 21/21.
- Ausgefuehrt (Frontend Regression): `node --test frontend/tests/*.test.js`.
- Ergebnis (Frontend Regression): Gruen, 98/98.
