# ADR-0005: Worker-Pipeline-Kette und Tenant-Fairness mit Backpressure

## Status
Angenommen – 2026-03-08

## Kontext
Mit WP-4.1 wurde Queue-Governance (Retry/DLQ/Dedup) auf Dispatcher-Ebene umgesetzt. Für Schritt 4 fehlten noch die eigentliche Worker-Verarbeitungskette (ASR/Alignment/Diarization) sowie ein Tenant-faires Lastmodell, das Starvation vermeidet und Backpressure erzwingt.

## Entscheidung
- Die Worker-Verarbeitung wird als dedizierter Applikationsservice (`WorkerPipeline`) umgesetzt, getrennt von Broker-/Dispatcher-Details.
- Die Kette verarbeitet nur tenant-scoped Jobs in zulässigen Zuständen (`queued`, `failed_retryable`) und persistiert Artefakte tenant-scoped.
- Fehler werden explizit klassifiziert:
  - `RetryableWorkerError` → `failed_retryable`
  - `TerminalWorkerError` → `failed_terminal`
- Tenant-Fairness und Backpressure werden in einer separaten Scheduling-Policy (`TenantFairnessPolicy`) mit globalen und per-tenant Inflight-Limits sowie Round-Robin-Entnahme umgesetzt.

## Begründung
- Verhindert unkontrollierte Kopplung zwischen Fachlogik und Broker-Layer.
- Erzwingt Mandantenisolation auch innerhalb der Worker-Pipeline (object_key-Scope-Check).
- Reduziert Betriebsrisiko durch klare Retry/Terminal-Trennung und begrenzte Parallelität.
- Verbessert horizontale Skalierbarkeit, weil Fairness/Backpressure als austauschbare Policy implementiert ist.

## Konsequenzen
- Zusätzliche Service-/Policy-Module erhöhen initiale Komplexität, verbessern aber Wartbarkeit und Testbarkeit.
- Für produktiven Betrieb müssen Fairness-Limits je Deployment-Klasse konfiguriert und überwacht werden.
- Folgearbeit empfohlen: Persistenter Scheduler-State für Multi-Worker-Fairness über Prozessgrenzen hinweg.
