# EvidoX Frontend/UI-Spezifikation v1 (Phase 1)

## 1. Status, Scope und Ziel
- **Status:** Verbindliche UX/UI-Spezifikation fÃ¼r die Realisierung von Phase 1.
- **Scope:** Login, Dashboard, Job-Erstellung/Upload, Job-Detail inkl. Status und Transcript-Ansicht, Speaker-Alias-Pflege, Admin-Audit-Ansicht.
- **Nicht-Scope:** Export-Feininteraktionen jenseits der in Schritt 3 vorgesehenen Endpunkte.
- **PrimÃ¤rreferenzen:**
  - `docs/architecture/api-spec-v1.md`
  - `docs/security/security-spec-v1.md`
  - `docs/testing/test-spec-v1.md`
  - `docs/development/implementation-playbook-v1.md`

Diese UI-Spezifikation ergÃ¤nzt die bestehenden v1-Spezifikationen, ersetzt sie aber nicht. API-/Security-/Test-Contracts bleiben fÃ¼hrend.

## 2. Technologieentscheidung Frontend (verbindlich)
### 2.1 Entscheidung
**React + TypeScript + Vite** wird als Frontend-Stack fÃ¼r Phase 1 festgelegt.

### 2.2 BegrÃ¼ndung (Architektur, Sicherheit, Betrieb)
1. **Architektur-Fit:** In `Entwicklungs.md` bereits als Zielarchitektur vorgesehen; reduziert Architekturdrift.
2. **Sicherheitsfit:** Reife OIDC-Bibliotheken, gutes Ecosystem fÃ¼r strikte Typisierung von API-Responses und Auth-Claims.
3. **Skalierbarkeit/Wartbarkeit:** Komponentenbasierte UI-Struktur mit klarer Trennung von Domain-Logik, View und API-Client.
4. **Betrieb/Reproduzierbarkeit:** Schnelle, deterministische Builds mit Vite; gut in Container-Build-Pipelines integrierbar.

### 2.3 Kritische Alternativenbewertung
- **Vue 3 + TypeScript:** technisch geeignet, aber Architekturwechsel ohne Mehrwert gegenÃ¼ber bereits festgelegter Zielarchitektur.
- **Angular:** stark fÃ¼r Enterprise, aber hÃ¶here KomplexitÃ¤t und lÃ¤ngere Einarbeitung; fÃ¼r Phase-1-Ziele nicht optimal.
- **Svelte/SvelteKit:** hohe Performance, aber geringere organisatorische Standardisierung im aktuellen Architekturplan.

**Fazit:** React + TypeScript ist die beste Variante unter Architektur- und Governance-Gesichtspunkten.

## 3. Verbindliche Produkt- und UX-Entscheidungen
Folgende Entscheidungen sind durch den Auftraggeber festgelegt und verbindlich umzusetzen:
- Branding-Grad: **markenprÃ¤gend**
- Theme: **Light + Dark** von Beginn an
- Dashboard-Dichte: **Kartenbasiert**
- Retention-Eingabe im MVP: **nur anzeigen** (nicht editierbar)
- Fehlerkommunikation: **debug-freundlich**
- Admin-Audit-Ansicht: **in Phase 1 sichtbar** (rollenbasiert)
- Internationalisierung: **i18n-ready ab Tag 1**
- Upload-UX: **Drag&Drop + klassischer File-Picker**
- Statusdarstellung: **Prozentanzeige**
- Mobile-PrioritÃ¤t: **responsive desktop-first**

## 4. Informationsarchitektur
## 4.1 PrimÃ¤re Navigation
- Dashboard
- Neuer Job
- Job-Detail
- Audit (nur mit Admin/Compliance-Rolle sichtbar)

## 4.2 Globaler Header
- Tenant-Badge (`tenant_id` aus validiertem Token-Kontext)
- Benutzer-MenÃ¼ (Rolle, Session-Infos, Logout)
- Theme-Toggle (Light/Dark)
- Sprachumschalter (i18n-ready; initiale Sprachenkonfiguration gemÃ¤ÃŸ Produktvorgabe)

## 5. Screen-by-Screen-Spezifikation
## 5.1 Login
- OIDC Authorization Code + PKCE Startpunkt
- PrimÃ¤rer CTA: â€žAnmeldenâ€œ
- Debug-freundliche Fehlerdarstellung fÃ¼r 401/Session-Timeout/Issuer-Audience-Mismatch
- Keine internen Sicherheitsdetails leaken (z. B. keine Roh-Stacktraces)

### Akzeptanzkriterien
- UngÃ¼ltige Session fÃ¼hrt zu kontrollierter Weiterleitung auf Login.
- Auth-Fehler erzeugen nutzbare Fehlerhinweise mit Korrelation-ID.

## 5.2 Dashboard (kartenbasiert)
- Job-Karten mit: Job-ID (gekÃ¼rzt), Dateiname, Status, Prozentfortschritt, `retention_months`, Erstellzeit
- Filter: Status, Zeitraum, optional Suchbegriff
- Empty-State mit klarem CTA â€žNeuen Job erstellenâ€œ

### Akzeptanzkriterien
- Nur tenant-zugehÃ¶rige Jobs werden angezeigt.
- Karten aktualisieren Status ohne inkonsistente Zwischendarstellung.

## 5.3 Neuer Job (Wizard)
### Schritt A â€“ Metadaten
- Datei via Drag&Drop oder File-Picker
- Anzeige erlaubter Dateitypen/MaximalgrÃ¶ÃŸe
- Anzeige `retention_months` als read-only (MVP)

### Schritt B â€“ Upload und Finalisierung
- Chunked-/resumable Upload-Progress in Prozent
- Abschluss via `complete-upload`
- Erfolgsfall: Weiterleitung zum Job-Detail

### Akzeptanzkriterien
- Clientseitige Vorvalidierung ergÃ¤nzt serverseitige Pflichtvalidierung.
- FehlerfÃ¤lle (MIME/GrÃ¶ÃŸe/Netzwerk) sind nachvollziehbar und debug-freundlich.

## 5.4 Job-Detail
- Status-Timeline: Created â†’ Uploaded â†’ Queued â†’ Processing â†’ Done/Failed
- Prozentfortschritt prominent
- Fehlerdetails einklappbar mit technischen Debug-Daten (ohne Secret-Leakage)
- Transcript-Ansicht mit zusammengefassten Speaker-Bloecken: aufeinanderfolgende Segmente desselben Roh-Speakers werden zu einem Block.
- Speaker-Aliase sind editierbar und werden pro Transcript-Version gespeichert; der Block-Header zeigt den Alias oder das Roh-Label.

### Akzeptanzkriterien
- Kein Information-Leak bei fremder Job-ID (kein Existenzbeweis Ã¼ber Fehlermeldung).
- Polling/Refresh ist robust bei kurzen Netzwerkunterbrechungen.
- Speaker-Bloecke folgen dem Sprachverlauf: erst ein Speaker-Wechsel erzeugt einen neuen Block.
- Alias-Aenderungen fuehren bei Konflikten zu kontrollierter Fehlermeldung und anschliessendem Reload-Pfad.

## 5.5 Admin-Audit-Ansicht (Phase 1)
- Rollenbasiert sichtbar (Default-Deny)
- Listet nur gemÃ¤ÃŸ API-Berechtigung verfÃ¼gbare Audit-Events
- Filter nach Tenant, Zeitraum, Event-Typ

### Akzeptanzkriterien
- Nicht-Admin erhÃ¤lt keine Navigationssichtbarkeit und keinen Datenzugriff.
- Audit-Detailansicht zeigt `tenant_id`, `actor_id`, `correlation_id` soweit API-seitig verfÃ¼gbar.

## 6. Design System (modern, nicht Ã¼berladen)
- **Visueller Stil:** markenprÃ¤gend, klar, reduzierte OberflÃ¤chenkomplexitÃ¤t
- **Typografie:** gut lesbare Sans-Serif mit klarer Hierarchie
- **Spacing:** 8px-Grid
- **Komponenten-Mindestset:**
  - Buttons (Primary/Secondary/Ghost/Danger)
  - Inputs/Selects/Dropzone
  - Status-Badges
  - Progress-Bar
  - Toast + Inline-Errors
  - Karten-Layouts
  - Dialoge fÃ¼r kritische Aktionen
- **Theming:** einheitliche Design-Tokens fÃ¼r Light/Dark

## 7. i18n- und Accessibility-Anforderungen
- UI-Text ausschlieÃŸlich Ã¼ber i18n-Keys (keine Hardcoded-Strings in Komponenten)
- Keyboard-Navigation vollstÃ¤ndig fÃ¼r Kernflows
- Kontrastziel mindestens WCAG 2.1 AA
- Sichtbare FokuszustÃ¤nde in beiden Themes

## 8. Sicherheitsanforderungen fÃ¼r das Frontend
1. Token nur Ã¼ber definierte Auth-Flows beziehen; keine unsichere Persistenz sensibler Daten.
2. Tenant-Kontext wird angezeigt, aber Autorisierung ausschlieÃŸlich serverseitig erzwungen.
3. Alle Eingaben als untrusted behandeln; Frontend-Validation ist rein UX, nicht Security-Grenze.
4. Fehlerausgaben debug-freundlich, jedoch ohne Offenlegung von Secrets/Interna.
5. Schutz gegen Missbrauch: Upload-Raten, Retry-Verhalten und Timeout-Handling gemÃ¤ÃŸ Backend-Policies.

## 9. Architekturkonflikte und Gegenstrategien
- **Konflikt:** MarkenprÃ¤gendes UI vs. reduzierte KomplexitÃ¤t.
  - **Gegenstrategie:** Striktes Component-System, wenig visuelle SpezialfÃ¤lle, klare Informationshierarchie.
- **Konflikt:** Debug-freundliche Fehler vs. Security by Default.
  - **Gegenstrategie:** Korrelation-ID + kategorisierte Fehlercodes statt sensibler Rohdetails.
- **Konflikt:** Light/Dark ab Start vs. Liefergeschwindigkeit.
  - **Gegenstrategie:** Token-basiertes Theming von Anfang an, keine nachtrÃ¤glichen Theme-Refactors.

## 10. Verbindliche Umsetzungsartefakte (vor Coding)
1. Screen-Flows (Login, Dashboard, Upload-Wizard, Job-Detail, Audit)
2. UI-Contract-Check gegen API v1 (Payloads, Fehlercodes, Statusfelder)
3. Testable Acceptance Criteria je Screen
4. Frontend-spezifische Threat-/Control-/Test-Zuordnung in den bestehenden Security-/Testdokumenten

## 11. Teststrategie fÃ¼r UI-Realisierung (TDD-konform)
- Unit-Tests fÃ¼r Formatierungs-/Mapping-/State-Logik
- Integration-Tests fÃ¼r API-Interaktion inkl. Fehlerpfade
- Edge-/Abuse-Tests (Dateitypen, GrÃ¶ÃŸenlimits, ungÃ¼ltige Statusdaten)
- E2E-Smoke fÃ¼r Kernfluss Login â†’ Job â†’ Upload complete â†’ Status
- Regression nur verpflichtend bei Pipeline-/Build-/Architektur-/StrukturÃ¤nderungen

## 12. Dokumentations- und PR-Pflichten
- Jede Nutzer-/Betreiberrelevante UI-Ã„nderung in `docs/product/changelog.md`
- Architekturrelevante UI-Entscheidungen in `docs/development/decisions-log.md`
- Bei UI/Design-Ã„nderungen sind Screenshots im PR verpflichtend (siehe `AGENTS.md`)
- Fuer Transcript-Ansicht und Alias-Pflege gelten Screenshots fuer Default-Zustand, Fehler-/Validierungszustand und responsive Darstellung.

