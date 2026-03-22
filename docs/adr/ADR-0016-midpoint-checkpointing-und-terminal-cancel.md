# ADR-0016: Midpoint-Checkpointing und terminaler Cancel-Endpunkt

- Status: Accepted
- Datum: 2026-03-22

## Kontext
Der bisherige Pause/Resume-Pfad war ein kooperativer Stop mit anschließendem Neu-Start ab Stage-Beginn. Das erhöht Laufzeitkosten und kann Segmentarbeit doppelt ausführen. Gleichzeitig fehlte ein expliziter terminaler Cancel-Endpunkt mit finaler Semantik.

## Entscheidung
1. Checkpointing wird als persistentes Stage+Segment-Modell eingeführt (`job_checkpoints`).
2. Checkpoint-Stages: `downloaded`, `asr_started`, `asr_done`, `diarization_done`.
3. ASR erhält segmentbasiertes Midpoint-Checkpointing (`stage_offset`), sodass `resume` ab letztem Segment fortsetzt statt Stage-Neustart.
4. Neuer API-Endpunkt: `POST /api/v1/jobs/{id}/cancel`.
5. Cancel ist terminal: `canceled` ist final; `resume` auf `canceled` liefert `409 job.resume.invalid_state`.
6. Transition-Modell für Cancel: `queued|processing|pause_requested|paused -> cancel_requested -> canceled`.
7. Teilresultate bleiben intern (Checkpoint/Worker-Artefakte), ohne Frontend-/API-Exposition.

## Sicherheitsauswirkungen
- Tenant-Isolation bleibt erzwungen, da Checkpoints tenant-scoped gespeichert und gelesen werden.
- Resume/Cancellation folgen weiterhin dem standardisierten Fehlerprofil (`error_code`, `correlation_id`) ohne sensitive Laufzeitdetails.
- Interne Teilresultate werden nicht als API-Ressource veröffentlicht und reduzieren damit Datenabfluss-/Enumeration-Risiken.
- Cancel priorisiert kontrollierten Abbruch vor Retry-Fortsetzung; dadurch sinkt Risiko ungewollter Weiterverarbeitung nach Nutzerabbruch.

## Architekturfolgen
- Neue persistente Infrastrukturkomponente `job_checkpoints` mit minimalem Write-Overhead.
- Worker-Pipeline wird checkpoint-aware und entscheidet stagebasiert über Skip/Fortsetzung.
- Outbox- und Lifecycle-Logik werden um terminale Cancel-Semantik ergänzt.
- Frontend erhält aktive Cancel-Interaktion bei laufenden/pausierten Jobs, ohne interne Partialdaten sichtbar zu machen.

## Alternativen
- Nur Stage-basiertes Checkpointing ohne Segmentoffset: verworfen, weil ASR-Doppellauf bei langen Medien bestehen bleibt.
- Resume weiterhin als kompletter Neu-Start: verworfen, weil ineffizient und operativ teuer.
- Soft-Cancel mit Resume-Möglichkeit: verworfen, da Produktentscheidung einen finalen Cancel fordert.

## Umgesetzte Artefakte
- `evodox/jobs/lifecycle_service.py`
- `evodox/web/fastapi_adapter.py`
- `evodox/jobs/infrastructure.py`
- `evodox/jobs/worker_pipeline_service.py`
- `evodox/runtime/worker_runner.py`
- `frontend/app.js`
- `frontend/utils.js`
