# ADR-0020: WhisperX large-v3 Erzwingung, Sprachwahl pro Job und Chunk/VAD Exposition

## Status
Angenommen - 2026-03-23

## Kontext
Die Transcriptionsqualitaet war nicht stabil genug, weil Runtime-Modelle per ENV variieren konnten und Sprach-/Decoding-Parameter nicht konsistent entlang API -> Queue -> Worker durchgereicht wurden.

## Entscheidung
- WhisperX-Worker erzwingt im whisperx Mode hart das Modell large-v3.
- Abweichende Modellkonfigurationen werden als Audit-Event worker.runtime.model_forced protokolliert.
- POST /api/v1/jobs akzeptiert language; Default ist de, zulaessig sind auto|de|en|fr|es|it.
- Sprache wird im Job-Snapshot (transcription_options_json) gespeichert.
- Bei complete-upload werden Tenant-Defaults mit Job-Snapshot gemerged; Job-Werte haben Vorrang.
- Tenant-Admin Decoding-Settings werden um chunk_size, vad_onset, vad_offset erweitert.
- Worker mappt die neuen Felder in WhisperX-CLI-Flags (--chunk_size, --vad_onset, --vad_offset); --language nur wenn Sprache != auto.

## Begruendung
- Konsistente Modellqualitaet: keine Drift durch ENV-Uneinheitlichkeit.
- Reproduzierbarkeit pro Job: Sprache und relevante Decoding-Optionen bleiben im Snapshot nachvollziehbar.
- Sicherheitskonform: strikte Feld-Whitelist, Range-Validation und fail-safe Fallbacks bleiben erhalten.
- Rueckwaertskompatibilitaet: bestehende Jobs ohne neue Felder laufen weiterhin ueber Defaults.

## Konsequenzen
- Positiv:
  - Hoehere und stabilere ASR-Qualitaet durch verpflichtendes large-v3.
  - Weniger Sprach-Fehlklassifikation durch explizite Sprachwahl.
  - Bessere Steuerung von Segmentierung/Qualitaet via Chunk/VAD-Parameter.
- Negativ:
  - Hoeherer Ressourcenbedarf durch large-v3.
  - Mehr Konfigurationsflaeche in Admin-Settings erfordert klare Validierung und Tests.

## Security-Auswirkung
- Neue Inputs (language, chunk_size, vad_onset, vad_offset) werden serverseitig strikt validiert.
- Snapshot-/Settings-Payloads bleiben data-only; keine Input-Ausfuehrung.
- Worker bleibt defensiv: invalide Payloads fallen auf sichere Defaults zurueck.
