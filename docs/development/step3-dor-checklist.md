# Schritt 3 DoR-Checklist (WP-3.1 bis WP-3.4)

## Zweck
Verbindlicher Startnachweis für Schritt 3 gemäß `docs/development/implementation-playbook-v1.md`.

## Status-Definition
- `open`: Start nicht zulässig
- `ready`: inhaltlich vollständig, Sign-off ausstehend
- `signed`: Start zulässig

## WP-3.1 Auth Middleware + Tenant Context
- Akzeptanzkriterien definiert: ☐
- Security-Scoping dokumentiert (AuthN/AuthZ/Tenant): ☐
- Testdesign (Unit/Integration/Abuse) dokumentiert: ☐
- Reproduzierbarkeit (Versionen/Fixtures) referenziert: ☐
- Referenzen: `keycloak-integration-profile-v1`, `security-spec-v1`, `test-spec-v1`
- **Status:** `open`
- Sign-off API Lead: ☐
- Sign-off Security Lead: ☐

## WP-3.2 Job-Create Endpoint + Upload Session
- Akzeptanzkriterien definiert: ☐
- Security-Scoping dokumentiert (Validation/Tenant/Audit): ☐
- Testdesign (Unit/Integration/Abuse) dokumentiert: ☐
- Reproduzierbarkeit (Versionen/Fixtures) referenziert: ☐
- Referenzen: `api-spec-v1`, `security-spec-v1`, `test-matrix`
- **Status:** `open`
- Sign-off API Lead: ☐
- Sign-off QA Lead: ☐

## WP-3.3 Complete-Upload Idempotency + Queue Publish
- Akzeptanzkriterien definiert: ☐
- Security-Scoping dokumentiert (Replay/State-Integrity): ☐
- Testdesign (Integration/Contract/Abuse) dokumentiert: ☐
- Reproduzierbarkeit (Versionen/Fixtures) referenziert: ☐
- Referenzen: `api-spec-v1`, `event-contracts-v1`, `test-spec-v1`
- **Status:** `open`
- Sign-off API Lead: ☐
- Sign-off Security Lead: ☐
- Sign-off QA Lead: ☐

## WP-3.4 Job-Status Endpoint
- Akzeptanzkriterien definiert: ☐
- Security-Scoping dokumentiert (Info-Disclosure/Tenant): ☐
- Testdesign (Integration/E2E/Abuse) dokumentiert: ☐
- Reproduzierbarkeit (Versionen/Fixtures) referenziert: ☐
- Referenzen: `api-spec-v1`, `test-matrix`
- **Status:** `open`
- Sign-off API Lead: ☐
- Sign-off QA Lead: ☐

## Gesamtfreigabe Schritt 3
- Schritt 3A signiert: ☐
- WP-3.1 bis WP-3.4 `signed`: ☐
- Threat→Control→Test-Mapping vollständig: ☐
- Gate-Entscheidung: `NO-GO` / `GO`
- Datum/Verantwortung:
