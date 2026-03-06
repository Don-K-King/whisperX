# EvidoX – Entwicklungsplan (lebendes Dokument)

## Zielbild
EvidoX wird als sichere, skalierbare Webplattform zur Upload-basierten Transkription großer Audio- und Videodateien aufgebaut. Die Plattform nutzt **WhisperX** für ASR + Alignment sowie **Speaker-Diarization** (Stimmallokation), erzeugt ein editierbares Transkript und stellt revisionssichere Job-/Ergebnisdaten bereit.

**Leitprinzipien**
- Architektur vor Einfachheit (langfristig wartbar, modular, klar trennbare Verantwortlichkeiten)
- Security by Design (Zero-Trust zwischen Komponenten, Least Privilege, Auditierbarkeit)
- Test-Driven Development (TDD) in allen Umsetzungsschritten
- Dokumentationspflicht bei jeder Nutzer-/Betriebsrelevanz
- Wartbarkeit, Lesbarkeit und Skalierbarkeit als Primärziele

---

## Entwicklungsschritt 1 (festgelegt): Vollständige Zielarchitektur

## 1) Festgelegte Kernentscheidungen
- **Mandantenmodell:** Multi-Tenant (Logical Tenant Isolation in gemeinsamer Plattform).
- **Betrieb:** On-Premise in Docker-Containern.
- **Authentifizierung/Benutzerverwaltung:** Keycloak via OIDC Authorization Code + PKCE.
- **Verarbeitung:** Queue-basierte asynchrone Pipeline mit paralleler, hardwareabhängiger Skalierung.
- **Model-Abhängigkeit:** Kein Runtime-Zwang zur OpenAI-API; Modelle werden initial geladen/gespiegelt und anschließend lokal betrieben.
- **Output in Phase 1:** Editierbares Transkript + initialer Edit-Export.
- **Löschfristen:** Standardwert in `.env` in Monaten; pro Job/Transkript im Frontend sichtbar und mitgeführt.

### Multi-Tenant – Konsequenzen (kurz)
Multi-Tenant reduziert Betriebsaufwand gegenüber getrennten Einzelinstanzen und verbessert Ressourcenauslastung (GPU, Storage, Queue). Gleichzeitig steigen Anforderungen an strikte Mandantenisolation in AuthZ, Datenmodell, Logs, Caches und Exportpfaden. Fehler in Tenant-Scoping führen sonst zu kritischen Datenlecks. Deshalb werden Tenant-ID und Zugriffsprüfung systemweit als Pflichtfelder behandelt (DB-Schema, API-Filter, Queue-Metadaten, Audit).

## 2) Zielarchitektur (Container-/Service-Sicht)

### Frontend (React + TypeScript + Vite)
- OIDC-Login, Job-Upload, Status, Transcript-Editor, Export.
- Anzeige und Übergabe von `retention_months` pro Job/Transcript.
- Mandantenbezogene UI-Kontexte (Tenant Scope aus Token/Claims).

### API Backend (FastAPI)
- Token-Validierung (JWKS, issuer/audience), RBAC + Tenant-Autorisierung.
- Endpunkte für Upload-Session, Job-Lifecycle, Transcript-Versionierung, Export.
- Standard-Löschfrist aus ENV, überschreibbar nach Policy:
  - `EVIDOX_DEFAULT_RETENTION_MONTHS=12` (Beispiel).
- Presigned-Uploads (direkt in Object Storage), Audit Events append-only.

### Processing Worker (Python, Celery + RabbitMQ)
- Pipeline: Ingest → Audio-Extraktion → WhisperX → Alignment → Diarization → Postprocessing.
- Ausführung parallelisierbar über Worker-Prozesse und Worker-Instanzen.
- GPU-spezifische Queues für schwere Jobs, CPU-Queue für leichte Aufgaben.
- Modellzugriff lokal (Model Cache/Repository), kein externer API-Zwang zur Laufzeit.

### Message Broker / Queue (RabbitMQ, verbindlich)
- Durable Queues, Acknowledgements, Retry/Backoff, Dead Letter Queue.
- Routing nach Job-Klasse (z. B. `gpu-long`, `gpu-standard`, `cpu-short`).
- Tenant-fair Scheduling durch Quoten/Concurrency-Limits pro Tenant.

### Datenbank (PostgreSQL)
- Mandantenfähiges Schema mit `tenant_id` als Pflichtattribut in allen fachlichen Entitäten.
- Job-/Transcript-/Audit-Metadaten, Versionen, Retention-Attribute.

### Objekt-Storage (MinIO, S3-kompatibel)
- Rohuploads + Artefakte (JSON, TXT, SRT, VTT, Edit-Export).
- Serverseitige Verschlüsselung, Bucket-Policies pro Tenant-Prefix.

### IAM (Keycloak)
- Realm, Rollen, Gruppen, optionale MFA.
- Tenant-/Rollenclaims in Tokens; API erzwingt Claim-basierte Autorisierung.

### Reverse Proxy / Edge (NGINX)
- TLS, Security Headers, Request Limits, Body-Size-/Timeout-Profile für große Uploads.
- Routing für Frontend/API, optional WAF-Regeln.

## 3) Lastprofil- und Skalierungsstrategie (große MP4, mehrere Stunden)
**Anforderung:** Sehr große Dateien, lange Laufzeiten, variable Hardware.

**Strategie (best fit zur Zielarchitektur):**
1. **Direct-to-Object-Storage Uploads** (Chunked/Resumable), um API-Timeouts zu vermeiden.
2. **Asynchrone Job-Queue** mit RabbitMQ + dedizierten Queue-Klassen (lang/schwer vs. kurz/leicht).
3. **Horizontale Worker-Skalierung** per zusätzlicher Container-Instanzen (je nach verfügbarer GPU/CPU).
4. **Ressourcenbewusste Parallelität**:
   - pro GPU begrenzte parallele Jobs (Memory-Schutz),
   - pro Tenant faire Limits gegen Starvation.
5. **Backpressure & Priorisierung**:
   - Queue-Lag-Monitoring,
   - dynamische Concurrency, Retry mit Exponential Backoff,
   - DLQ für Fehleranalyse.
6. **Artefaktorientierte Persistenz**: Zwischenschritte optional persistieren für Recovery nach Worker-Ausfall.

## 4) API-Schnittstellen (v1, erweitert)
- `POST /api/v1/jobs` – Job + Upload vorbereiten (inkl. `retention_months`/Tenant-Kontext)
- `POST /api/v1/jobs/{id}/complete-upload` – Upload finalisieren, Queueing
- `GET /api/v1/jobs/{id}` – Status, Progress, Retention-Info
- `GET /api/v1/jobs/{id}/transcript` – aktuelle Version
- `PUT /api/v1/jobs/{id}/transcript` – editierte Version (optimistic locking)
- `POST /api/v1/jobs/{id}/export` – initialer Edit-Export
- `GET /api/v1/jobs` – mandantengefilterte Liste
- `GET /api/v1/audit` – nur Admin/Compliance

## 5) Sicherheitsstandards (verpflichtend)
- Tenant-Isolation als harte Sicherheitsanforderung (AuthZ + Data Access + Logs).
- OIDC Best Practices, TLS 1.2+, strikte CORS/CSP/Security Header.
- Upload-Härtung: MIME+Magic-Bytes, Maximalgröße, Malware-Scan-Hook, Quarantäne-Pfad.
- Least Privilege für API/Worker/Storage/DB-Servicekonten.
- Verschlüsselung at-rest (DB + Object Storage) und in-transit.
- Audit-Events unveränderbar, inklusive Tenant-Kontext.
- Löschfristen technisch erzwungen (Retention Job + Nachweis im Audit).

## 6) TDD- und Teststrategie (verbindlich)
- Erst Testspezifikation, dann Implementierung (Red-Green-Refactor).
- Pflichttests für Architekturthemen:
  - Tenant-Isolation Tests (API + DB + Export)
  - Retention-Regeltests (Default aus ENV + Überschreibung nach Policy)
  - Queue/Retry/DLQ Tests
  - Large-File Integrationstests (resumable upload, long-running jobs)
- Regressionstests verpflichtend bei Pipeline-/Build-/Architekturänderungen.


## 6a) Edge-Teststrategie pro Entwicklungsschritt (verbindlich)
- **Schritt 1 (Architektur):** Edge-/Abuse-Testkatalog muss pro Komponente definiert sein.
- **Schritt 2 (Infra):** Proxy/Rate-Limits, Container-Hardening, Secret-Handling und Fehlkonfigurations-Tests.
- **Schritt 3 (Auth+Upload):** Cross-Tenant/AuthZ-Bypass-Tests, Eingabevalidierung, Upload-Fuzzing (MIME/Chunks/Größe).
- **Schritt 4 (Pipeline):** Poison-Message, Duplicate-Delivery, Worker-Restarts, Queue-Backpressure, Tenant-Fairness.
- **Schritt 5 (Edit+Export):** XSS/Injection, unkonventionelle Unicode-Eingaben, Export-AuthZ.
- **Schritt 6 (Retention/Compliance):** Retention-Manipulation, Löschnachweis im Audit, Restore-Konsistenztests.
- **Prompt-Injection-resilienz:** Inhalte aus Transcript/Metadaten werden immer als Daten behandelt, nie als Systemanweisung.

## 7) Risiken / Architekturkonflikte und Gegenmaßnahmen
- **Konflikt:** Multi-Tenant vs. Datenisolation.
  - **Gegenmaßnahme:** Tenant-Scopes in jedem Zugriffspfad + Security-Tests.
- **Konflikt:** Maximaler Durchsatz vs. GPU-Stabilität.
  - **Gegenmaßnahme:** GPU-bound concurrency + adaptive Scheduling.
- **Konflikt:** Große Uploads vs. Proxy/API-Limits.
  - **Gegenmaßnahme:** Direct upload + dedizierte Timeout/Profile.
- **Konflikt:** Externe Modellabhängigkeit vs. On-Prem-Verfügbarkeit.
  - **Gegenmaßnahme:** Lokales Model-Mirroring und versionierter Modellcache.

## 8) Offene Punkte mit Nutzerentscheidung
1. Darf `retention_months` durch Nutzer frei gesetzt werden oder nur in vordefinierten Compliance-Stufen?
2. Soll initialer Edit-Export nur TXT/JSON oder zusätzlich SRT/VTT enthalten?
3. Benötigt jeder Tenant eigene Keycloak-Gruppen/Rollen oder genügt Claim-basiertes Shared-Realm-Modell?
