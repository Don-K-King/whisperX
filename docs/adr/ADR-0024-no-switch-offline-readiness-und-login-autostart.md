# ADR-0024: No-Switch Offline-Readiness und Login-Autostart

## Status
Accepted - 2026-03-27

## Kontext
EvidoX soll auf einem Windows-PC im Normalbetrieb weiterentwickelbar bleiben, fuer den Pilotbetrieb aber ohne Internet nach Neustart (nach User-Login) transkribieren koennen.
Manuelle Umschaltung zwischen "Dev" und "Offline" ist fehleranfaellig und fuer sensible Medien nicht ausreichend robust.

## Entscheidung
1. Es gibt einen einheitlichen Bootstrap-Pfad (`deploy/start-evodox.ps1`) fuer beide Betriebslagen.
2. Der Bootstrap prueft Offline-Readiness automatisch und fuehrt bei verfuegbarem Internet ein Auto-Prepare fehlender Artefakte aus.
3. Worker-Laufzeit wird offline-sicher gehaertet:
   - WhisperX-CLI immer mit `--model_cache_only True`
   - optionaler Strict-Offline-Modus (`WORKER_OFFLINE_STRICT=true`)
   - lokale Diarization-Snapshot-Aufloesung statt Hub-Identifier
   - fail-fast bei fehlender `punkt_tab`-Ressource
4. Windows-Autostart wird ueber Task Scheduler bei Login eines beliebigen Users umgesetzt (kein BIOS-Zwang, kein Firewall-Autoblocking).

## Konsequenzen
- Positiv:
  - Kein manueller Moduswechsel im Tagesbetrieb notwendig.
  - Offline-Uebergabe nach Neustart und User-Wechsel wird reproduzierbar.
  - Fehlende Offline-Voraussetzungen werden frueh und konkret gemeldet.
- Negativ:
  - Erstbereitstellung kann laenger dauern (Auto-Prepare von Modellen/Ressourcen).
  - Zusatzausfallpfad bei unvollstaendiger lokaler Artefaktlage.

## Sicherheits-/Betriebsauswirkungen
- Sensitive Medien bleiben im Offline-Betrieb lokal verarbeitbar.
- Runtime greift im Strict-Offline-Modus nicht auf Laufzeit-Downloads zurueck.
- Start-/Readiness-Verhalten ist auditiert und runbook-basiert nachvollziehbar.

## Verweise
- `deploy/start-evodox.ps1`
- `deploy/register-evodox-login-autostart.ps1`
- `evodox/runtime/offline_readiness.py`
- `evodox/runtime/worker_runner.py`
- `docs/operations/runbooks.md`
