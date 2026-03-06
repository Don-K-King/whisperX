# Decisions Log

## 2026-03-06
- ADR-0001 angenommen: On-Prem Multi-Tenant Architektur mit RabbitMQ/Celery Pipeline, lokaler Modellbereitstellung und Retention-Konzept.
- Konsequenz: Alle neuen API-/DB-/Export-Pfade müssen `tenant_id`-gescoped umgesetzt und getestet werden.
- Konsequenz: Retention-Felder und Frontend-Anzeige sind Pflicht für Nutzer-/Compliance-Transparenz.
- Ergänzung: Edge-/Abuse-Teststrategie ist je Entwicklungsschritt verpflichtend (u. a. Prompt-Injection-Resilienz, Rate-Limiting, Input-Validation, ungewöhnliche Eingaben).

- ADR-0002 angenommen: Phase-1 Spezifikationsfreeze mit verbindlichen Fach-, API-, Event-, Datenmodell-, Security- und Test-Spezifikationen.
- Konsequenz: Implementierungsstart nur über Vertical Slice `Auth + Upload` mit TDD- und Security-Gates.
