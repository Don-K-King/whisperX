# Product Requirements (Phase 1)

## Muss-Anforderungen
1. Benutzeranmeldung via Keycloak (OIDC PKCE)
2. Upload großer Audio-/Video-Dateien als Jobs
3. Asynchrone, skalierbare Queue-Verarbeitung
4. Vollständige Transkription inkl. Speaker-Diarization
5. Editierbares Transkript im Frontend
6. Initialer Edit-Export
7. Multi-Tenant-Betrieb mit strikter Datenisolation
8. Löschfrist pro Job/Transcript sichtbar; Default aus ENV in Monaten

## Nicht-funktionale Anforderungen
- On-Prem Docker-Betrieb
- Keine Runtime-Abhängigkeit von externer OpenAI-API
- Hohe Wartbarkeit, Lesbarkeit und Skalierbarkeit
- Vollständige Auditierbarkeit sicherheitsrelevanter Aktionen


## Verbindliche Spezifikationsreferenz
Die umsetzungsrelevanten Detailanforderungen für Phase 1 sind in `docs/product/phase1-fachliche-spezifikation-v1.md` festgelegt.

## 2026-03-24 Erweiterung
9. Korrekturmodus als dedizierter Arbeitsbereich mit Session-Draft, Undo/Redo, Sprecherkorrektur, Suche/Ersetzen, Pruefstatus und Final-Fuehrung.
