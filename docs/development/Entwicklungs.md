# Entwicklungsplan Referenz

Die Hauptversion des Entwicklungsplans befindet sich in der Repository-Wurzel: [`/Entwicklungs.md`](../../Entwicklungs.md).

Dieses Dokument dient als stabile Referenz innerhalb der `/docs`-Struktur.

## Vorgeschalteter Schritt 3A (AuthN/AuthZ-Gate)
Vor dem Implementierungsstart von Schritt 3 ist der verbindliche Teilschritt **3A** abgeschlossen.

### Ziel
Vollständige Klärung der AuthN/AuthZ-Spezifikation für die Implementierung, inklusive Tenant-Isolation und Default-Deny-Verhalten.

### Verbindliche Lieferobjekte für 3A
1. Keycloak-Integrationsprofil v1 (Realm, Clients, Flows, Token-Laufzeiten, JWKS/Issuer/Audience).
2. Rollen-/Claim-Mapping v1 (`user`, `reviewer`, `admin`, `tenant_id`) inkl. Default-Deny-Regeln.
3. Fehler- und Recovery-Verhalten für Auth-Fälle (401/403, Token-Expiry, Key-Rotation, Clock-Skew).
4. Security-Testgates für AuthN/AuthZ (Claim-Manipulation, Cross-Tenant-Zugriffe, Replay).

### Referenzen
- `docs/architecture/api-spec-v1.md`
- `docs/security/security-spec-v1.md`
- `docs/testing/test-spec-v1.md`

### Abnahmekriterium
Kein offener Auth-/Tenant-Entscheidungspunkt mehr vor Start der Implementierung.

Schritt 3 darf erst starten, wenn die Keycloak-Integration-Inputs-v1 vollständig befüllt und von Keycloak-Team und API-Team signiert/freigegeben sind.
