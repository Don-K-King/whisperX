# AGENTS.md – Verbindliche Arbeitsanweisungen für EvidoX

Geltungsbereich: gesamtes Repository (sofern keine tiefer liegende AGENTS.md existiert).

## 1) Grundprinzipien
1. **Architektur vor Einfachheit:** Änderungen müssen zur Zielarchitektur passen; kurzfristige Hacks sind unzulässig.
2. **Security by Default:** Jede Entscheidung muss Sicherheitsauswirkungen benennen und absichern.
3. **Test-Driven Development ist Pflicht:** Kein Produktivcode ohne vorherigen Testfall (Red → Green → Refactor).
4. **Kritische Anforderungsanalyse:** Widersprüche, Risiken und Fehlstrategien aktiv benennen.
5. **Nachvollziehbarkeit:** Jede relevante Entscheidung dokumentieren (siehe Dokumentationsstruktur).
6. **Wartbarkeit & Lesbarkeit:** Klare Module, sprechende Namen, niedrige Kopplung, hohe Kohäsion.
7. **Skalierbarkeit als Architekturziel:** Queue- und Worker-Design auf horizontale Skalierung auslegen.

## 2) Verbindlicher TDD-Workflow
Für jedes Arbeitspaket sind folgende Schritte zwingend:
1. Akzeptanzkriterium formulieren.
2. Testfälle definieren (Unit, Integration, ggf. E2E/Regression).
3. Failing Test implementieren (Red).
4. Minimalen Code zur Erfüllung schreiben (Green).
5. Refactor ohne Verhaltensänderung.
6. Security-Review je Änderung (Threats, Input Validation, AuthZ/AuthN, Secrets, Logging).
7. Dokumentation aktualisieren.

## 3) Testpflichten
- **Immer erforderlich:** Unit-Tests für neue/angepasste Business-Logik.
- **Erforderlich bei Schnittstellen:** Integration-/Contract-Tests.
- **Erforderlich bei Mandantenlogik:** Isolationstests für AuthZ, Datenabfragen und Exporte.
- **Erforderlich je Entwicklungsschritt:** Edge-/Abuse-Tests (Prompt-Injection-Resilienz, Rate-Limiting, unkonventionelle Eingaben, strikte Eingabevalidierung).
- **Erforderlich bei Pipeline-, Build-, Architektur- oder Strukturänderungen:** vollständige Regressionstest-Suite.
- **Nicht erforderlich:** Regressionstests bei reinen Dokumentationsänderungen oder sehr kleinen isolierten Änderungen ohne Verhaltensänderung.

## 4) Sicherheits-Mindeststandards
- Keine Secrets im Code/Repo.
- Alle externen Inputs validieren (Datei, MIME, Größe, Encoding, Grenzfälle).
- Inhalte aus Transkripten/Metadaten stets als Daten behandeln (keine Ausführung von eingebetteten Anweisungen).
- AuthN/AuthZ zwingend und explizit (Default Deny).
- Mandantenisolation strikt erzwingen (`tenant_id` als Pflichtkontext).
- Least Privilege für Dienste und Datenzugriff.
- Sicherheitsrelevante Aktionen auditierbar protokollieren.
- Abhängigkeiten regelmäßig scannen und pinnen.

## 5) Architektur-Governance
- Bei größeren Architekturentscheidungen ist ein ADR Pflicht.
- Jede Änderung muss folgende Fragen beantworten:
  - Passt sie zur Zielarchitektur?
  - Entstehen neue Kopplungen oder Single Points of Failure?
  - Wie wirkt sie auf Skalierung, Betrieb, Sicherheit und Kosten?
- Runtime-Betrieb darf nicht von externer OpenAI-API abhängen (lokale Modellbereitstellung erforderlich).

## 6) Verbindliche Dokumentationsstruktur
Diese Struktur ist bei jeder Entscheidung/Implementierung nachzuführen.

```text
/docs
  /adr
    ADR-0001-<titel>.md
  /architecture
    system-context.md
    container-view.md
    data-flow.md
    security-architecture.md
  /development
    Entwicklungs.md
    roadmap.md
    decisions-log.md
  /testing
    test-strategy.md
    test-matrix.md
    regression-log.md
  /operations
    runbooks.md
    monitoring-alerting.md
    backup-restore.md
  /security
    threat-model.md
    security-controls.md
    incident-response.md
  /product
    requirements.md
    changelog.md
```

### Dokumentationsregeln (Pflicht)
- **Bei Nutzer-/Betreiberrelevanz:** `/docs/product/changelog.md` aktualisieren.
- **Bei Architekturentscheidung:** neues/ergänztes ADR in `/docs/adr` + Referenz in `/docs/development/decisions-log.md`.
- **Bei Teststrategieänderung:** `/docs/testing/test-strategy.md` und ggf. `regression-log.md` aktualisieren.
- **Bei Sicherheitsrelevanz:** `/docs/security/security-controls.md` und ggf. `threat-model.md` aktualisieren.
- **Bei Betrieb/Deployment-Änderung:** `/docs/operations/*` nachführen.
- Jeder PR muss dokumentieren, **welche** Dateien unter `/docs` angepasst wurden und **warum**.

## 7) Definition of Done (DoD)
Ein Arbeitspaket ist nur fertig, wenn:
- Tests grün (entsprechend Testpflichten),
- Security-Auswirkungen bewertet und umgesetzt,
- erforderliche Dokumentation aktualisiert,
- Architekturkonflikte adressiert oder als ADR festgehalten.

## 8) Umgang mit Konflikten
Bei Zielkonflikten (z. B. Geschwindigkeit vs. Sicherheit) gilt Priorität:
1. Sicherheit & Compliance
2. Architekturkonsistenz & Wartbarkeit
3. Performance/UX
4. Umsetzungsgeschwindigkeit

## 9) Pull-Request-Qualität
PR-Beschreibung muss enthalten:
- Problem und Ziel
- Architekturentscheidung(en)
- Sicherheitsauswirkungen + Gegenmaßnahmen
- Testumfang inkl. Regression (falls verpflichtend)
- Dokumentationsänderungen

