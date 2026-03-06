# Threat Model (Kurzfassung)

## Schützenswerte Assets
- Rohmedien
- Transkripte und Edit-Historie
- Tenant-Metadaten und Auditdaten

## Top-Bedrohungen
1. Cross-Tenant Data Leakage
2. Token-Missbrauch / Privilege Escalation
3. Denial-of-Service durch große Dateien
4. Manipulation von Exporten/Löschfristen

## Priorisierte Gegenmaßnahmen
- Striktes Tenant-Scoping + verpflichtende Isolationstests
- Signatur-/Claim-Validierung und kurzlebige Tokens
- Queue-Backpressure, Upload Limits, Worker Concurrency Caps
- Unveränderbare Audit Trails und prüfbare Retention-Jobs
