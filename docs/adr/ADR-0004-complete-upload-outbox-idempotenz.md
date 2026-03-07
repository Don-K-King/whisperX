# ADR-0004: Complete-Upload mit Outbox-basierter Queue-Publikation

## Status
Angenommen – 2026-03-07

## Kontext
Für `POST /api/v1/jobs/{id}/complete-upload` besteht ein Zielkonflikt zwischen einfacher direkter Queue-Publikation und konsistenter, replay-resistenter Verarbeitung im Tenant-Scope.

## Entscheidung
- Fachliche Idempotenz wird tenant-scoped im Service erzwungen.
- Statusübergang nach `queued` und Event-Erzeugung erfolgen über Outbox-Speicherung.
- Queue-Publikation wird über einen separaten Dispatcher verarbeitet (publish + mark_published).

## Begründung
- Reduziert Risiko inkonsistenter Zustände bei Teilfehlern (Persistenz ok, Publish fail / umgekehrt).
- Erhöht Auditierbarkeit und Reproduzierbarkeit.
- Entspricht Security-by-Default und Architekturziel (skalierbare, entkoppelte Verarbeitung).

## Konsequenzen
- Zusätzliche Infrastrukturkomponente (Outbox) erhöht Implementierungsaufwand.
- Betrieb benötigt Dispatcher-Monitoring (Lag, Fehlerquote).
- API-Vertrag bleibt stabil; interne Konsistenz steigt.
