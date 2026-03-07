# Implementation Playbook v1 (Gate zwischen Planung und Umsetzung)

## Status und Zweck
- **Status:** Verbindlich für Phase-1-Implementierungsstart.
- **Zweck:** Dieses Dokument operationalisiert die Planung in reproduzierbare, auditierbare Entwicklungsarbeitspakete.
- **Scope:** Schritt 3 bis Schritt 6 gemäß `/Entwicklungs.md`.

## 1) Verbindliche Grundsätze für die Umsetzung
1. Architekturkonformität vor Umsetzungsgeschwindigkeit.
2. Security by Default mit expliziter Threat/Control/Test-Zuordnung.
3. TDD strikt: Red → Green → Refactor pro Arbeitspaket.
4. Tenant-Isolation ist hartes Musskriterium (`tenant_id` Pflichtkontext).
5. Reproduzierbarkeit ist Freigabekriterium (Versionen, Artefakte, Testnachweise).

## 2) Definition of Ready (DoR) – Pflichtcheckliste je Arbeitspaket
Ein Arbeitspaket darf nur gestartet werden, wenn **alle** DoR-Felder erfüllt sind.

### 2.1 Fachliche und architekturelle Klarheit
- [ ] Arbeitspaket-ID, Ziel, Scope und Nicht-Scope dokumentiert.
- [ ] Referenzen auf relevante Spezifikationen gesetzt:
  - `docs/architecture/api-spec-v1.md`
  - `docs/security/security-spec-v1.md`
  - `docs/testing/test-spec-v1.md`
- [ ] Architekturkonflikte benannt und Gegenstrategie dokumentiert.
- [ ] Kein Widerspruch zu ADR-0001/ADR-0002/ADR-0003.

### 2.2 Security- und Compliance-Klarheit
- [ ] Tenant-Scoping-Regeln pro Endpoint/Event/Datenzugriff dokumentiert.
- [ ] AuthN/AuthZ-Regeln inkl. Default-Deny konkret benannt.
- [ ] Input-Validation-Anforderungen dokumentiert (MIME, Größe, Encoding, Grenzfälle).
- [ ] Erwartete Audit-Events inkl. `tenant_id`, `actor_id`, `correlation_id` benannt.
- [ ] Retention-Auswirkung dokumentiert (`retention_months`, Lösch-/Nachweisregeln).

### 2.3 TDD-Testdesign vor Implementierung
- [ ] Akzeptanzkriterien (funktional + Security) formuliert.
- [ ] Unit-, Integration-, Contract- und Edge/Abuse-Tests spezifiziert.
- [ ] Failing Tests (Red) als erster Implementierungsschritt geplant.
- [ ] Gate-Zuordnung in `docs/testing/test-matrix.md` vorhanden.

### 2.4 Reproduzierbarkeit
- [ ] Versionsmatrix (Toolchain/Container) referenziert und gültig.
- [ ] Abhängigkeitspinning/Lockfiles für betroffene Komponenten definiert.
- [ ] Testdaten/Fixtures für deterministischen Lauf referenziert.

## 3) Definition of Done (DoD) – Pflichtcheckliste je Arbeitspaket
Ein Arbeitspaket ist nur abgeschlossen, wenn **alle** Kriterien erfüllt sind.

- [ ] Tests grün gemäß Gate-Profil des Entwicklungsschritts.
- [ ] Security-Auswirkungen bewertet, Gegenmaßnahmen implementiert und nachgewiesen.
- [ ] Threat → Control → Test Traceability vollständig.
- [ ] Dokumentation aktualisiert (mindestens betroffene Bereiche unter `/docs`).
- [ ] Architekturkonflikte adressiert; bei strategischer Abweichung: ADR erstellt/aktualisiert.
- [ ] Reproduzierbarkeitsnachweise dokumentiert (Versionen, Artefakte, Testlaufkontext).

## 4) Verbindliche Gate-Reihenfolge (CI/CD Blocking)
Diese Reihenfolge ist für Schritt 3–6 als Merge- und Release-Blocker verbindlich:
1. Lint/Static Checks/Schema-Validation
2. Unit Tests
3. Integration Tests
4. Contract Tests (API + Event)
5. Security/Abuse Tests
6. E2E und ggf. vollständige Regression (pflichtig bei Pipeline-/Build-/Architektur-/Strukturänderungen)

## 5) Work-Package-Katalog (Phase 1)

## Schritt 3 – Auth + Upload Vertical Slice

### WP-3.1 Auth Middleware + Tenant Context
- **Ziel:** Einheitliche AuthN/AuthZ-Prüfung mit Default-Deny und Tenant-Kontext.
- **Abhängigkeiten:** Schritt 3A Sign-off, Keycloak-Integrationsprofil v1.
- **Akzeptanzkriterien:**
  - Ungültige/abgelaufene Tokens führen zu `401`.
  - Rollen-/Tenant-Mismatch führt zu `403` ohne Datenleck.
- **Security-Auswirkung:** Hochkritisch (Cross-Tenant Risiko).
- **Pflichttests:** Unit (Policy), Integration (JWT/JWKS), Abuse (Claim-Manipulation/Cross-Tenant).
- **Doku-Update:** `api-spec-v1`, `security-controls`, `threat-model`, `test-spec-v1`.

### WP-3.2 Job-Create Endpoint + Upload Session
- **Ziel:** `POST /api/v1/jobs` mit Validation, Retention-Policy und Presigned-Upload-Session.
- **Abhängigkeiten:** WP-3.1.
- **Akzeptanzkriterien:**
  - Validierungsfehler für ungültige Formate/Größen/Retention.
  - Tenant-scoped Job-Erstellung inkl. Audit-Event.
- **Security-Auswirkung:** Kritisch (Input Validation, Tenant Scope).
- **Pflichttests:** Unit (Validatoren), Integration (API↔DB/Storage), Abuse (MIME/Extension-Spoofing).
- **Doku-Update:** `api-spec-v1`, `security-controls`, `test-matrix`.

### WP-3.3 Complete-Upload Idempotency + Queue Publish
- **Ziel:** `POST /jobs/{id}/complete-upload` mit genau-einmaliger fachlicher Wirkung.
- **Abhängigkeiten:** WP-3.2.
- **Akzeptanzkriterien:**
  - Wiederholte Requests mit gleichem Idempotency-Key erzeugen keinen Doppel-Queueing-Effekt.
  - Fehlerpfade sind auditierbar und liefern konsistente Statuscodes.
- **Security-Auswirkung:** Kritisch (Replay/Duplicate/State-Integrity).
- **Pflichttests:** Integration (API↔Queue), Contract (Event `job.queued`), Abuse (Replay/duplicate delivery).
- **Doku-Update:** `api-spec-v1`, `event-contracts-v1`, `test-spec-v1`.

### WP-3.4 Job-Status Endpoint
- **Ziel:** `GET /jobs/{id}` tenant-scoped inkl. Progress/Retention-Infos.
- **Abhängigkeiten:** WP-3.3.
- **Akzeptanzkriterien:**
  - Status abrufbar nur im eigenen Tenant.
  - Keine Leaks über Existenz fremder IDs.
- **Security-Auswirkung:** Kritisch (Information Disclosure).
- **Pflichttests:** Integration + E2E (Tenant-Isolation), Abuse (ID enumeration).
- **Doku-Update:** `api-spec-v1`, `test-matrix`.

## Schritt 4 – Pipeline + Queue-Skalierung

### WP-4.1 Queue Routing + Retry/DLQ Governance
- **Ziel:** Routing nach Queue-Klassen mit Retry/Backoff/DLQ-Regeln.
- **Pflichttests:** Integration + Contract + Resilience (Poison Message/Duplicate Delivery/Restart).

### WP-4.2 Worker Processing Chain (ASR/Alignment/Diarization)
- **Ziel:** Stabile Verarbeitungskette inkl. tenant-scoped Artefaktpersistenz.
- **Pflichttests:** Integration + E2E + Edge (malformed media).

### WP-4.3 Tenant-Fairness + Backpressure
- **Ziel:** Quoten/Concurrency-Limits ohne Starvation.
- **Pflichttests:** Last-/Integrationstests, Security/Abuse (Retry-Storm).

## Schritt 5 – Edit + Export

### WP-5.1 Transcript-Versionierung (Optimistic Locking)
- **Ziel:** Konfliktsichere Versionierung.
- **Pflichttests:** Unit + Integration + E2E, Edge (parallel writes).

### WP-5.2 Export Pipeline (TXT/JSON/SRT/VTT)
- **Ziel:** Sichere Exporterstellung im Tenant-Kontext.
- **Pflichttests:** Contract + Integration + Security (XSS/Injection/Unicode).

## Schritt 6 – Retention + Compliance

### WP-6.1 Retention Enforcement Job
- **Ziel:** Löschfristen technisch erzwingen mit Audit-Nachweis.
- **Pflichttests:** Unit + Integration, Abuse (Manipulation retention fields).

### WP-6.2 Restore/Konsistenzprüfung
- **Ziel:** Restore-Prozess mit Tenant-Konsistenzgarantie.
- **Pflichttests:** Integrations- und Betriebs-Drills.

## 6) Reproduzierbarkeits-Spezifikation (verbindlich)

## 6.1 Versionsmatrix (Mindestanforderung)
Die reale Ausprägung pro Umgebung wird in Environment-Files gepflegt, muss aber diese Klassen enthalten:
- Runtime: Python, Node.js
- Container: Docker Engine, Docker Compose
- Plattformdienste: PostgreSQL, RabbitMQ, MinIO, Keycloak, NGINX
- Worker Compute: CUDA/Treiber/Runtime-Kompatibilität (falls GPU genutzt)

## 6.2 Dependency- und Image-Pinning
- Container-Basisimages nur per festem Tag + Digest.
- Abhängigkeiten mit Lockfiles pinnen.
- Update-Strategie zyklisch und auditierbar dokumentieren.

## 6.3 Build Provenance
Jeder Release-Kandidat benötigt:
- Commit SHA
- Container-Digests
- Build-Zeitpunkt
- Referenz auf Dependency-/SBOM-Report

## 6.4 Deterministische Testdaten
Pflicht-Fixture-Set für reproduzierbare Gates:
- Mindestens zwei Tenants (`tenant-a`, `tenant-b`)
- Rollen (`user`, `reviewer`, `admin`)
- Gültige + ungültige Medienfälle (MIME/Chunk/Size Edge Cases)
- Erwartete Audit-Events pro Kernflow

## 7) Threat → Control → Test Mapping (Pflicht)
Kein Arbeitspaket ohne vollständige Traceability:
- Bedrohung aus `docs/security/threat-model.md`
- Gegenmaßnahme aus `docs/security/security-controls.md`
- Testfall aus `docs/testing/test-spec-v1.md` / `docs/testing/test-matrix.md`
- Audit-Nachweis (welches Event/Log den Control-Erfolg belegt)

## 8) Verantwortlichkeiten und Freigabe
- **Tech Lead/API:** Architekturkonformität, API/Event-Contracts.
- **Security Lead:** Threat/Control/Test-Konsistenz, AuthN/AuthZ-Freigabe.
- **QA/Test Lead:** Gate-Konfiguration, Nachweisführung, Regression-Entscheidung.
- **Ops Lead:** Reproduzierbarkeit, Restore-/Monitoring-/Runbook-Konsistenz.

## 9) Go-Implementation-Kriterium
Die Implementierung von Schritt 3 darf erst beginnen, wenn:
1. Schritt 3A vollständig signiert ist.
2. DoR für WP-3.1 bis WP-3.4 vollständig erfüllt ist.
3. Threat/Control/Test-Mapping für Schritt 3 vollständig dokumentiert ist.
4. Gate-Profil und reproduzierbare Testumgebung freigegeben sind.
