# Security Controls

## Referenz
Verbindliche Security-Spezifikation: `docs/security/security-spec-v1.md`.

## Identität & Zugriff
- OIDC JWT Validation (Signatur, `iss`, `aud`, `exp`)
- RBAC + Tenant Claims
- Default Deny bei fehlendem Tenant-Kontext
- `/api/v1/audit` nur für `admin` (tenant-lokal)

## Daten- und Mandantenschutz
- `tenant_id` in allen relevanten Tabellen und APIs
- Query-Guards und Service-Layer-Prüfungen
- Export nur innerhalb Tenant Scope
- Tenant-scoped Object Keys in MinIO

## Upload- und Verarbeitungs-Sicherheit
- Dateityp-/Signaturprüfung (MIME + Magic Bytes)
- Maximalgrößen und Ratenlimits
- Queue-Isolation durch Routing-Keys und Quoten
- Retry/Backoff/DLQ mit idempotenten Consumern

## Compliance
- Retention Default: `EVIDOX_DEFAULT_RETENTION_MONTHS`
- Validierte Retention-Range: `1..36` Monate
- Audit-Log für Erstellung, Zugriff, Export, Löschung
- Audit append-only und tenant-scope Pflicht

## Verifikationsnachweise (Testgates)
- Tenant-Isolation: Unit + Integration + E2E.
- AuthN/AuthZ: Contract + Integration.
- Upload-Härtung: Edge-/Abuse-Tests.
- Retention/Audit: Unit + Integration mit Nachweisfällen.


## Control-to-Test-Mapping (verbindlich)
- Jede sicherheitsrelevante Änderung benötigt eine Zuordnung: **Control → Testfall → Audit-Ereignis**.
- Pflicht für Schritt 3:
  - JWT- und Claim-Validierung → Auth-Abuse-Tests → `auth.denied`/`auth.accepted`
  - Tenant-Isolation im Datenzugriff → Isolationstests API/DB/Export → `access.denied`
  - Upload-Validation → Edge-Fuzzing-Tests → `upload.rejected`
  - Idempotenzschutz bei Queueing → Replay-/Duplicate-Tests → `job.queue.publish`


## Ergänzende Controls für Schritt 3A/3
- Sicheres Fehlerprofil: standardisierte Fehlerobjekte mit `error_code`/`correlation_id`, ohne sensitive Interna.
- Enumerationsschutz auf tenant-sensitiven Endpunkten (`403/404`-Verhalten gemäß API-Vertrag).
- Verifikationspflicht über Abuse-Tests gegen verbose Fehlerantworten.

## WP-3.1 Kontrollkonkretisierung (Auth Middleware + Tenant Context)
- Zentrale Policy-Funktion `authorize_request(...)` als Single-Entry für Claims-Validierung (`sub`, `tenant_id`, `roles`, `iss`, `aud`, `exp`, `iat`, `nbf`).
- Default-Deny bei fehlendem `tenant_id` oder Rollen-/Tenant-Mismatch (`403 authz.deny`).
- AuthN-Verletzungen führen konsistent zu `401` (`auth.invalid_token`/`auth.expired`).
- Korrelations-ID ist verpflichtend in Fehlern und Erfolgs-Context für Audit/Forensik.
- Missbrauchsschutz: nur erlaubte Rollen (`user`, `reviewer`, `admin`) werden akzeptiert.


## WP-3.2 Kontrollkonkretisierung (Job-Create + Upload Session)
- Input-Validation serverseitig verpflichtend: MIME-Allowlist, Größenlimit (`<= 21474836480`), Retention-Range (`1..36`), Dateinamen-Härtung.
- Tenant-Isolation in Speicherpfaden: Upload-Objektpfad strikt `tenant/<tenant_id>/<job_id>/<filename>`.
- Idempotenzschutz auf `POST /jobs` verhindert doppelte Job-Erstellung und Audit-Dubletten bei Wiederholungsrequests.
- Audit-Ereignis `job.create` wird für jeden neu erzeugten Job geschrieben (`tenant_id`, `actor_id`, `job_id`, `idempotency_key`).


## HTTP-/Infrastruktur-Adapter Controls
- HTTP-Gate `POST /api/v1/jobs` erzwingt Bearer-Token-Präsenz und delegiert Claim-Prüfung zentral an `authorize_request` (Default-Deny bleibt erhalten).
- Idempotency-Key wird als Header Pflicht gemacht; fehlender Header führt zu validierungsbasiertem Reject.
- SQLite-Adapter persistiert `tenant_id` verpflichtend in Job- und Idempotenzdaten (Isolation auf Datenebene).
- Audit-Adapter schreibt JSONL append-only mit Zeitstempel für forensische Nachvollziehbarkeit.
- Presign-Adapter signiert Upload-URLs und bindet Objektpfade strikt an Tenant/Job-Kontext.


## WP-3.3 Kontrollkonkretisierung (Complete-Upload + Queueing)
- `complete-upload` akzeptiert nur tenant-/job-konsistente `object_key`-Werte und SHA256-Prüfsummenformat.
- Cross-Tenant-Zugriffe führen zu neutralem `job.not_found` ohne Existenzleck.
- Idempotenz ist tenant-scoped verpflichtend; Payload-Mismatch führt zu Konfliktablehnung.
- Queue-Publikation erfolgt über Outbox + Dispatcher zur Absicherung gegen Persist/Publish-Teilfehler.
- Auditierbarkeit: Outbox-Event `job.queued` enthält `tenant_id`, `actor_id`, `job_id`, `queue`.


## WP-3.4 Kontrollkonkretisierung (GET Job-Status)
- Tenant-Isolation im Read-Pfad: Lookup ausschließlich über `(tenant_id, job_id)`.
- Enumerationsschutz: tenant-fremde Job-IDs liefern neutralen Not-Found-Fehler ohne Existenzdetails.
- AuthN/AuthZ-Pflicht auch für Read-Operationen bleibt aktiv (Bearer + Claim-Prüfung via zentraler Auth-Policy).
- Response-Härtung: nur vertraglich definierte Felder (`job_id`, `status`, `progress`, `retention_until`).


## WP-4.1 Kontrollkonkretisierung (Queue Routing + Retry/DLQ Governance)
- Fehlerklassifikation ist verbindlich: Retryable-Fehler triggern begrenzte Requeue-Strategie, Terminal-Fehler gehen direkt in DLQ (Poison-Message-Isolation).
- Duplicate-Delivery wird explizit abgefangen und als bereits verarbeitet markiert, um Replay-/At-least-once-Effekte sicher zu neutralisieren.
- Backoff nutzt Jitter zur Vermeidung von Retry-Stürmen und korrelierten Lastspitzen nach Broker-Störungen.
- Queue-Publish nutzt stabile `message_id` je Outbox-Event für deduplizierbare Zustellung und forensische Nachvollziehbarkeit.
- Monitoring-Pflicht: Queue-Lag, Retry- und DLQ-Metriken werden für Security/Operations-Audits erhoben.


## WP-4.2/4.3 Kontrollkonkretisierung (Worker Chain + Fairness/Backpressure)
- Worker verarbeitet nur erlaubte Quellzustände (`queued`, `failed_retryable`) und tenant-scoped `object_key`-Präfixe; Scope-Verletzungen werden terminal beendet.
- Fehlerklassifikation minimiert Fehlstrategien: transient (`failed_retryable`) vs. irreparabel (`failed_terminal`) wird explizit getrennt.
- Tenant-Fairness-Policy begrenzt gleichzeitige Verarbeitung global und pro Tenant zur Vermeidung von Ressourcen-Monopolisierung (DoS-Risiko).
- Worker-Audit-Events (`start`, `completed`, `failed`) sind verpflichtend für forensische Nachvollziehbarkeit.


## WP-5.1/5.2 Kontrollkonkretisierung (Transcript-Edit + Export)
- Optimistic Locking erzwingt konsistente Parallel-Edits (`base_version`), Konflikte werden ohne stilles Überschreiben abgewiesen.
- Segmenttexte werden auf unzulässige Steuerzeichen geprüft; missbräuchliche Inhalte werden abgelehnt.
- Export-Format ist strikt allowlisted (`txt|json|srt|vtt`); unbekannte Formate werden geblockt.
- Textbasierte Exportformate behandeln Transcript-Inhalte als Daten (Escaping), um XSS-/Markup-Injection zu erschweren.
- Tenant-scoped Transcript-Lookup vor Export verhindert Cross-Tenant-Datenabfluss.


## WP-6.1 Kontrollkonkretisierung (Retention Enforcement)
- Retention-Resolver validiert Eingabewerte strikt (Integer-Pflicht) und begrenzt auf globale Min/Max-Werte, um manipulierte Fristen zu neutralisieren.
- Löschpfad ist tenant-scoped verpflichtend (`tenant_id` + `job_id`), Candidate- und Execution-Query ohne Tenant-Kontext sind unzulässig.
- Clock-Skew-Toleranz reduziert Risiko verfrühter Löschung bei Zeitdrift zwischen Worker und Datenquelle.
- Jede Entscheidung/Ausführung wird auditiert (`retention.decision`, `retention.execution`, `retention.execution.failed`) zur forensischen Nachvollziehbarkeit.
- Teilfehler werden explizit als Sicherheits-/Betriebsrisiko behandelt und dürfen nicht stillschweigend als Erfolg markiert werden.


## WP-6.2 Kontrollkonkretisierung (Restore + Recovery)
- Restore akzeptiert ausschließlich tenant-konsistente Requests (`tenant_id`-Match zum Auth-Context).
- Wiederherzustellende Objektpfade müssen strikt tenant-präfixiert sein (`tenant/<tenant_id>/...`).
- Post-Restore-Konsistenzprüfung ist verpflichtend; fehlende Job-Referenzen in Transcript/Export/Audit gelten als Blocker für Freigabe.
- Scheduler-Recovery behandelt Teilfehler klassenbasiert und idempotent; unbegrenzte Blind-Retries sind verboten.
- Restore- und Recovery-Aktionen sind auditpflichtig und müssen forensisch zeitlich korreliert werden können.


## 2026-03-08 – Controls für Retention-Scheduler-Lease und Recovery-Idempotenz
- **Control: Lease-Kollision verhindern.** Scheduler-Run wird nur ausgeführt, wenn Lease fällig und Lock frei/owning ist (`lock_until` + `lock_owner`), sonst Default-Deny.
- **Control: Idempotenz pro Failure-Klasse.** Retry-Queue erzwingt Eindeutigkeit über `(failure_id, failure_class)`, um Mehrfachausführung bei Duplikaten zu unterbinden.
- **Control: Tenant-Kontext im Recovery-Pfad.** Jeder Retry-Datensatz enthält `tenant_id`; Monitoring/Audit-Auswertungen müssen tenant-scoped erfolgen.
- **Control: Manipulationsresistenz.** Ungültige/inkonsistente Retry-Einträge (z. B. negative Attempts, leere IDs) werden nicht ausgeführt.


## 2026-03-08 – Ergänzung: Quarantäne für ungültige Retry-Datensätze
- **Control: Invalid-Quarantine statt Success-Marking.** Ungültige Retry-Einträge werden als `invalid` mit `invalid_reason` markiert und nicht als `recovered` verbucht.
- **Control: Lease-Heartbeat.** Längere Scheduler-Läufe erneuern das Lease periodisch, um parallele Ausführung bei TTL-Expiry zu verhindern.


## 2026-03-08 – Runtime-Config Controls (Retention-Scheduler)
- **Control: Fail-fast Runtime-Konfiguration.** Scheduler-Start wird bei fehlenden/inkonsistenten Parametern abgebrochen (kein stilles Weiterlaufen).
- **Control: Heartbeat/TTL-Konsistenz.** `heartbeat_seconds < lease_ttl_seconds` ist verpflichtend, um Lease-Race-Risiken zu minimieren.
- **Control: Eindeutiger Lock-Owner.** Jede Instanz muss einen expliziten `lock_owner` setzen; anonyme Defaults sind untersagt.

## 2026-03-08 – Runtime-Sicherheitskontrollen für Retention-Runner-Bootstrap
- **Control: Fail-fast Bootstrap-Validierung.** Runner-Start wird bei fehlenden Pflicht-ENVs (`RETENTION_TENANT_IDS`, `RETENTION_AUDIT_LOG_PATH`, `RETENTION_OBJECT_STORAGE_ROOT`) und inkonsistenten Policy-Grenzen sofort abgebrochen.
- **Control: Nicht-sensitive Structured Logging.** Start-/Shutdown-/Tick-Logs enthalten ausschließlich operative Nicht-Secret-Felder.
- **Control: Path-Traversal-Schutz bei lokaler Objektlöschung.** Löschpfade werden gegen den konfigurierten Storage-Root aufgelöst; Pfade außerhalb des Roots werden abgewiesen.
- **Control: Fail-safe Recovery-Semantik.** Unbekannte Retry-Failure-Klassen gelten als nicht recoverbar und werden nicht fälschlich als erfolgreich markiert.

## 2026-03-08 – Controls für S3/MinIO-Adapter und Recovery-Governance
- **Control: Backend-spezifische Pflichtvalidierung.** Storage-Backend (`filesystem|s3`) erzwingt jeweils vollständige Pflichtparameter (fail-fast).
- **Control: Prefix-Delete-Semantik backend-konsistent.** Sowohl Filesystem- als auch S3-Adapter akzeptieren nur sichere tenant-präfixierte Schlüssel; Traversal-/Prefix-Manipulation wird verworfen.
- **Control: Versionierte Recovery-Governance.** Recovery-Failure-Klassen werden über Mapping-Version (`v1`) kontrolliert und nicht implizit erweitert.
- **Control: Unknown-Class Fail-Safe.** Unbekannte Failure-Klassen führen zu Warnsignal und verbleiben im Retry-Backlog.
- **Control: Preflight als Deployment-Guard.** `RETENTION_VALIDATE_ENV_ONLY=true` muss vor Start in Pipeline/Init-Checks ausgeführt werden.
