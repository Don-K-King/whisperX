# ADR-0006: Transcript-Versionierung (Optimistic Locking) und sichere Export-Pipeline

## Status
Angenommen – 2026-03-08

## Kontext
Nach Schritt 4 fehlte in Phase 1 die fachliche Bearbeitungsschicht für Transkript-Edits sowie ein sicherer Exportpfad (`txt|json|srt|vtt`) im Tenant-Kontext. Ohne explizite Versionierung drohen Lost Updates bei parallelen Edits; ohne Export-Härtung drohen XSS-/Injection-Risiken in Ausgabeformaten.

## Entscheidung
- Transcript-Änderungen werden über `base_version` mit Optimistic Locking abgesichert.
- Bei Versionskonflikt wird deterministisch ein Konfliktfehler (`transcript.version_conflict`) erzeugt.
- Export wird über dedizierten Service (`queue_export`) gekapselt, inkl. strikter Format-Validierung und tenant-scoped Transcript-Lookup.
- Für textbasierte Exportformate wird eine Escape-Strategie angewendet, damit Transkriptinhalte als Daten behandelt werden.

## Begründung
- Entkoppelte Services verbessern Wartbarkeit gegenüber endpoint-zentrierter Inline-Logik.
- Optimistic Locking minimiert Race Conditions ohne globale Schreibsperren.
- Validierung + Escaping reduzieren Security-Risiken bei untrusted Transcript-Inhalten.
- Tenant-gebundene Repositories stärken Mandantenisolation im Edit/Export-Pfad.

## Konsequenzen
- Zusätzliche Konfliktbehandlung im Client erforderlich (`409` bei veralteter `base_version`).
- Export-Inhalte können durch Escaping von Rohtranskript-Darstellung abweichen (sicherheitsgetrieben).
- Für spätere Skalierung empfohlen: persistente Export-Queue mit idempotenter Worker-Ausführung je `export_id`.
