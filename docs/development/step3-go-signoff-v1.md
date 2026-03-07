# Schritt 3 Umsetzungs-Referenz v1

## Zweck
Konsolidierte Referenz auf die für Schritt 3 relevanten technischen Spezifikationen, ohne personenbezogene Sign-offs oder formale Gate-Entscheidung.

## Referenzquellen
- `docs/security/keycloak-integration-profile-v1.md`
- `docs/security/keycloak-integration-inputs-v1.md`
- `docs/development/step3-dor-checklist.md` (als Arbeitscheckliste)
- `docs/security/threat-model.md`
- `docs/security/security-controls.md`
- `docs/testing/test-matrix.md`

## Architektur-Check (kontinuierlich)
- Tenant-Scoping ist in allen WP als Pflichtkontext umzusetzen.
- AuthN/AuthZ, Business-Validation und Queue/Outbox-Logik bleiben getrennte Verantwortlichkeiten.
- Idempotenz für `complete-upload` ist fachlich verbindlich umzusetzen.

## Security-Check (kontinuierlich)
- Keine internen Stacktraces/Secrets in Responses.
- Fehlerprofil mit `correlation_id` konsistent halten.
- Abuse-Tests für Claim-Manipulation, Cross-Tenant, Replay und Upload-Spoofing pro WP führen.
