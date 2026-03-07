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
- Sicherheits- und Testdokumentation um verpflichtende Threat→Control→Test-Traceability sowie CI-Blocker-Gates pro Entwicklungsschritt ergänzt.
- Architektur-/Event-Spezifikation um normative Job-State-Machine und Duplikat-/Recovery-Regeln präzisiert.
