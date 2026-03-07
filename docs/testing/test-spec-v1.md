# Test-Spezifikation v1 (Freeze-Gates)

## Ziel
Diese Spezifikation definiert die verpflichtenden Test-Gates für die Realisierungsphase basierend auf dem Spezifikationsfreeze.

## Test-Gates (Abnahme)
1. Keine offenen Muss-Anforderungen aus der fachlichen Spezifikation.
2. Jede API-Operation besitzt dokumentierte AuthZ-Regel, Tenant-Scope und Validierungsregeln.
3. Jede Datenentität hat definierte Retention- und Audit-Regeln.
4. Kritische Security-Risiken besitzen Gegenmaßnahmen und Testnachweis.
5. Happy Path + Edge/Abuse sind für alle P0-Anforderungen abgedeckt.

## Priorisierung
- **P0:** Tenant-Isolation, AuthN/AuthZ, Upload-Validierung, Queue-Robustheit, Retention, Audit.
- **P1:** Edit-Konfliktlogik, Exportformate, Observability-Checks.
- **P2:** Performance-Tuning, Komfortfeatures.

## Pflicht-Testfälle (Auszug)

### Unit
- Retention-Range-Validation (`1..36`).
- Statusübergänge Job/Export (inkl. ungültige Übergänge).
- Role-to-Operation Entscheidungen (Default Deny).

### Integration
- API↔DB tenant-scoped Queries.
- API↔Queue Idempotency + Retry.
- Worker↔Storage korrekte tenant object keys.

### Contract
- OpenAPI Schema-Konformität pro Endpoint.
- Event-Schema-Konformität (`event_version=v1`).

### E2E
- Login → Upload → Verarbeitung → Edit → Export.
- Tenant A darf keine Daten aus Tenant B sehen.

### Edge/Abuse
- MIME-Spoofing, oversized upload, ungültige Chunks.
- Manipulierte JWT claims/abgelaufene Tokens.
- Prompt-/Instruction-Injection in Transcript-Content.
- Retry-Storm/Poison-Message Verhalten mit DLQ.
- Verbose Error Probing: keine Stacktraces/Secrets/tenant-fremden Existenzhinweise in 401/403/404/422-Responses.

## Zusätzliche Sicherheits-Contract-Checks
- Fehlerobjekt enthält immer `error_code` + `correlation_id`.
- Tenant-sensitive Endpunkte werden auf Enumerationsresistenz getestet (neutrale Fehlerantworten).

## Regression
- Für diese Dokumentationsänderung nicht erforderlich.
- Für nachfolgende Architektur-/Pipeline-Implementierung verpflichtend (vollständige Regression).


## State-Machine- und Idempotenz-Pflichttests (Schritt 3/4)
- `POST /jobs/{id}/complete-upload` ist fachlich idempotent (kein Doppel-Queueing bei Wiederholung).
- Ungültige Zustandsübergänge werden konsistent abgewiesen und auditierbar protokolliert.
- Race Case: Upload finalisiert, Objekt fehlt im Storage → definierter Fehler ohne inkonsistenten Job-Status.
- Duplicate Event Delivery führt nicht zu mehrfacher fachlicher Verarbeitung.
- Reconciliation-Szenario bei Publish/Persist-Teilfehler wird getestet und dokumentiert.
