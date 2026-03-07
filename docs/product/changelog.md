# Changelog

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
- Sicherheits- und Testdokumentation um verpflichtende Threat→Control→Test-Traceability sowie CI-Blocker-Gates pro Entwicklungsschritt ergänzt.
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
