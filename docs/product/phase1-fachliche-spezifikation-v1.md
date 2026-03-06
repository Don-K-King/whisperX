# Fachliche Spezifikation v1 (Phase 1)

## Status
Spezifikationsfreeze für Realisierungsphase (Stand: 2026-03-06).

## Ziel und Scope
Phase 1 umfasst die durchgängige Prozesskette **Upload → Verarbeitung → Edit → Export → Retention** für mandantenfähige Transkription.

### In Scope (verbindlich)
1. OIDC-Login via Keycloak (PKCE) mit Rollen `user`, `reviewer`, `admin`.
2. Anlage eines Transkriptionsjobs mit optionaler Retention-Auswahl innerhalb vorgegebener Grenzen.
3. Resumable/chunked Upload nach Object Storage (presigned, direct upload).
4. Asynchrone Verarbeitung über Queue/Worker inkl. WhisperX, Alignment und Speaker-Diarization.
5. Editierbares Transkript mit Versionierung (optimistic locking).
6. Export in **TXT, JSON, SRT, VTT**.
7. Tenant-isolierter Zugriff auf Jobs, Transkripte, Exporte und Auditdaten.
8. Retention-Durchsetzung mit Nachweis im Audit.

### Out of Scope (Phase 1)
- Live-Streaming-Transkription.
- Automatische Übersetzung/Summarization.
- Globale (tenant-übergreifende) Suche.
- Custom Training/Fine-Tuning von Modellen.

## Verbindliche Grenzwerte
- Maximale Upload-Größe: **20 GB** pro Job.
- Maximale Medienlänge: **8 Stunden** pro Job.
- Erlaubte Eingabeformate: `mp3`, `wav`, `m4a`, `mp4`, `mov`, `mkv`.
- Dateivalidierung: Extension + MIME + Magic Bytes müssen konsistent sein.
- Retention-Werte: `1..36` Monate.

## Rollen- und Rechtekatalog (fachlich)
- **User:** eigene Jobs im eigenen Tenant anlegen, sehen, editieren, exportieren.
- **Reviewer:** alle Jobs im eigenen Tenant lesen/bearbeiten/exportieren; keine Systemadministration.
- **Admin:** tenant-lokale Administrationsrechte inkl. Audit-Einsicht im eigenen Tenant.
- **Default Deny:** Nicht explizit erlaubte Operationen sind untersagt.

## Akzeptanzkriterien (Given/When/Then)

### 1) Upload
- **Given** ein authentifizierter User im Tenant A, **when** der User einen Job mit gültigen Metadaten anlegt, **then** erhält er eine upload session inkl. presigned URL.
- **Given** eine Datei >20 GB oder ungültigem Format, **when** Upload vorbereitet wird, **then** wird die Anfrage mit Validierungsfehler abgewiesen.

### 2) Verarbeitung
- **Given** ein finalisierter Upload, **when** `complete-upload` aufgerufen wird, **then** wird genau ein verarbeitbarer Job in die Queue überführt (idempotent).
- **Given** Worker-Fehler, **when** Retry-Limit erreicht ist, **then** wird der Job in DLQ überführt und auditierbar markiert.

### 3) Edit
- **Given** ein vorhandenes Transkript, **when** User/Reviewer Änderungen speichert, **then** wird eine neue Version mit `version_number+1` erzeugt.
- **Given** parallele Änderungen, **when** veraltete Version gespeichert wird, **then** erfolgt Konfliktantwort (optimistic locking).

### 4) Export
- **Given** berechtigter Zugriff im Tenant, **when** Export angefordert wird, **then** wird Exportartefakt im gewählten Format erstellt und tenant-scoped ausgeliefert.
- **Given** Zugriff auf Fremd-Tenant-ID, **when** Export gelesen wird, **then** erfolgt `403` ohne Datenleck.

### 5) Retention
- **Given** gesetzte Retention-Frist, **when** Frist abläuft, **then** werden Rohdaten/Artefakte nach Richtlinie gelöscht und Audit-Events erzeugt.
- **Given** Manipulationsversuch an Retention-Feldern, **when** API-Eingabe validiert wird, **then** werden ungültige Werte verworfen und geloggt.

## Architekturkonflikte und Gegenmaßnahmen
1. **Konflikt:** Große Datei-Support vs. API/Proxy-Stabilität.
   - **Maßnahme:** Direct upload, Chunking, serverseitige Größenprüfung.
2. **Konflikt:** Breiter Reviewer-Zugriff vs. Least Privilege.
   - **Maßnahme:** Reviewer strikt tenant-lokal, Audit aller Review-Operationen.
3. **Konflikt:** Mehr Exportformate vs. Angriffsfläche.
   - **Maßnahme:** Format-Whitelisting, Output-Encoding, Security-Tests je Format.
