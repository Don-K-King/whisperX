# ADR-0017: GPU-First Local Runtime und vorbereitete Multi-GPU Worker-Pools (Compose)

## Status
Angenommen - 2026-03-22

## Kontext
Die Worker-Runtime war funktional fuer WhisperX, lief aber standardmaessig CPU-basiert. Gleichzeitig bestand das Zielbild aus queue-orientierter horizontaler Skalierung, inklusive dedizierter GPU-Ressourcen fuer schwere Jobs. Fuer den lokalen Betrieb sollte GPU ohne Zusatzschalter direkt genutzt werden; fuer spaeteren Serverbetrieb sollten mehrere GPUs dediziert bedienbar sein.

## Entscheidung
- Worker-Defaults werden auf GPU-first gesetzt:
  - `WORKER_WHISPERX_DEVICE=cuda`
  - `WORKER_WHISPERX_COMPUTE_TYPE=float16`
- Worker-Runtime fuehrt einen GPU-Preflight aus:
  - Bei nicht verfuegbarer CUDA erfolgt kontrollierter CPU-Fallback auf `device=cpu`, `compute_type=int8`.
  - Fallback wird strukturiert geloggt und auditierbar protokolliert (`worker.runtime.gpu_fallback`).
- Multi-GPU-Vorbereitung wird ohne Runtime-Refactor umgesetzt:
  - `WORKER_WHISPERX_DEVICE_INDEX` wird eingefuehrt und an WhisperX CLI (`--device_index`) durchgereicht.
  - `WORKER_ALLOWED_QUEUES` wird eingefuehrt; Worker koennen queue-spezifisch filtern (`gpu-*` vs `cpu-*`).
  - Compose erhaelt vorbereitete dedizierte Services `worker-gpu-0`, `worker-gpu-1`, `worker-cpu` (Profile `multi-gpu`) mit GPU-Pinning und Queue-Trennung.

## Begruendung
- GPU-first reduziert lokale Time-to-Result deutlich ohne manuelles Umschalten.
- Kontrollierter Fallback sichert Verfuegbarkeit im Dev-/On-Prem-Betrieb, bleibt aber durch Audit/Logs transparent.
- Device-Index + Queue-Filter schafft einen stabilen Migrationspfad zu dedizierten Worker-Pools.
- Die Loesung bleibt kompatibel zur bestehenden Architektur (Outbox, tenant-scope, Retry/DLQ, Audit).

## Konsequenzen
- Positiv:
  - Lokale Standardlaeufe nutzen GPU direkt.
  - Multi-GPU-Serverbetrieb ist per Compose-Profil sofort aktivierbar.
  - Fallbacks sind operativ nachvollziehbar (kein stilles Degradieren).
- Negativ:
  - Queue-Filter ist vorbereitend; fuer maximale Cluster-Skalierung bleibt spaetere vollstaendige Broker-Consumer-Entkopplung sinnvoll.
  - GPU-Container setzen funktionierende NVIDIA-Runtime voraus.

## Security-Auswirkung
- Keine Aenderung an Tenant-Isolation oder AuthZ/AuthN.
- Keine Secrets in Fallback-Logs; nur nicht-sensitive Runtime-Metadaten.
- Audit-Pflicht fuer sicherheitsrelevante Runtime-Degradierung (GPU -> CPU) ist umgesetzt.
