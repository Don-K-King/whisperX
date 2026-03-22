# Schritt 3 Arbeits-Checkliste (WP-3.1 bis WP-3.4)

## Zweck
Pragmatische Arbeitscheckliste für Schritt 3 als interne Umsetzungsstütze ohne formale Freigabeentscheidungslogik.

## WP-3.1 Auth Middleware + Tenant Context
- Akzeptanzkriterien dokumentiert
- Security-Scoping dokumentiert (AuthN/AuthZ/Tenant)
- Testdesign dokumentiert (Unit/Integration/Abuse)
- Reproduzierbarkeit referenziert (Versionen/Fixtures)
- Referenzen: `keycloak-integration-profile-v1`, `security-spec-v1`, `test-spec-v1`

## WP-3.2 Job-Create Endpoint + Upload Session
- Akzeptanzkriterien dokumentiert
- Security-Scoping dokumentiert (Validation/Tenant/Audit)
- Testdesign dokumentiert (Unit/Integration/Abuse)
- Reproduzierbarkeit referenziert (Versionen/Fixtures)
- Referenzen: `api-spec-v1`, `security-spec-v1`, `test-matrix`

## WP-3.3 Complete-Upload Idempotency + Queue Publish
- Akzeptanzkriterien dokumentiert
- Security-Scoping dokumentiert (Replay/State-Integrity)
- Testdesign dokumentiert (Integration/Contract/Abuse)
- Reproduzierbarkeit referenziert (Versionen/Fixtures)
- Referenzen: `api-spec-v1`, `event-contracts-v1`, `test-spec-v1`

## WP-3.4 Job-Status Endpoint
- Akzeptanzkriterien dokumentiert
- Security-Scoping dokumentiert (Info-Disclosure/Tenant)
- Testdesign dokumentiert (Integration/E2E/Abuse)
- Reproduzierbarkeit referenziert (Versionen/Fixtures)
- Referenzen: `api-spec-v1`, `test-matrix`
