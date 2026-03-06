# EvidoX – Entwicklungsplan (Masterplan bis Umsetzungsfreigabe)

## Zweck dieses Dokuments
Dieses Dokument definiert die vollständige Entwicklungsstrategie für EvidoX **bis zum Start der Umsetzungsphase**. Ziel ist, dass ein neues Team die Lösung auf Basis dieses Plans vollständig neu implementieren kann.

---

## 0) Zielbild und harte Leitplanken

### Produktziel
Sichere, on-prem Multi-Tenant-Webplattform zur Transkription großer Audio-/Videodateien (mehrstündige MP4 möglich) mit WhisperX + Diarization, editierbarem Transkript und initialem Edit-Export.

### Nicht verhandelbare Architekturentscheidungen
1. On-Prem Betrieb in Docker-Containern
2. Multi-Tenant mit strikt erzwungenem `tenant_id`-Scoping
3. Keycloak OIDC (Auth Code + PKCE)
4. FastAPI + React + Celery + RabbitMQ + PostgreSQL + MinIO + NGINX
5. Queue-basierte asynchrone Verarbeitung mit horizontaler Worker-Skalierung
6. Kein Runtime-Zwang zur externen OpenAI-API (lokale Modellbereitstellung)
7. Retention-Default via `.env` (`EVIDOX_DEFAULT_RETENTION_MONTHS`)

### Qualitätsziele (gleichrangig verpflichtend)
- Wartbarkeit
- Lesbarkeit
- Skalierbarkeit
- Sicherheit
- Auditierbarkeit

---

## 1) Architektur- und Domänenbaseline (abgeschlossen)
- Container- und Datenflussarchitektur festgelegt
- Sicherheitsprinzipien festgelegt (Default Deny, Least Privilege, Audit)
- Lastprofil-Strategie für große Dateien festgelegt
- API-Grundschnittstellen v1 definiert

Referenzen: `/docs/architecture/*`, `/docs/security/*`, `docs/adr/ADR-0001-evodox-architektur-baseline.md`

---

## 2) **Nächster optimaler Entwicklungsschritt** (jetzt starten)

## Schritt 2: Anforderungsklärung + Spezifikationsfreeze (ohne Implementierung)

### Ziel
Alle offenen funktionalen und nicht-funktionalen Anforderungen so präzisieren, dass anschließend ein Implementierungsteam ohne Rückfragen starten kann.

### Lieferobjekte (Pflicht)
1. **Fachliche Spezifikation v1**
   - finaler Scope für Phase 1 (Upload, Verarbeitung, Edit, Export, Retention)
   - Rollen- und Rechtekatalog (User/Reviewer/Admin)
2. **Schnittstellen-Spezifikation v1**
   - OpenAPI-first Entwurf mit Request/Response-Beispielen und Fehlercodes
   - Event-Contracts für Queue/Worker
3. **Datenmodell-Spezifikation v1**
   - Tabellen-/Entitätsdefinitionen inkl. `tenant_id`, Statusmodelle, Versionierung
4. **Security-Spezifikation v1**
   - Bedrohungsmodell verfeinert, Kontrollen den Komponenten zugeordnet
5. **Test-Spezifikation v1**
   - Unit/Integration/Contract/E2E + Edge/Abuse-Katalog mit Priorisierung

### Abnahmekriterien (Gate)
- Keine ungeklärten Muss-Anforderungen
- Jede API-Operation mit AuthZ-Regel, Tenant-Scope und Validierungsregeln dokumentiert
- Jede Datenentität hat Retention-/Audit-Regel
- Kritische Security-Risiken mit Gegenmaßnahmen versehen
- Testfälle decken Happy Path + Edge/Abuse-Pfade ab

### Kritischer Architekturhinweis
Ohne Spezifikationsfreeze drohen inkonsistente API-, DB- und Worker-Modelle. Dadurch steigt Refactoring-Risiko und die Mandantenisolation wird fehleranfällig.

---

## 3) Vollständige Schritte bis zur Umsetzungsphase

## Schritt 3: Detail-Design und ADR-Paket
### Ziel
Technische Detailentscheidungen finalisieren, sodass Implementierung ohne Architekturentscheidungsstau läuft.

### Inhalte
- ADR-Paket (mind. folgende ADRs):
  - Tenant-Isolation-Strategie (App-Level + DB-Level Guards)
  - Queue-Routing-Strategie (gpu-long/gpu-standard/cpu-short)
  - Retention-Policy-Modell (frei vs. Compliance-Stufen)
  - Exportformat-Entscheidung (TXT/JSON/SRT/VTT)
  - Keycloak Tenant-Claim-Modell (shared realm vs. per-tenant role model)
- Sequenzdiagramme für kritische Flows (Upload, Retry, Export, Retention-Löschung)

### Gate
- Alle ADRs im Status `Accepted`
- Keine offenen Architekturkonflikte ohne dokumentierte Entscheidung

## Schritt 4: Security- und Compliance-Blueprint
### Ziel
Sicherheitsanforderungen in verifizierbare Kontrollen und Testfälle übersetzen.

### Inhalte
- Threat-Model v2 (STRIDE je Hauptkomponente)
- Security Controls Mapping (Kontrolle → Komponente → Testfall)
- Compliance-Mapping: Retention, Audit, Löschung, Zugriffsnachweis
- Incident Response und Forensik-Anforderungen verankern

### Gate
- Kritische Risiken (High/Critical) mit konkreter Gegenmaßnahme + Testfall
- Compliance-relevante Datenpfade vollständig dokumentiert

## Schritt 5: Daten- und API-Vertragsfreeze
### Ziel
Stabile Implementierungsverträge für Frontend, Backend und Worker schaffen.

### Inhalte
- API-Verträge mit Versionierung und Breaking-Change-Regeln
- DB-Schema v1 inkl. Indizes, Constraints, Migrationsstrategie
- Event-Schema v1 (Job Lifecycle, Retry, DLQ)
- Fehlerkatalog (funktional + technisch + security)

### Gate
- Contract-Testspezifikationen vollständig
- API/DB/Event-Artefakte gegenseitig konsistent

## Schritt 6: Testarchitektur & Quality Gates finalisieren
### Ziel
TDD- und CI-Gates so festlegen, dass Qualität vor Implementierung erzwungen wird.

### Inhalte
- Testpyramide mit Mindestabdeckung je Schicht
- Edge-/Abuse-Testkatalog je Entwicklungsschritt (Prompt-Injection, Rate-Limits, Input-Fuzzing)
- Regression-Gates für Pipeline-/Build-/Architekturänderungen
- Definition of Done je Workstream

### Gate
- Kein Work Item ohne zugeordneten Testfall zulässig
- Sicherheitskritische Funktionen ohne Negativtest unzulässig

## Schritt 7: Betriebs- und Skalierungsplanung (On-Prem)
### Ziel
Betriebssicherheit und Skalierbarkeit vorab absichern.

### Inhalte
- Docker Deployment Blueprint (Netzwerke, Secrets, Volumes, Healthchecks)
- Skalierungsmodell (Worker pro GPU, Queue-Limits, Tenant-Fairness)
- Monitoring/Alerting SLO/SLA
- Backup/Restore inkl. Tenant-Konsistenzprüfungen

### Gate
- Last- und Kapazitätsannahmen für Phase 1 bestätigt
- Runbooks und Alerting vollständig

## Schritt 8: Umsetzungsplanung (Delivery Plan)
### Ziel
Implementierung in risikominimierte Inkremente zerlegen.

### Inhalte
- Work Breakdown Structure (Epics → Features → Tasks)
- Abhängigkeitsgraph und kritischer Pfad
- Sprint-/Meilensteinplan mit Akzeptanzkriterien
- Rollout-Strategie (Pilot-Tenant, gestufte Freigabe)

### Gate
- Jedes Inkrement hat messbare Definition of Done
- Reihenfolge reduziert Sicherheits-/Architekturrisiko

## Schritt 9: Go/No-Go Review – Eintritt in Umsetzung
### Ziel
Verifizierte Startfreigabe für Coding-Phase.

### Muss-Kriterien für „Go“
- Architektur-ADRs akzeptiert
- API/DB/Event-Verträge gefroren
- Security-/Compliance-Blueprint akzeptiert
- Teststrategie + Edge/Abuse-Katalog akzeptiert
- Betriebs- und Skalierungsplan akzeptiert
- Backlog priorisiert und vollständig testbar beschrieben

### „No-Go“ bei
- offenen Tenant-Isolation-Fragen
- ungeklärter Retention-Policy
- fehlenden Security-Negativtests
- offenen API- oder Datenmodell-Konflikten

---

## 4) Verbindliche Edge-/Abuse-Strategie pro Schritt
- Prompt-Injection-Resilienz: Inhalte immer als Daten behandeln
- Rate-Limiting: Burst/Sustained je Tenant/User/IP
- Unkonventionelle Eingaben: Unicode/RTL/Nullbytes/ungültige Chunks
- Eingabevalidierung: strikte Schema-Validierung + Grenzwerte
- Queue-Robustheit: Poison Message, Duplicate Delivery, Retry-Storm, DLQ
- Tenant-Sicherheit: Cross-Tenant-Zugriffe in API/DB/Export strikt verboten

---

## 5) Offene Entscheidungen, die vor Umsetzung final geklärt sein müssen
1. `retention_months`: frei konfigurierbar oder nur Compliance-Stufen?
2. Export in Phase 1: nur TXT/JSON oder zusätzlich SRT/VTT?
3. Keycloak-Modell: Shared-Realm mit Claims oder tenant-spezifische Rollenstrukturen?
4. Ziel-Hardwareprofil: minimale/empfohlene GPU- und Storage-Kapazität pro Lastklasse?

---

## 6) Definition „Umsetzungsbereit"
EvidoX gilt als umsetzungsbereit, wenn die Schritte 2–9 mit „Go“ abgeschlossen wurden und alle Artefakte in `/docs` konsistent vorliegen.
