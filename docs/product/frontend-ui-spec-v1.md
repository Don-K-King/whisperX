# EvidoX Frontend/UI-Spezifikation v1 (Phase 1)

## 1. Status, Scope und Ziel
- **Status:** Verbindliche UX/UI-Spezifikation für die Realisierung von Phase 1.
- **Scope:** Login, Dashboard, Job-Erstellung/Upload, Job-Detail inkl. Status, Admin-Audit-Ansicht.
- **Nicht-Scope:** Finaler Transcript-Editor und Export-Feininteraktionen jenseits der in Schritt 3 vorgesehenen Endpunkte.
- **Primärreferenzen:**
  - `docs/architecture/api-spec-v1.md`
  - `docs/security/security-spec-v1.md`
  - `docs/testing/test-spec-v1.md`
  - `docs/development/implementation-playbook-v1.md`

Diese UI-Spezifikation ergänzt die bestehenden v1-Spezifikationen, ersetzt sie aber nicht. API-/Security-/Test-Contracts bleiben führend.

## 2. Technologieentscheidung Frontend (verbindlich)
### 2.1 Entscheidung
**React + TypeScript + Vite** wird als Frontend-Stack für Phase 1 festgelegt.

### 2.2 Begründung (Architektur, Sicherheit, Betrieb)
1. **Architektur-Fit:** In `Entwicklungs.md` bereits als Zielarchitektur vorgesehen; reduziert Architekturdrift.
2. **Sicherheitsfit:** Reife OIDC-Bibliotheken, gutes Ecosystem für strikte Typisierung von API-Responses und Auth-Claims.
3. **Skalierbarkeit/Wartbarkeit:** Komponentenbasierte UI-Struktur mit klarer Trennung von Domain-Logik, View und API-Client.
4. **Betrieb/Reproduzierbarkeit:** Schnelle, deterministische Builds mit Vite; gut in Container-Build-Pipelines integrierbar.

### 2.3 Kritische Alternativenbewertung
- **Vue 3 + TypeScript:** technisch geeignet, aber Architekturwechsel ohne Mehrwert gegenüber bereits festgelegter Zielarchitektur.
- **Angular:** stark für Enterprise, aber höhere Komplexität und längere Einarbeitung; für Phase-1-Ziele nicht optimal.
- **Svelte/SvelteKit:** hohe Performance, aber geringere organisatorische Standardisierung im aktuellen Architekturplan.

**Fazit:** React + TypeScript ist die beste Variante unter Architektur- und Governance-Gesichtspunkten.

## 3. Verbindliche Produkt- und UX-Entscheidungen
Folgende Entscheidungen sind durch den Auftraggeber festgelegt und verbindlich umzusetzen:
- Branding-Grad: **markenprägend**
- Theme: **Light + Dark** von Beginn an
- Dashboard-Dichte: **Kartenbasiert**
- Retention-Eingabe im MVP: **nur anzeigen** (nicht editierbar)
- Fehlerkommunikation: **debug-freundlich**
- Admin-Audit-Ansicht: **in Phase 1 sichtbar** (rollenbasiert)
- Internationalisierung: **i18n-ready ab Tag 1**
- Upload-UX: **Drag&Drop + klassischer File-Picker**
- Statusdarstellung: **Prozentanzeige**
- Mobile-Priorität: **responsive desktop-first**

## 4. Informationsarchitektur
## 4.1 Primäre Navigation
- Dashboard
- Neuer Job
- Job-Detail
- Audit (nur mit Admin/Compliance-Rolle sichtbar)

## 4.2 Globaler Header
- Tenant-Badge (`tenant_id` aus validiertem Token-Kontext)
- Benutzer-Menü (Rolle, Session-Infos, Logout)
- Theme-Toggle (Light/Dark)
- Sprachumschalter (i18n-ready; initiale Sprachenkonfiguration gemäß Produktvorgabe)

## 5. Screen-by-Screen-Spezifikation
## 5.1 Login
- OIDC Authorization Code + PKCE Startpunkt
- Primärer CTA: „Anmelden“
- Debug-freundliche Fehlerdarstellung für 401/Session-Timeout/Issuer-Audience-Mismatch
- Keine internen Sicherheitsdetails leaken (z. B. keine Roh-Stacktraces)

### Akzeptanzkriterien
- Ungültige Session führt zu kontrollierter Weiterleitung auf Login.
- Auth-Fehler erzeugen nutzbare Fehlerhinweise mit Korrelation-ID.

## 5.2 Dashboard (kartenbasiert)
- Job-Karten mit: Job-ID (gekürzt), Dateiname, Status, Prozentfortschritt, `retention_months`, Erstellzeit
- Filter: Status, Zeitraum, optional Suchbegriff
- Empty-State mit klarem CTA „Neuen Job erstellen“

### Akzeptanzkriterien
- Nur tenant-zugehörige Jobs werden angezeigt.
- Karten aktualisieren Status ohne inkonsistente Zwischendarstellung.

## 5.3 Neuer Job (Wizard)
### Schritt A – Metadaten
- Datei via Drag&Drop oder File-Picker
- Anzeige erlaubter Dateitypen/Maximalgröße
- Anzeige `retention_months` als read-only (MVP)

### Schritt B – Upload und Finalisierung
- Chunked-/resumable Upload-Progress in Prozent
- Abschluss via `complete-upload`
- Erfolgsfall: Weiterleitung zum Job-Detail

### Akzeptanzkriterien
- Clientseitige Vorvalidierung ergänzt serverseitige Pflichtvalidierung.
- Fehlerfälle (MIME/Größe/Netzwerk) sind nachvollziehbar und debug-freundlich.

## 5.4 Job-Detail
- Status-Timeline: Created → Uploaded → Queued → Processing → Done/Failed
- Prozentfortschritt prominent
- Fehlerdetails einklappbar mit technischen Debug-Daten (ohne Secret-Leakage)

### Akzeptanzkriterien
- Kein Information-Leak bei fremder Job-ID (kein Existenzbeweis über Fehlermeldung).
- Polling/Refresh ist robust bei kurzen Netzwerkunterbrechungen.

## 5.5 Admin-Audit-Ansicht (Phase 1)
- Rollenbasiert sichtbar (Default-Deny)
- Listet nur gemäß API-Berechtigung verfügbare Audit-Events
- Filter nach Tenant, Zeitraum, Event-Typ

### Akzeptanzkriterien
- Nicht-Admin erhält keine Navigationssichtbarkeit und keinen Datenzugriff.
- Audit-Detailansicht zeigt `tenant_id`, `actor_id`, `correlation_id` soweit API-seitig verfügbar.

## 6. Design System (modern, nicht überladen)
- **Visueller Stil:** markenprägend, klar, reduzierte Oberflächenkomplexität
- **Typografie:** gut lesbare Sans-Serif mit klarer Hierarchie
- **Spacing:** 8px-Grid
- **Komponenten-Mindestset:**
  - Buttons (Primary/Secondary/Ghost/Danger)
  - Inputs/Selects/Dropzone
  - Status-Badges
  - Progress-Bar
  - Toast + Inline-Errors
  - Karten-Layouts
  - Dialoge für kritische Aktionen
- **Theming:** einheitliche Design-Tokens für Light/Dark

## 7. i18n- und Accessibility-Anforderungen
- UI-Text ausschließlich über i18n-Keys (keine Hardcoded-Strings in Komponenten)
- Keyboard-Navigation vollständig für Kernflows
- Kontrastziel mindestens WCAG 2.1 AA
- Sichtbare Fokuszustände in beiden Themes

## 8. Sicherheitsanforderungen für das Frontend
1. Token nur über definierte Auth-Flows beziehen; keine unsichere Persistenz sensibler Daten.
2. Tenant-Kontext wird angezeigt, aber Autorisierung ausschließlich serverseitig erzwungen.
3. Alle Eingaben als untrusted behandeln; Frontend-Validation ist rein UX, nicht Security-Grenze.
4. Fehlerausgaben debug-freundlich, jedoch ohne Offenlegung von Secrets/Interna.
5. Schutz gegen Missbrauch: Upload-Raten, Retry-Verhalten und Timeout-Handling gemäß Backend-Policies.

## 9. Architekturkonflikte und Gegenstrategien
- **Konflikt:** Markenprägendes UI vs. reduzierte Komplexität.
  - **Gegenstrategie:** Striktes Component-System, wenig visuelle Spezialfälle, klare Informationshierarchie.
- **Konflikt:** Debug-freundliche Fehler vs. Security by Default.
  - **Gegenstrategie:** Korrelation-ID + kategorisierte Fehlercodes statt sensibler Rohdetails.
- **Konflikt:** Light/Dark ab Start vs. Liefergeschwindigkeit.
  - **Gegenstrategie:** Token-basiertes Theming von Anfang an, keine nachträglichen Theme-Refactors.

## 10. Verbindliche Umsetzungsartefakte (vor Coding)
1. Screen-Flows (Login, Dashboard, Upload-Wizard, Job-Detail, Audit)
2. UI-Contract-Check gegen API v1 (Payloads, Fehlercodes, Statusfelder)
3. Testable Acceptance Criteria je Screen
4. Frontend-spezifische Threat-/Control-/Test-Zuordnung in den bestehenden Security-/Testdokumenten

## 11. Teststrategie für UI-Realisierung (TDD-konform)
- Unit-Tests für Formatierungs-/Mapping-/State-Logik
- Integration-Tests für API-Interaktion inkl. Fehlerpfade
- Edge-/Abuse-Tests (Dateitypen, Größenlimits, ungültige Statusdaten)
- E2E-Smoke für Kernfluss Login → Job → Upload complete → Status
- Regression nur verpflichtend bei Pipeline-/Build-/Architektur-/Strukturänderungen

## 12. Dokumentations- und PR-Pflichten
- Jede Nutzer-/Betreiberrelevante UI-Änderung in `docs/product/changelog.md`
- Architekturrelevante UI-Entscheidungen in `docs/development/decisions-log.md`
- Bei UI/Design-Änderungen sind Screenshots im PR verpflichtend (siehe `AGENTS.md`)
