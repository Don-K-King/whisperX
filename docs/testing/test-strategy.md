# Test Strategy (TDD) – inkl. Edge/Security-Tests pro Entwicklungsschritt

## 1) Verbindlicher Ablauf je Arbeitspaket
1. Akzeptanzkriterien + Security-Akzeptanzkriterien festlegen
2. Edge-Case-Katalog für das Paket definieren
3. Failing Tests zuerst schreiben (Red)
4. Minimal implementieren (Green)
5. Refactor ohne Verhaltensänderung
6. Security-Review + Doku-Update als DoD-Pflicht

## 2) Testebenen (für alle Schritte)
- **Unit:** Business-Regeln (Tenant-Scoping, Retention, Statuswechsel, Validatoren)
- **Integration:** API↔DB, API↔Queue, Worker↔Storage, Auth-Flow gegen Keycloak-Testumgebung
- **Contract:** API- und Event-Schema-Tests
- **E2E:** Upload → Queue → Verarbeitung → Edit → Export
- **Security/Abuse:** Negative Tests (AuthZ-Bypass, Rate-Limit-Evasion, Payload-Manipulation)

## 3) Edge-/Abuse-Testkatalog (global verpflichtend)
- **Prompt-Injection/Instruction-Injection:**
  - Transkript-/Metadateninhalte mit „ignore previous instructions“, Script-Tags, Command-Mustern dürfen keine privilegierten Aktionen auslösen.
  - Inhalte werden als Daten behandelt, nie als Steueranweisung.
- **Rate-Limiting & Abuse:**
  - Burst- und Sustained-Traffic-Tests pro Tenant/Benutzer/IP.
  - Retry-Stürme (Client + Worker) dürfen System nicht destabilisieren.
- **Unkonventionelle Eingaben:**
  - Sehr lange Dateinamen, Unicode/RTL, Nullbytes, doppelte Extensions, ungültige MIME-Header.
  - Korruptes Media, unvollständige Chunks, Out-of-order Chunks.
- **Eingabevalidierung:**
  - Schema-Validation für API-Inputs (z. B. `retention_months` Grenzen, Job-Parameter-Whitelists).
  - Path Traversal, SQLi-/NoSQLi-Muster, Header Injection, JSON Bombs.

## 4) Entwicklungsschritt-spezifische Teststrategie

### Schritt 1 – Architektur- und Governance-Festlegung
- DoR: Security- und Testanforderungen pro Komponente dokumentiert.
- Tests: Dokumentations-Qualitätschecks (Vollständigkeit, Konsistenz der Testpflichten).
- Edge-Fokus: Kein Schritt ohne definierten Edge-Testkatalog zulässig.

### Schritt 2 – Repo-/Infra-Struktur (On-Prem Docker)
- Integration: Container-Netzwerk, Secrets-Mounts, Healthchecks.
- Edge/Security:
  - Fehlkonfigurationen (offene Ports, Default-Passwörter) müssen fehlschlagen.
  - Image- und Dependency-Scans als Gate.
  - Rate-Limit-Konfiguration am Proxy automatisiert testen.

### Schritt 3 – Auth + Upload Skeleton
- Integration/E2E:
  - OIDC Login, Tenant-Claims, Token-Expiry/Refresh-Verhalten.
  - Chunked Upload Happy Path + Abbruch/Fortsetzen.
- Edge/Security:
  - AuthZ-Bypass-Versuche (Cross-Tenant IDs, manipulierte Claims).
  - Upload-Fuzzing: MIME-Spoofing, oversized files, ungültige Chunks.
  - Rate-Limit- und Throttling-Tests gegen Upload-/Job-Endpunkte.

### Schritt 4 – Processing Pipeline (Queue + Worker + Skalierung)
- Integration:
  - Queue-Routing (gpu-long/gpu-standard/cpu-short), Retry/Backoff/DLQ.
  - Long-running Jobs (mehrstündige MP4) unter begrenzter GPU.
- Edge/Security:
  - Poison Messages, Duplicate Delivery, Worker-Restart-Recovery.
  - Prompt-Injection-artige Inhalte in Transkripten dürfen keine Systemlogik beeinflussen.
  - Tenant-Fairness unter Last (keine Starvation eines Tenants).

### Schritt 5 – Transcript Edit + Export
- E2E:
  - Versionierung, optimistic locking, Export-Erzeugung.
- Edge/Security:
  - XSS/HTML-Injection in Editoren und Exportvorschau.
  - Export-Zugriff nur im Tenant Scope.
  - Malformed Unicode/Control Characters in Transkripttexten.

### Schritt 6 – Retention, Compliance, Betriebshärtung
- Integration:
  - `EVIDOX_DEFAULT_RETENTION_MONTHS` Default und Policy-Override.
  - Löschjobs inkl. Audit-Nachweis.
- Edge/Security:
  - Manipulationsversuche an Retention-Feldern.
  - Restore-Tests mit Tenant-Konsistenzprüfung.
  - Incident-Runbook-Drills (Queue-Stau, AuthZ-Anomalien).

## 5) Regression-Gates (verbindlich)
- Vollständige Regression bei Änderungen an Pipeline, Build, Architektur, Mandantenmodell, Queueing.
- Für reine Doku-Änderungen: keine Runtime-Regression erforderlich, aber Konsistenzchecks der Doku verpflichtend.
