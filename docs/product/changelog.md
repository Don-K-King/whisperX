# Changelog

## 2026-03-26
- Frontend-Proxy gehaertet: Nginx nutzt jetzt Docker-DNS-Resolver (127.0.0.11) mit dynamischem API-Upstream, damit /api nach API-Container-Recreate automatisch wieder auf die neue Ziel-IP zeigt.
- Fehlerbild 502 Bad Gateway nach API-Neustart behoben (kein persistentes Stale-Upstream-Mapping mehr im Frontend-Proxy).
- Korrekturmodus zeigt und speichert Draft-Segmente wieder als Rohbloecke (keine implizite Zusammenfuehrung gleicher Speaker beim Laden/Speichern).
- Manuelle Speaker-Zuweisungen im Korrekturmodus behalten Rohblock-Grenzen bei; Segmentgrenzen werden nicht automatisch zusammengezogen.
- Export bleibt davon entkoppelt: fuer bessere Lesbarkeit kann weiterhin die kompakte Ausgabe verwendet werden.
- Korrekturmodus Timeline-Fix umgesetzt: Session-Start uebernimmt Segment-Zeitstempel (start/end) jetzt unveraendert aus der Transcript-Version.
- Seed-Kompaktierung fuer Timeline-Luecken entfernt; Drift gegenueber der Original-Videotimeline wird dadurch nicht mehr kumulativ vergroessert.
- Korrektur-Validierung angepasst: Luecken sind im Korrekturpfad zulaessig, Overlaps bleiben verboten; ungueltige Zeitwerte (NaN/inf/negativ) werden abgewiesen.
- Korrektur-Workspace merged Speaker-Bloecke nur noch bei kontiguierlichen Segmenten; Pausen bleiben als echte Timeline-Luecken erhalten.
- Medien-Sync im Workspace gehaertet: bei Seek in internen Luecken wird kein falscher vorheriger Block mehr als aktiv markiert.

## 2026-03-25
- Korrekturmodus-Start gegen Legacy-Runtime-DB stabilisiert: Session-Erstellung ist jetzt schema-kompatibel, auch wenn alte transcript_correction_sessions noch expires_at NOT NULL erzwingen.
- 404/500-Fehlerbild beim Start des Korrekturmodus im Docker-Zielbetrieb beseitigt; Session-Start (POST /api/v1/jobs/{id}/transcript/correction-sessions) liefert wieder erfolgreich 200.
- Korrektur-Startfluss gehaertet: tabuebergreifender Handover (single-use + TTL) statt sessionStorage-Bindung, damit neue Tabs/Fenster stabil bootstrappen.
- Korrekturmodus startet jetzt ausschliesslich in neuem Tab/Fenster; In-Tab-Fallback wurde entfernt.
- Neue API GET /api/v1/jobs/{id}/media-source eingefuehrt; Workspace laedt Audio/Video automatisch ohne manuelle Dateiauswahl.
- UX verbessert: Sidebar/Topbar/Audioleiste fixiert, nur Editor scrollt; Audio-Fokus wird im Editor zentriert; Schliessen-Flow mit Speichern | Verwerfen | Abbrechen hinzugefuegt.
- Korrekturmodus uebernimmt jetzt konsolidierte Sprecherbloecke (konsekutive gleiche Speaker) inkl. zusammengefuehrter Zeitfenster.

## 2026-03-23
- Speaker-Diarization im Docker-Zielbetrieb stabilisiert: Legacy-Modell pyannote/speaker-diarization wird auf pyannote/speaker-diarization-community-1 normalisiert.
- Worker-Defaults und Deploy-Compose-Defaults auf pyannote/speaker-diarization-community-1 angehoben, um diarization_fallback mit UNKNOWN-Only-Transkripten zu vermeiden.
- Ops-Dokumentation und Beispiel-ENV-Profile auf das Community-Modell aktualisiert.

## 2026-03-22
- Task View zeigt Transcript jetzt in lesbaren Speaker-Bloecken statt als lange Liste einzelner Mikrosegmente.
- Speaker koennen pro Transcript-Version persistent umbenannt werden, z. B. `SPEAKER_01` -> `Patrick`.
- Speaker-Alias-Updates sind tenant-scoped, versioniert und mit Optimistic Locking abgesichert.
- Export und UI nutzen denselben versionierten Alias-Snapshot, damit Anzeige und Nachvollziehbarkeit zusammenpassen.
- Neue Admin-Funktion im Frontend/API: tenant-spezifische, persistente Decoding-Settings fuer WhisperX (`GET/PUT /api/v1/admin/transcription-settings`).
- Neue Persistenz eingefuehrt: `tenant_transcription_settings` fuer Tenant-Defaults und `jobs.transcription_options_json` fuer reproduzierbare Job-Snapshots.
- Queueing/Resume erweitert: `job.queued` Events tragen jetzt `transcription_options`; Resumes verwenden denselben Snapshot statt aktueller Laufzeitwerte.
- Worker-CLI-Wiring erweitert: Whitelist-Decoding-Parameter werden in den WhisperX-Aufruf gemappt (inkl. defensiver Fallbacks auf sichere Defaults).
- Security-Haertung: strikte Feld-Whitelist mit Range-Validation; Audit-Events fuer Settings-Read/Update ohne Klartext-`initial_prompt` (nur Hash/Laenge).
- Frontend um Admin-Route "Transcription Settings" erweitert (Laden, Validieren, Speichern inkl. Fehlerdarstellung).
- Lokales Queue-Routing auf GPU-First verschaerft: `audio/*` und `video/*` werden bei `complete-upload` auf `gpu-standard` geroutet.
- Betriebsrunbook ergaenzt: expliziter Stopp lokaler Zusatz-Worker (`worker-cpu`, `worker-gpu-*`) nach Tests mit `--profile multi-gpu`, damit im Local-PC-Betrieb nur der GPU-First-Worker aktiv ist.
- Betriebsdokumentation korrigiert: Runbook-API-Beispiele auf den lokalen Frontend-Proxy (`http://localhost:18081/api/...`) aktualisiert, damit Checks dem Compose-Zielbetrieb entsprechen.
- GPU-Verifikation im Runbook gehaertet: Device-Nachweis erfolgt ueber Container-ENV + CUDA-Runtime-Check + Audit-Fallback-Event (`worker.runtime.gpu_fallback`) statt ausschliesslich ueber unstrukturierte Log-Strings.
- Neues Incident-Runbook dokumentiert: Diagnose und Behebung fuer Dashboard-Fehlerbild `unknown_error` bei Frontend-Proxy/API-Upstream-Problemen.
- Monitoring/Alerting ergaenzt um Frontend-Proxy-5xx- und Upstream-Connect-Fehler, die im UI als `unknown_error` sichtbar werden.
- Job-Lifecycle stabilisiert: `DELETE /api/v1/jobs/{id}` ist jetzt als Force-Soft-Delete fuer alle nicht bereits geloeschten Status verfuegbar (inkl. `upload_pending`, `queued`, `processing`, `pause_requested`, `cancel_requested`, `paused`).
- Delete ist idempotent (`deleted` bleibt `deleted`) und setzt konsistent `status=deleted`, `progress=100`; Nutzer koennen damit auch haengende Test-/Sample-Jobs entfernen.
- Delete prune't pending Outbox-Events und entfernt interne Checkpoint-/Artefakt-/Transcript-Reste auf Job-Ebene, sodass kein Re-Queue aus Altzustand mehr erfolgt.
- Worker-Timeout-Policy angepasst: `WORKER_WHISPERX_TIMEOUT_SECONDS=0` bedeutet kein hartes Subprocess-Timeout fuer lange ASR-Laeufe.
- Worker-Robustheit verschaerft: generische Exceptions gehen nicht mehr in Retry-Schleifen, sondern in terminale Behandlung (DLQ + `failed_terminal`), ausser bei explizit retryable Fehlerpfaden.
- Laufende WhisperX-Prozesse reagieren jetzt kooperativ auf `pause_requested`, `cancel_requested` und `deleted` (graceful terminate, dann kill fallback), damit Pause/Resume/Cancel/Delete auch bei langen Jobs verlässlich greifen.
- Midpoint-Checkpointing eingefuehrt: Worker persistiert Stage+Segment-Checkpoint (`downloaded`, `asr_started`, `asr_done`, `diarization_done`) und setzt bei Resume ab letztem Segment fort.
- Neuer terminaler Cancel-Endpunkt eingefuehrt: `POST /api/v1/jobs/{id}/cancel`.
- Statusmodell erweitert um `cancel_requested -> canceled`; `resume` auf `canceled` liefert konsistent `409 job.resume.invalid_state`.
- Outbox/Runner priorisieren Cancel gegenueber Retry-Fortsetzung, damit nach Abbruch keine weitere Verarbeitung fortlaeuft.
- Frontend-Job-Detail erweitert um `Cancel` fuer aktive/pausierte Jobs; `Resume` ist bei `canceled` nicht mehr verfuegbar.
- Timeline/Progress zeigen terminalen `canceled`-Pfad; interne Teiltranskripte bleiben weiterhin nicht im UI sichtbar.
- Lokaler Runtime-Vertical-Slice fuer Docker ergaenzt: API startet jetzt ueber ENV-basierte Factory (evodox.runtime.api_app:create_app) ohne manuelles DI im Startkommando.
- Hybrid-Auth fuer lokale Inkremente eingefuehrt (API_AUTH_MODE=oidc|dev) bei beibehaltenem Claim-Validierungspfad.
- API um fehlende Frontend-Endpunkte erweitert: tenant-scoped GET /api/v1/jobs und admin-scoped GET /api/v1/audit.
- complete-upload persistiert jetzt Worker-relevante Metadaten (upload_session_id, object_key, checksum_sha256) im Job-Datensatz.
- Dedizierter Stub-Worker-Runner ergaenzt (evodox.runtime.worker_runner) fuer deterministische lokale Verarbeitung queued -> processing -> completed.
- Compose-Zielbetrieb auf neue Runtime-Entrypoints umgestellt und gemeinsames Runtime-Volume fuer SQLite/Audit hinzugefuegt.
- Lokales Runtime-Image fuer den Docker-Slice ergaenzt (`deploy/Dockerfile.runtime`) und Compose-Runtime-Kommandos auf `python -m ...` vereinheitlicht.
- Testabdeckung erweitert: Runtime-Entrypoints, neue API-Endpunkte, Worker-Runner sowie lokaler Smoke-Flow (FastAPI-abhaengig).
- Status jetzt: Docker-Vertical-Slice ist lokal lauffaehig und per E2E geprueft; offen sind Transcript-API, Frontend-Upload mit Presigned-Flow und Anzeige von Transcript/Speaker-Diarization.
- Naechster TDD-Schritt fuer das Frontend: testbarer Presigned-Upload-Orchestrator (`create job -> presigned PUT -> complete-upload`) mit gruenen Frontend- und Runtime-Tests.
- Zielpfad danach: WhisperX-Worker als echte Live-Transcription mit Speaker-Diarization im selben Docker-Vertikal-Slice.
- Frontend ist jetzt im Target-Compose als eigener Service verfuegbar und lokal ueber `http://localhost:18081` erreichbar (inkl. `/api` Proxy zur API).
- Worker-Runtime auf `WORKER_MODE=whisperx` erweitert (echter Media-Download + WhisperX-CLI-Ausfuehrung im Docker-Container).
- Lokaler Upload-Pfad fuer Browser lauffaehig gemacht (`API_UPLOAD_BASE_URL=http://localhost:19000`, MinIO-Port `19000:9000`, Bucket-Init fuer `uploads`).
- Docker-Runtime-Image haertet Live-Betrieb mit `ffmpeg` + installierten WhisperX-Abhaengigkeiten.
- Diarization-Fallback eingefuehrt: falls gated HF-Diarization fehlschlaegt, wird Transkription trotzdem ohne Diarization abgeschlossen (Status bleibt `completed`).
- Lokaler E2E-Nachweis erfolgt: Job-Upload via Presigned PUT, Worker-Verarbeitung und Transcript-Abruf erfolgreich getestet.

## 2026-03-06
- Architektur präzisiert: Multi-Tenant, On-Prem Docker, RabbitMQ/Celery Skalierungsstrategie, lokale Modellbereitstellung.
- Produktanforderung ergänzt: Löschfristen im Frontend/Job-Kontext, Default per ENV in Monaten.
- Produktumfang Phase 1 klargestellt: initialer Edit-Export.
- Teststrategie erweitert: verpflichtende Edge-/Abuse-Tests pro Entwicklungsschritt (Prompt-Injection-Resilienz, Rate-Limiting, unkonventionelle Eingaben, Eingabevalidierung).
- Spezifikationsfreeze v1 hinzugefügt: fachliche Spezifikation, API- und Event-Contracts, Datenmodell, Security-Spezifikation und Test-Spezifikation als verbindliche Umsetzungsbasis.
- Entwicklungsplan aktualisiert: nächster optimaler Schritt ist der TDD-Implementierungsstart „Auth + Upload Vertical Slice“.
- Entwicklungsdokumentation bereinigt: `/Entwicklungs.md` als Single Point of Truth festgelegt; `/docs/development/Entwicklungs.md` enthält nur noch Referenz- und Contract-Check-Hinweise.
- Planungspräzisierung vor Realisierung: kein separates Frontend-Primärdokument, stattdessen verpflichtender Frontend/API-Contract-Check gegen API-, Security- und Test-Spezifikation v1.


## 2026-03-07
- Entwicklungsplanung um verbindliches Implementation Playbook v1 erweitert (DoR/DoD, Work-Packages, Gate-Reihenfolge, Reproduzierbarkeitsnachweise).
- Implementierungsstart Schritt 3 (WP-3.1): zentrales Auth-/Tenant-Context-Modul mit Default-Deny, Rollen-Whitelist und normierten `401/403`-Fehlercodes inkl. `correlation_id` ergänzt.
- Sicherheits- und Testdokumentation um verpflichtende Threat?Control?Test-Traceability sowie CI-Blocker-Gates pro Entwicklungsschritt ergänzt.
- Architektur-/Event-Spezifikation um normative Job-State-Machine und Duplikat-/Recovery-Regeln präzisiert.

## 2026-03-07
- Frontend/UI-Spezifikation v1 für Phase 1 ergänzt (`docs/product/frontend-ui-spec-v1.md`) mit verbindlichen Entscheidungen zu Branding, Light/Dark, Karten-Dashboard, Upload-UX, i18n-Readiness und Admin-Audit-Ansicht.
- Entwicklungsplan-Referenzen aktualisiert, damit die neue Frontend-Umsetzungsspezifikation formal eingebunden ist.
- Governance aktualisiert: Für UI/Design-Änderungen sind in der Realisierungsphase verpflichtende Screenshots im PR nachzuweisen.

## 2026-03-07
- Gap-Analyse und priorisierte Blocker-Liste dokumentiert, um Architektur-/Security-Risiken (Tenant-Leak, AuthZ-Drift, Contract-Drift) vor Implementierungsbeginn zu schließen.

- Schritt-3 Vorbereitungsdokumente auf technische Arbeitsreferenzen ohne formale Gate-Entscheidungen umgestellt.

- Implementierungsfortschritt Schritt 3 (WP-3.2): Job-Erstellung mit serverseitiger Upload-Validierung, tenant-scope Upload-Session, Audit-Eventing und Idempotenzschutz umgesetzt.

- Betreiberrelevante Erweiterung: HTTP-Adapter für Job-Erstellung sowie produktive Persistenz-/Audit-/Presign-Adapter (SQLite/JSONL/signierte Upload-URLs) ergänzt.

- Implementierungsfortschritt Schritt 3 (WP-3.3): `complete-upload` mit idempotentem Queueing, tenant-scoped Objektprüfung und Outbox-basierter Publish-Strategie ergänzt.

- Implementierungsfortschritt Schritt 3 (WP-3.4): tenant-sicherer Job-Statusabruf (`GET /jobs/{id}`) mit Progress- und Retention-Information ergänzt.

## 2026-03-08
- Implementierungsfortschritt Schritt 4 (WP-4.1): Outbox-Dispatcher um RabbitMQ-Publisher-Adapter, Retry/Backoff mit Jitter, DLQ-Routing und Duplicate-Delivery-Handling erweitert.
- Betreiberrelevante Monitoring-Erweiterung: Metrik-Hooks für Queue-Lag, Retry-Rate, DLQ-Count und Duplicate-Events in der Queue-Dispatch-Pipeline ergänzt.

- Implementierungsfortschritt Schritt 4 (WP-4.2/WP-4.3): Worker-Processing-Chain (ASR/Alignment/Diarization) mit tenant-scoped Artefaktpersistenz sowie Tenant-Fairness/Backpressure-Policy ergänzt.

- Implementierungsfortschritt Schritt 5 (WP-5.1/WP-5.2): Transkript-Versionierung mit Optimistic Locking und sichere Export-Pipeline (`txt|json|srt|vtt`) im Tenant-Kontext ergänzt.


## 2026-03-08
- Schritt 6.1 umgesetzt: Retention Enforcement Job eingeführt (Policy-Resolver + periodischer Löschlauf) inkl. Audit-Events pro Entscheidung und Ausführung.
- Sicherheitsrelevante Härtung: tenant-scoped Löschqueries, Clock-Skew-Schutz gegen verfrühte Löschung und Teilfehler-Nachweis bei Storage/DB-Inkonsistenzen.
- Infrastruktur erweitert: SQLite-Retention-Candidate/Execution-Adapter mit Anonymisierung (`filename` redacted, Status `deleted`) und tenant-spezifischem Outbox-Pruning.


## 2026-03-08
- Schritt 6.2 umgesetzt: tenant-sicherer Restore-Workflow mit fester Restore-Reihenfolge und automatischer Konsistenzprüfung (`Job?Transcript?Export?Audit`) eingeführt.
- Betriebsrelevante Härtung: periodischer Retention-Scheduler mit idempotentem Retry-Recovery-Pfad für Teilfehlerklassen ergänzt.
- Sicherheitsrelevante Absicherung: Restore-Guards gegen Cross-Tenant-Scopes und verpflichtende Restore-Audit-Events (`restore.started`, `restore.completed`) ergänzt.


## 2026-03-08
- Retention-Scheduler läuft produktiv jetzt mit persistentem SQLite-Lease statt In-Memory-Zustand; Scheduler-Intervall und Recovery-Fortschritt bleiben über Prozessneustarts erhalten.
- Retry-Recovery-Queue ist persistent und idempotent pro `failure_id + failure_class`; Duplikate lösen keine Mehrfachausführung mehr aus.
- Betriebsseitig wurden neue Monitoring-/Alerting-Anforderungen für Lease-Stale und Recovery-Backlog eingeführt.


## 2026-03-08
- Ungültige/manipulierte Retention-Retry-Datensätze werden nun explizit als `invalid` quarantänisiert (statt implizit als `recovered`).
- Für lange Scheduler-Läufe wurde ein Lease-Heartbeat ergänzt, um konkurrierende Parallel-Ausführung bei Lease-Expiry zu vermeiden.


## 2026-03-08
- E2E-Testabdeckung für den Kern-Lifecycle ergänzt (`create_job` ? `complete_upload` ? Outbox-Dispatch ? Statusabruf) und ein Status-Gap behoben: `complete_upload` akzeptiert jetzt auch frisch erzeugte Jobs im Zustand `upload_pending` (ohne Queue-/Tenant-Sicherheitsregeln zu lockern).
- Retention-Scheduler verfügt jetzt über ein verbindliches Runtime-Startprofil mit fail-fast Konfigurationsvalidierung (DB-Pfad, Lock-Owner, Intervall, TTL/Heartbeat).
- Der produktive Startpfad verdrahtet den Scheduler explizit auf persistente SQLite-Adapter und vermeidet implizite In-Memory-Fallbacks.

## 2026-03-08 – Betreiberupdate: Dedizierter Retention-Scheduler-Prozess
- Neu: Retention-Scheduler wird als dedizierter Runner-Prozess betrieben statt als eingebettete Nebenfunktion.
- Auswirkungen für Betrieb:
  - eigener Startpfad mit fail-fast Konfigurationschecks,
  - strukturierte Start-/Tick-/Shutdown-Logs,
  - kontrollierter Graceful-Shutdown via `SIGTERM`/`SIGINT`.
- Erwarteter Nutzen: klare Verantwortlichkeit, bessere Skalierbarkeit und geringere Kopplung zwischen API-Lifecycle und Retention-Lifecycle.

## 2026-03-08 – Betriebsupdate: produktiver Runner-Bootstrap vervollständigt
- Der dedizierte Retention-Runner besitzt nun einen ausführbaren Entrypoint (`python -m evodox.runtime.retention_scheduler_runner`) mit produktivem Dependency-Wiring.
- Neu sind fail-fast Bootstrap-Checks für Tenant-Liste, Audit-Log-Pfad, Storage-Root und Retention-Policy-Grenzen.
- Recovery-Pfad wurde für bekannte Teilfehlerklassen (`storage_delete_failed`, `db_mark_failed`) konkretisiert; unbekannte Klassen bleiben fail-safe im Retry.

## 2026-03-08 – Betreiberupdate: S3/MinIO-Backend + Recovery-Governance + Preflight
- Retention-Runner unterstützt jetzt neben lokalem Filesystem ein dediziertes `s3`-Backend (MinIO-kompatibel) mit gleicher Prefix-Delete-Semantik.
- Recovery-Failure-Klassen werden versioniert über `RETENTION_RECOVERY_MAPPING_VERSION` gesteuert (aktuell `v1`).
- Neuer Betriebsmodus zur Deployment-Härtung: `RETENTION_VALIDATE_ENV_ONLY=true` validiert Pflicht-ENVs vor Runner-Start.
- Neue vollständige Konfigurationsvorlage: `.env.example`.





## 2026-03-22
- Lifecycle-Controls im API/Frontend umgesetzt: `pause`, `resume`, `delete` fuer Jobs mit tenant-scope und konsistentem Fehlerprofil.
- Neue API-Endpunkte: `POST /api/v1/jobs/{id}/pause`, `POST /api/v1/jobs/{id}/resume`, `DELETE /api/v1/jobs/{id}`.
- Worker-Pipeline erweitert um kooperatives Pausieren (`pause_requested -> paused`) und Milestone-Progress-Updates.
- Worker-Runner erweitert um Retry-Limit fuer retryable Fehler mit terminalem Abschluss nach Exhaustion.
- Progress-Fallbacks in Backend + Frontend harmonisiert (Milestones: `5/20/60/90/100`).
- Job-Loeschung als Soft-Delete umgesetzt inkl. Pending-Outbox-Pruning und Audit-Eintrag.
- Frontend erweitert um Upload-Fortschrittsanzeige, statusabhaengige Action-Buttons und Polling mit 429-Backoff (5s bis 30s).
- Testabdeckung ausgebaut: neue API-Contract-, Lifecycle-, Worker- und Frontend-Tests fuer diesen Schritt.

## 2026-03-22
- GPU-First Worker-Default eingefuehrt: lokale Runtime nutzt standardmaessig `WORKER_WHISPERX_DEVICE=cuda` und `WORKER_WHISPERX_COMPUTE_TYPE=float16`.
- Runtime-Haertung: Worker fuehrt beim Start einen GPU-Preflight aus und faellt bei CUDA-Problemen kontrolliert auf `cpu/int8` zurueck.
- Auditierbarkeit erweitert: GPU-Fallback wird als `worker.runtime.gpu_fallback` im Worker-Audit protokolliert.
- Multi-GPU-Vorbereitung umgesetzt: neuer Parameter `WORKER_WHISPERX_DEVICE_INDEX` wird an WhisperX CLI (`--device_index`) uebergeben.
- Pool-Vorbereitung fuer spaetere Server-Skalierung umgesetzt: `WORKER_ALLOWED_QUEUES` und queue-basiertes Outbox-Filtering.
- Deployment-Artefakte erweitert: Compose bietet zusaetzlich `worker-cpu`, `worker-gpu-0`, `worker-gpu-1` (Profile `multi-gpu`) mit dediziertem GPU-Pinning.
- `.env`, `.env.example` und `.env.production.example` auf GPU-First-Defaults aktualisiert.



## 2026-03-23 - WhisperX large-v3 Erzwingung + Sprachwahl + Chunk/VAD
- Worker erzwingt im WhisperX-Mode das Modell large-v3 unabhaengig von WORKER_WHISPERX_MODEL; Abweichungen werden als worker.runtime.model_forced auditiert.
- POST /api/v1/jobs akzeptiert jetzt language (de default, auto|en|fr|es|it erlaubt); Sprache wird im Job-Snapshot gespeichert und bei Queueing/Worker genutzt.
- Worker setzt --language nur wenn Sprache ungleich auto ist.
- Tenant-Admin Transcription-Settings wurden um chunk_size, vad_onset, vad_offset erweitert; serverseitige Validation und CLI-Wiring (--chunk_size, --vad_onset, --vad_offset) sind aktiv.
- Rueckwaertskompatibilitaet: Jobs/Settings ohne neue Felder laufen weiterhin ueber sichere Defaults.

## 2026-03-24
- Neuer Korrekturmodus eingefuehrt: dedizierter Workspace mit Session-basiertem Draft (`create/get/patch/apply/undo/redo/discard/commit`).
- Transcript-Status erweitert: `review_status` und `is_final` ueber neuen API-Pfad `PATCH /api/v1/jobs/{id}/transcript/status`.
- Timeline-Schutz verschaerft: Korrektur-Operationen blockieren Overlaps/Luecken und invaliden Segmentzuschnitt.
- Segment-IDs im Transcript-Output stabilisiert; fehlende IDs werden deterministisch normalisiert.
- Frontend erweitert: Korrekturmodus kann aus Job-Detail in eigenem Fenster geoeffnet werden.
- Neuer Korrektur-Workspace: Fliesstext-Bearbeitung, Suche/Ersetzen, Sprecher-Umteilung, Undo/Redo, Verwerfen, Draft-Speichern, Commit, Audio-Mitfuehrung.
- Testabdeckung erweitert um Correction-Service/Store/HTTP-Mapping sowie neue Frontend-Utils fuer Korrekturmodus.
- Screenshot-Automation fuer Korrekturmodus hinzugefuegt (`scripts/capture_correction_mode_screenshots.mjs`).


## 2026-03-25
- Korrekturmodus-Sidebar als aufklappbarer Baum umgesetzt (Status, Suche/Ersetzen, Sprecherumteilung, Aenderungslog).
- Offene/geschlossene Baumknoten werden nun pro Nutzer lokal persistent gespeichert.
- Sidebar-Layout entkoppelt: eigener Scrollbereich verhindert Ueberdeckung mit Audio-Footer bei langen Menues.
- Frontend-Viewmodel-Tests fuer Sidebar-Baumzustand/Persistenz erweitert.
- Pflicht-Screenshots fuer Korrekturmodus nach UI-Aenderung aktualisiert (Default, Validierung, Responsive).

## 2026-03-25
- Korrekturmodus Sprecherumteilung erweitert: Block auswaehlen, Text im Block markieren und direkt als anderen Sprecher anwenden.
- Segment-Split bei Sprecherumteilung validiert: Zeitstempel werden proportional zu den Textteilen aufgeteilt (links/mittel/rechts).
- Sprecherumteilungs-UI vereinfacht (ohne manuelle Start/End-Char-Eingabe), inklusive Markierungs-Feedback im Sidebar-Panel.

## 2026-03-25
- Markierte Textpassagen im Korrekturmodus bleiben bei Sidebar-Interaktionen (z.B. Sprecherauswahl/Statusklicks) erhalten; Aufhebung nur durch neue gueltige Markierung im Transkript oder Segmentwechsel nach Datenaenderung.
- Beim Auswaehlen/Fokussieren eines Transcript-Blocks springt Audio/Video automatisch auf den Block-Startzeitpunkt (ohne Autoplay), sodass direkt mit Play gestartet werden kann.

## 2026-03-25
- Korrekturmodus Audio-Text-Sync gehaertet: Beim manuellen Seeken (Slider/seeked/metadata) wird der aktive Transcript-Block jetzt sofort aktualisiert, auch im Pause-Zustand.
- Klick/Fokus auf einen Transcript-Block setzt die aktive Blockmarkierung deterministisch und springt Medien auf Segmentstart, ohne doppelte Markierung auf vorherigem Block.
- Segmentgrenzen explizit abgesichert: Boundary-Mapping bleibt konsistent in beide Richtungen (Text->Media, Media->Text).

## 2026-03-25
- Hybrid-Seek im Korrekturmodus umgesetzt: automatischer Sprung auf Blockstart nur noch bei echtem Blockwechsel, kein Ruecksprung mehr bei Refokus/Edit im selben Block.
- Pro Transcript-Block wurde ein expliziter Jump-Button (keyboard-accessible) ergaenzt, um gezielt auf den Blockstart im Media zu springen.
- Media->Text-Sync bei Slider/Seek gestaerkt: beim Seeken wird der passende Block weiterhin automatisch aktiv und zusaetzlich als Auswahl uebernommen.

## 2026-03-25
- Bedienbarkeit im Korrekturmodus verbessert: Nach Sprecherzuweisung bleibt der Editor im bearbeiteten Bereich; Scrollposition und Segmentkontext werden nach Rendern wiederhergestellt.
- Neue Header-Option Auto-Sprung Media eingefuehrt (persistiert): automatischer Sprung auf Blockstart kann aktiviert/deaktiviert werden.
- Header-Layout neu gegliedert (Meta, Aktionen, Optionen) sowie konsistentes Button-Styling mit dezentem Hover-/Active-Effekt umgesetzt.

## 2026-03-25
- Korrekturmodus-Editor passt Textblockhoehen jetzt automatisch an den Inhalt an; interne Scrollbalken in den Bloecken entfallen.
- Neue Exportfunktion direkt im Korrekturmodus: Download als Markdown (.md), PDF (.pdf) und Word-kompatibel (.doc/RTF).
- Header-Layout weiter gegliedert und Export-Aktionen integriert, inklusive konsistenter dezent hervorgehobener Action-Buttons.

## 2026-03-26 - Legacy-Reseed gegen additive Timeline-Drift
- Korrekturmodus-Session-Start akzeptiert jetzt optional `force_reseed_from_transcript` und kann damit bei Legacy-Session-Resume den Draft auf aktuelle Transcript-Segmente (absolute Timeline) zuruecksetzen.
- Legacy-Resume-Fall wird fix-forward behandelt: `history[0]` wird reseeded, `history_index` auf `0` gesetzt und Drift aus historisch kompaktierter Draft-Historie entfernt.
- End-Pause-Verhalten im Workspace gehaertet: fuer `currentTime > lastEnd` wird kein aktiver Block mehr markiert.

## 2026-03-26 (Korrektur-Export Lesbarkeit)
- Korrektur-Workspace Export erweitert: neuer Modus `compact|raw` (Default `compact`) ohne Backend-API-Aenderung.
- Kompaktmodus nutzt Dashboard-Semantik (konsekutive gleiche Speaker werden zusammengefuehrt, Speakerwechsel bleiben getrennt).
- Zeitachsenpraezision bleibt erhalten: kompakte Bloecke behalten absolute `start/end` Grenzen (keine Timeline-Kompaktierung).
- Exportlayout vereinheitlicht: Speaker + Zeitrange in einer Zeile, Text darunter; Header mit Job-/Session-/Versions-Metadaten und UTC-Exportzeitpunkt.


## 2026-03-26 (Korrekturmodus Seed-Overlap Hotfix)
- Fehlerbehebung fuer `transcript.timeline_overlap` beim Start des Korrekturmodus: kleine Rundungs-Ueberlappungen in bestehenden Transcript-Zeitstempeln werden beim Session-Seed automatisch auf den vorherigen Segment-Endpunkt gesnappt (50ms Toleranz).
- Strikte Safety bleibt erhalten: groessere Overlaps werden weiterhin mit `transcript.timeline_overlap` abgewiesen.
- Zukuenftige Erstmaterialisierung aus Worker-Artefakten haertet die Timeline ebenfalls gegen kleine Rundungs-Ueberlappungen.

## 2026-03-26 (Korrekturmodus UI-Modernisierung)
- Korrekturmodus-Header modernisiert: neues 3-Zonen-Layout (Meta, Hauptaktionen, Utility-Toggles) mit klarerer visueller Hierarchie und kompakter Sticky-Darstellung.
- Export im Header auf Icon + Dropdown-Submenue umgestellt (Drucken, Markdown, PDF, Word) inkl. integrierter Exportmodus-Wahl `Kompakt|Rohdaten`.
- Header-Toggles auf Aktiv/Inaktiv-Pills umgebaut (Autosave, Auto-Sprung, Sidebar, Theme) mit `aria-pressed` fuer verbesserte Tastatur-/Screenreader-Bedienung.
- Segmentkarten im Korrekturmodus erhalten eine stabile, sehr dezente Speaker-Farbkodierung (deterministisch pro Speaker-Key, neutraler UNKNOWN-Fallback) fuer bessere visuelle Zuordnung.
- UI-Feinschliff fuer Lesbarkeit und Orientierung: ruhigeres Spacing, konsistente Button-/Chip-Proportionen, praezisere Hover-/Fokus-Zustaende und verbesserte Responsive-Umbrueche.

## 2026-03-26 (Korrekturmodus UI-Feinschliff: Header + Media-Stabilitaet)
- Header-Container im Korrekturmodus auf abgerundete Kanten umgestellt und visuell an die uebrigen Grids angeglichen.
- Header-Buttons vereinheitlicht (konsistente Hoehe/Breitenlogik pro Button-Gruppe) fuer ein ruhigeres, modernes Gesamtbild.
- Light-Mode-Farbkonzept fuer Buttons geschaerft: alle Buttons heben sich klarer von der Flaeche ab, inklusive konsistenter Hover-Zustaende.
- Speaker-spezifische Blockeinfaerbung im Transcript dezent verstaerkt (leichter Tint + subtile farbige Akzentkante pro Sprecher).
- Media-Playback bleibt bei UI-Aktionen erhalten (Zeitposition, Play/Pause, Rate, Lautstaerke), sodass Header-/Status-Aktionen das laufende Medium nicht mehr resetten.
- Sidebar-Baum startet jetzt standardmaessig eingeklappt; initial sind nur die Menuepunkte sichtbar.

## 2026-03-26 (Korrekturmodus Header-Kompaktlayout + Icon-Toolbar)
- Header im Korrekturmodus stark verdichtet (ca. halbierte vertikale Flaeche) und von 3-Spalten-Layout auf platzsparende Toolbar-Anordnung umgestellt.
- Aktionen neu geordnet: kompakte Action-Cluster mit Icon-Buttons fuer Speichern, Drucken, Undo und Redo; Tooltip-Texte liefern die Bezeichnung im Hover.
- Export-Menue als platzsparender Icon-Trigger umgesetzt; Utility-Toggles auf kurze Labels in kompakter Reihe reduziert.
- Header-Buttons in Groesse/Abstand vereinheitlicht, damit ein konsistentes und modernes Bedienbild entsteht.

## 2026-03-26 (Header-Reflow + Statuszeile + Toggle-Farbsemantik)
- Korrekturmodus-Header auf 2 Bereiche umgebaut: oben vollbreite Aktionsleiste, unten kompakte Statuszeile (`Job`, `B`, `W`, `Review`, `Final`).
- Beschriftung `Korrekturmodus` im Header entfernt; Statusinfos in eigene Footer-Zeile des Headers verschoben.
- Aktionsleiste nutzt jetzt die volle Breite mit kompakter Toolbar-Anordnung (Main- und State-Controls).
- `Autosave` und `Auto-Sprung` haben explizite Aktiv/Inaktiv-Farbsemantik: aktiv gruen, inaktiv leicht rot.
- Sprecher-Blockfarben deutlich verstaerkt (kraeftigere Palette + staerkerer Rahmen-/Akzentkontrast) fuer klarere visuelle Unterscheidung.

## 2026-03-26 (Block-Fokus Hervorhebung)
- Fokusdarstellung der Transcript-Bloecke deutlich verstaerkt: aktive/selektierte Bloecke erhalten klarere Akzentfarbe, staerkere Outline und sichtbareren Left-Accent.
- Kombinierter Zustand `active + selected` wurde explizit gehaertet, damit der aktuelle Media-Block waehrend Playback eindeutig erkennbar bleibt.

## 2026-03-27
- Korrekturmodus zeigt beim Oeffnen jetzt sofort einen Bootstrap-Ladebildschirm statt eines leeren Tabs.
- Neues Feedback im Ladezustand: Titel Transcript mit Media wird geladen, Spinner sowie sichtbare Processing-Schritte (Arbeitsbereich, Media, Transcript, Session).
- Ladefehler im Bootstrap-Pfad werden im selben Screen angezeigt und koennen direkt per Erneut versuchen erneut gestartet werden.
