# Test Strategy (TDD) â€“ inkl. Edge/Security-Tests pro Entwicklungsschritt

Verbindliche Freeze-Referenz: `docs/testing/test-spec-v1.md`.

## 1) Verbindlicher Ablauf je Arbeitspaket
1. Akzeptanzkriterien + Security-Akzeptanzkriterien festlegen
2. Edge-Case-Katalog fÃ¼r das Paket definieren
3. Failing Tests zuerst schreiben (Red)
4. Minimal implementieren (Green)
5. Refactor ohne VerhaltensÃ¤nderung
6. Security-Review + Doku-Update als DoD-Pflicht

## 2) Testebenen (fÃ¼r alle Schritte)
- **Unit:** Business-Regeln (Tenant-Scoping, Retention, Statuswechsel, Validatoren)
- **Integration:** APIâ†”DB, APIâ†”Queue, Workerâ†”Storage, Auth-Flow gegen Keycloak-Testumgebung
- **Contract:** API- und Event-Schema-Tests
- **E2E:** Upload â†’ Queue â†’ Verarbeitung â†’ Edit â†’ Export
- **Security/Abuse:** Negative Tests (AuthZ-Bypass, Rate-Limit-Evasion, Payload-Manipulation)

## 3) Edge-/Abuse-Testkatalog (global verpflichtend)
- **Prompt-Injection/Instruction-Injection:**
  - Transkript-/Metadateninhalte mit â€žignore previous instructionsâ€œ, Script-Tags, Command-Mustern dÃ¼rfen keine privilegierten Aktionen auslÃ¶sen.
  - Inhalte werden als Daten behandelt, nie als Steueranweisung.
- **Rate-Limiting & Abuse:**
  - Burst- und Sustained-Traffic-Tests pro Tenant/Benutzer/IP.
  - Retry-StÃ¼rme (Client + Worker) dÃ¼rfen System nicht destabilisieren.
- **Unkonventionelle Eingaben:**
  - Sehr lange Dateinamen, Unicode/RTL, Nullbytes, doppelte Extensions, ungÃ¼ltige MIME-Header.
  - Korruptes Media, unvollstÃ¤ndige Chunks, Out-of-order Chunks.
- **Eingabevalidierung:**
  - Schema-Validation fÃ¼r API-Inputs (z. B. `retention_months` Grenzen, Job-Parameter-Whitelists).
  - Path Traversal, SQLi-/NoSQLi-Muster, Header Injection, JSON Bombs.

## 4) Entwicklungsschritt-spezifische Teststrategie

### Schritt 1 â€“ Architektur- und Governance-Festlegung
- DoR: Security- und Testanforderungen pro Komponente dokumentiert.
- Tests: Dokumentations-QualitÃ¤tschecks (VollstÃ¤ndigkeit, Konsistenz der Testpflichten).
- Edge-Fokus: Kein Schritt ohne definierten Edge-Testkatalog zulÃ¤ssig.

### Schritt 2 â€“ Repo-/Infra-Struktur (On-Prem Docker)
- Integration: Container-Netzwerk, Secrets-Mounts, Healthchecks.
- Edge/Security:
  - Fehlkonfigurationen (offene Ports, Default-PasswÃ¶rter) mÃ¼ssen fehlschlagen.
  - Image- und Dependency-Scans als Gate.
  - Rate-Limit-Konfiguration am Proxy automatisiert testen.

### Schritt 3 â€“ Auth + Upload Skeleton
- Integration/E2E:
  - OIDC Login, Tenant-Claims, Token-Expiry/Refresh-Verhalten.
  - Chunked Upload Happy Path + Abbruch/Fortsetzen.
- Edge/Security:
  - AuthZ-Bypass-Versuche (Cross-Tenant IDs, manipulierte Claims).
  - Upload-Fuzzing: MIME-Spoofing, oversized files, ungÃ¼ltige Chunks.
  - Rate-Limit- und Throttling-Tests gegen Upload-/Job-Endpunkte.

### Schritt 4 â€“ Processing Pipeline (Queue + Worker + Skalierung)
- Integration:
  - Queue-Routing (gpu-long/gpu-standard/cpu-short), Retry/Backoff/DLQ.
  - Long-running Jobs (mehrstÃ¼ndige MP4) unter begrenzter GPU.
- Edge/Security:
  - Poison Messages, Duplicate Delivery, Worker-Restart-Recovery.
  - Prompt-Injection-artige Inhalte in Transkripten dÃ¼rfen keine Systemlogik beeinflussen.
  - Tenant-Fairness unter Last (keine Starvation eines Tenants).

### Schritt 5 â€“ Transcript Edit + Export
- E2E:
  - Versionierung, optimistic locking, Export-Erzeugung.
- E2E/Integration:
  - Speaker-Alias-Snapshot pro Transcript-Version.
  - Blockbildung in der Task View: gleiche Roh-Speaker in Folge werden zusammengefasst.
- Edge/Security:
  - XSS/HTML-Injection in Editoren und Exportvorschau.
  - Export-Zugriff nur im Tenant Scope.
  - Malformed Unicode/Control Characters in Transkripttexten.
  - Alias-Input mit Steuerzeichen, leeren Werten und Cross-Tenant-Scoping wird abgewiesen.

### Schritt 6 â€“ Retention, Compliance, BetriebshÃ¤rtung
- Integration:
  - `EVIDOX_DEFAULT_RETENTION_MONTHS` Default und Policy-Override.
  - LÃ¶schjobs inkl. Audit-Nachweis.
- Edge/Security:
  - Manipulationsversuche an Retention-Feldern.
  - Restore-Tests mit Tenant-KonsistenzprÃ¼fung.
  - Incident-Runbook-Drills (Queue-Stau, AuthZ-Anomalien).

## 5) Regression-Gates (verbindlich)
- VollstÃ¤ndige Regression bei Ã„nderungen an Pipeline, Build, Architektur, Mandantenmodell, Queueing.
- FÃ¼r reine Doku-Ã„nderungen: keine Runtime-Regression erforderlich, aber Konsistenzchecks der Doku verpflichtend.


## 6) Freeze-Gates fÃ¼r Implementierungsstart (Schritt 3)
- Keine offenen Muss-Anforderungen.
- API-Operationen vollstÃ¤ndig mit AuthZ/Tenant/Validierung dokumentiert.
- DatenentitÃ¤ten vollstÃ¤ndig mit Retention/Audit-Regeln dokumentiert.
- Kritische Risiken mit GegenmaÃŸnahmen und TestfÃ¤llen hinterlegt.


## 7) Gate-Profile (CI-Blocker) je Entwicklungsschritt

### Schritt 3 (Auth + Upload)
- Pflicht-Gates: Lint/Schema, Unit, Integration, Contract, Security/Abuse.
- Blocker: Jeder fehlgeschlagene Cross-Tenant-, Claim-Manipulations- oder Upload-Validation-Test.
- Verantwortlich: API-Team + Security + QA.

### Schritt 4 (Pipeline + Queue + Worker)
- Pflicht-Gates: Lint/Schema, Unit, Integration, Contract, Security/Abuse, Regression.
- Blocker: DLQ/Retry/Poison-Message-Resilience-Test schlÃ¤gt fehl; Tenant-Fairness nicht erfÃ¼llt.
- Verantwortlich: Worker-Team + Ops + QA.

### Schritt 5 (Edit + Export)
- Pflicht-Gates: Lint/Schema, Unit, Integration, Contract, Security/Abuse, E2E.
- Blocker: XSS/Injection-/Export-AuthZ-Test fehlgeschlagen.
- Verantwortlich: API/Frontend + Security + QA.

### Schritt 6 (Retention + Compliance)
- Pflicht-Gates: Lint/Schema, Unit, Integration, Security/Abuse, E2E/Operations-Drills, Regression.
- Blocker: fehlender Audit-Nachweis fÃ¼r LÃ¶schpfade oder Restore-Konsistenzverletzung.
- Verantwortlich: Ops + API + Security + QA.

## WP-5.1/5.2 Nachweis (Transcript-Versionierung + Speaker-Aliase)
- Unit/Integration: `tests/test_transcript_service.py` und neue Frontend-Tests decken Alias-Snapshot, Blockbildung und Conflict-Faelle ab.
- Contract/Core HTTP: `tests/test_transcript_http_adapter.py` prueft GET/PUT-Transcript-Responses inklusive Speaker-Label-Update.
- Security/Abuse: Alias-Injection, Cross-Tenant-Missbrauch, Control Characters und falsche Blockfusion werden explizit getestet.
- Ergebnisnachweis: Versionierte Aliase und gruppierte Speaker-Bloecke muessen im UI und in der API konsistent sein.

## 2026-03-22 - Erweiterung fuer Midpoint-Checkpointing und terminalen Cancel
- API-Contract Pflichttests: `POST /cancel` fuer erlaubte/verbotene Zustaende, tenant-scope, RBAC, idempotentes Verhalten und `resume` auf `canceled` => `409`.
- Checkpoint-Core Pflichttests: Stage+Segment Persistenz (`stage`, `stage_offset`, `payload`) und Resume-Fortsetzung ohne Doppelverarbeitung.
- Worker-Integration Pflichttests: kooperatives `pause_requested`/`cancel_requested` zwischen Segmenten und Stage-Grenzen.
- Frontend Pflichttests: Sichtbarkeit/Aktivierung der `Cancel` Action je Status sowie kein `Resume` bei `canceled`.
- Smoke-Pflichtpfade: `create -> processing -> pause -> resume(checkpoint) -> completed` und `create -> processing -> cancel -> canceled`.

## 2026-03-22 - Erweiterung fuer GPU-First Runtime + Multi-GPU Pool-Vorbereitung
- Neue Pflichttests (Step 4 / Worker Runtime):
  - Runtime-Settings: Defaults fuer `WORKER_WHISPERX_DEVICE`, `WORKER_WHISPERX_COMPUTE_TYPE`, `WORKER_WHISPERX_DEVICE_INDEX`.
  - Command-Build: WhisperX-Aufruf enthaelt `--device_index`.
  - Runtime-Fallback: `device=cuda` und nicht verfuegbare GPU fuehrt zu kontrolliertem Fallback (`cpu/int8`) mit Audit-Event.
  - Queue-Pool-Filter: Worker verarbeitet nur erlaubte Queue-Klassen (`WORKER_ALLOWED_QUEUES`).
- Deployment-Tests erweitert:
  - Compose/ENV-Artefakte pruefen GPU-First-Defaults und dedizierte Multi-GPU-Service-Definitionen.
- Regression-Gate bleibt verpflichtend:
  - Vollstaendige Python-Suite (`test_*.py`) plus Frontend-Tests (`frontend/tests/*.test.js`) bei Pipeline-/Build-/Architektur-Aenderungen.


## 2026-03-23 - Erweiterung fuer language + chunk/vad + model forcing
- Pflicht Unit-Tests: serverseitige Validation fuer language, chunk_size, vad_onset, vad_offset inkl. Negativfaelle.
- Pflicht Integrationstests: POST /api/v1/jobs persistiert language im Job-Snapshot; complete-upload merged Snapshot mit Tenant-Defaults (Job-Wert gewinnt).
- Pflicht Worker-Tests: Modell-Erzwingung auf large-v3 inkl. Audit-Event worker.runtime.model_forced.
- Pflicht Worker-Command-Tests: --chunk_size, --vad_onset, --vad_offset werden gemappt; --language nur bei Sprache != auto.
- Pflicht Frontend-Tests: Upload-Flow sendet language; Settings-Flow validiert neue Felder clientseitig.

## 2026-03-24 - Erweiterung Korrekturmodus
- Neue Pflichttests fuer Session-Lifecycle (`create/get/patch/apply/undo/redo/discard/commit`) inkl. tenant-scoping und actor-binding.
- Neue Pflichttests fuer Timeline-Invarianten im Korrekturpfad (keine Overlaps, monotone Chronologie, finite Zeitwerte, `start <= end`; Timeline-Luecken sind erlaubt).
- Neue Pflichttests fuer Suche/Ersetzen und Sprecher-Teilumteilung inklusive Abuse-Faelle (invalid char ranges, no-match replace, control-char payloads).
- Neue Pflichttests fuer Statusfuehrung (`review_status`, `is_final`) inklusive Rollenpruefung (`reviewer|admin`) und Audit-Nachweis.
- Frontend-Pflicht fuer UI-Aenderungen: Screenshot-Nachweise (`default`, `validation/error`, `responsive`) ueber `scripts/capture_correction_mode_screenshots.mjs`.

## Erweiterung 2026-03-25 - Korrekturmodus Stabilisierung
- Contract/Integration Pflicht: GET /api/v1/jobs/{id}/media-source mit Pfaden 200 (tenant-local), 404 (unknown/cross-tenant) und 503 (fehlende Quelle).
- Frontend Unit Pflicht: tabuebergreifender Handover (single-use + TTL + Cleanup).
- Frontend E2E Pflicht: Popup/New-Tab Start ohne In-Tab-Fallback; Haupttab bleibt unveraendert.
- UX Pflichttests: zentrierter Audio-Fokus, sticky Sidebar/Header/Footer, Close-Flow mit Speichern/Verwerfen/Abbrechen.
