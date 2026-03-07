# Decisions Log

## 2026-03-06
- ADR-0001 angenommen: On-Prem Multi-Tenant Architektur mit RabbitMQ/Celery Pipeline, lokaler Modellbereitstellung und Retention-Konzept.
- Konsequenz: Alle neuen API-/DB-/Export-Pfade müssen `tenant_id`-gescoped umgesetzt und getestet werden.
- Konsequenz: Retention-Felder und Frontend-Anzeige sind Pflicht für Nutzer-/Compliance-Transparenz.
- Ergänzung: Edge-/Abuse-Teststrategie ist je Entwicklungsschritt verpflichtend (u. a. Prompt-Injection-Resilienz, Rate-Limiting, Input-Validation, ungewöhnliche Eingaben).

- ADR-0002 angenommen: Phase-1 Spezifikationsfreeze mit verbindlichen Fach-, API-, Event-, Datenmodell-, Security- und Test-Spezifikationen.
- Konsequenz: Implementierungsstart nur über Vertical Slice `Auth + Upload` mit TDD- und Security-Gates.


## 2026-03-07
- ADR-0003 angenommen: Verbindliches Implementation Playbook v1 als Gate zwischen Spezifikationsphase und Implementierung.
- Konsequenz: Schritt 3 startet nur bei vollständig erfüllter Definition of Ready (DoR) je Work Package.
- Konsequenz: Threat→Control→Test-Traceability sowie reproduzierbare Build-/Test-Nachweise sind verpflichtende Freigabekriterien.
- Frontend-Stack für Phase 1 festgelegt: React + TypeScript + Vite als architekturkonforme Umsetzungslinie.
- Konsequenz: UI-Spezifikation in `docs/product/frontend-ui-spec-v1.md` als ergänzende Umsetzungsspezifikation eingeführt; API/Security/Test-v1 bleiben führende Primärreferenzen.
- Governance ergänzt: Screenshot-Pflicht für UI/Design-Änderungen in `AGENTS.md` als DoD-relevantes PR-Kriterium verankert.



## 2026-03-07
- Schritt-3 Arbeitsdokumente auf neutrale technische Referenzen ohne formale Gate-/Freigabeentscheidungen umgestellt.
- Personenbezogene Sign-off-Einträge aus den Keycloak-Integrationsvorlagen entfernt; Fokus auf technische Parameter und Sicherheitsanforderungen.
