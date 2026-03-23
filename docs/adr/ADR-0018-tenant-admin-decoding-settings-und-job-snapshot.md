# ADR-0018: Tenant-Admin Decoding Settings mit Job-Snapshot

## Status
Angenommen - 2026-03-22

## Kontext
WhisperX-Decoding-Optionen waren nur ueber Worker-ENV konfigurierbar. Das war fuer Tenant-Admins nicht bedienbar, nicht persistent ueber das Frontend steuerbar und fuer einzelne Jobs nicht reproduzierbar, wenn sich Runtime-Parameter zwischenzeitlich aendern.

## Entscheidung
- Neue admin-only, tenant-scoped API-Endpunkte:
  - `GET /api/v1/admin/transcription-settings`
  - `PUT /api/v1/admin/transcription-settings`
- Persistente Tenant-Defaults werden in `tenant_transcription_settings` gespeichert.
- Bei `complete-upload` wird ein normalisierter Decoding-Snapshot pro Job erzeugt und in `jobs.transcription_options_json` persistiert.
- `job.queued` Outbox-Events enthalten den Snapshot als `transcription_options`.
- `resume` uebernimmt denselben Snapshot in neue Outbox-Events.
- Worker mappt nur eine Whitelist von Decoding-Optionen auf WhisperX-CLI-Flags; invalide Payloads werden defensiv auf sichere Defaults zurueckgesetzt.
- Audit-Events fuer Read/Update werden geschrieben, ohne `initial_prompt` im Klartext zu loggen (nur Hash/Laenge).

## Begruendung
- Tenant-Isolation bleibt erhalten: jeder Admin konfiguriert nur den eigenen Tenant.
- Reproduzierbarkeit: Jobs nutzen den beim Queueing festgelegten Parameterstand, unabhaengig von spaeteren Tenant-Updates.
- Security by default: strikte Validierung, Whitelist-Mapping und keine sensitive Prompt-Protokollierung.
- Geringes Betriebsrisiko: bestehende Jobs ohne Snapshot bleiben kompatibel und laufen mit Defaults.

## Konsequenzen
- Positiv:
  - Admin-Self-Service fuer transkriptionsrelevante Decoding-Parameter.
  - Deterministisches Verhalten fuer neue Queueings/Resumes.
  - Klare API-Vertraege und testbare Integrationspunkte.
- Negativ:
  - Mehr Komplexitaet in Complete-Upload/Resume/Worker-Wiring.
  - Zusätzliche Persistenzflaechen (Settings-Tabelle + Job-Snapshot-Spalte).

## Security-Auswirkung
- Admin-RBAC bleibt Default-Deny (`required_roles={"admin"}`).
- Tenant-Scoping ist fuer Read/Write verpflichtend.
- Input-Validation erzwingt Feld-Whitelist und Wertebereiche.
- Auditierung ohne Prompt-Klartext reduziert Informationsabfluss.
