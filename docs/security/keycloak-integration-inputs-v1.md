# Keycloak-Integration Inputs v1 (Schritt 3A Vorlage)

## Status
- **Dokumenttyp:** Verbindliche Abstimmungsvorlage für Schritt 3A.
- **Nutzung:** Technische Integrationsparameter für AuthN/AuthZ.
- **Status:** Arbeitsstand (ohne personenbezogene Freigabeeinträge).

## 1) Metadaten
- Owner Security:
- Owner API:
- Owner IAM/Keycloak:
- SLA Auth-Service:
- Letzte Aktualisierung:

## 2) Realm/Client-Parameter je Umgebung
### dev
- Realm: `evodox`
- Frontend Client-ID: `evodox-frontend`
- API Audience: `evodox-api`
- Redirect URI(s): `https://app.dev.evidox.local/*`
- Post Logout URI(s): `https://app.dev.evidox.local/*`
- Web Origins: `https://app.dev.evidox.local`

### stage
- Realm: `evodox`
- Frontend Client-ID: `evodox-frontend`
- API Audience: `evodox-api`
- Redirect URI(s): `https://app.stage.evidox.local/*`
- Post Logout URI(s): `https://app.stage.evidox.local/*`
- Web Origins: `https://app.stage.evidox.local`

### prod
- Realm: `evodox`
- Frontend Client-ID: `evodox-frontend`
- API Audience: `evodox-api`
- Redirect URI(s): `https://app.evidox.local/*`
- Post Logout URI(s): `https://app.evidox.local/*`
- Web Origins: `https://app.evidox.local`

## 3) Security-Parameter
- Issuer URI(s):
  - dev: `https://keycloak.dev/realms/evodox`
  - stage: `https://keycloak.stage/realms/evodox`
  - prod: `https://keycloak.prod/realms/evodox`
- JWKS URI(s):
  - dev: `https://keycloak.dev/realms/evodox/protocol/openid-connect/certs`
  - stage: `https://keycloak.stage/realms/evodox/protocol/openid-connect/certs`
  - prod: `https://keycloak.prod/realms/evodox/protocol/openid-connect/certs`
- Access Token TTL: 10 Minuten
- Refresh Token TTL: 30 Minuten idle / 8 Stunden max
- Not Before / Revocation Policy: zentrale `not-before`-Steuerung; sofortige Token-Invalidierung bei Security-Incident
- Clock Skew: ±60 Sekunden
- Key Rotation Strategie: 24h JWKS-Refresh + sofortiger Fallback-Refetch bei unbekannter `kid`; Rollback über vorherigen Key innerhalb Wartungsfenster

## 4) Claim-Spezifikation
- `tenant_id` Quelle: Keycloak Protocol Mapper (single source of truth)
- Konfliktregel bei mehreren Tenant-Quellen: Hard-Deny (`403`), Audit-Event `authz.deny` mit `reason=ambiguous_tenant_claim`
- Rollenmapping (`user/reviewer/admin`): Realm-Rollen, tenant-lokal interpretiert
- Admin-Scope (tenant-lokal): bestätigt

## 5) JWT-Beispiele (Pflicht)
- `user` Tenant A: eingebracht
- `reviewer` Tenant A: eingebracht
- `admin` Tenant B: eingebracht

## 6) Session/Logout/MFA
- Session Idle Timeout: 30 Minuten
- Absolute Session Timeout: 8 Stunden
- Logout-Flow: RP-Initiated Logout + Frontend Session Clear + Token Revocation
- MFA/Step-up Regelung: verpflichtend für `admin`; optional für `user/reviewer` in Phase 1

## 7) Nicht-produktive Testzugänge
- Testnutzer Tenant A: `qa-user-a`, `qa-reviewer-a`, `qa-admin-a`
- Testnutzer Tenant B: `qa-user-b`, `qa-reviewer-b`, `qa-admin-b`
- Rollenabdeckung: vollständige Abdeckung `user/reviewer/admin` für beide Tenants

## 8) Offene Risiken + Zieltermine
| Risiko | Auswirkung | Gegenmaßnahme | Zieltermin | Owner |
|---|---|---|---|---|
| Fehlkonfiguration Redirect URIs | Token-Leak/Open Redirect Risiko | CI-Policy-Check auf Allowlist + Security Review vor Deploy | offen | offen |
| Verzögerte JWKS-Rotation in Stage | Temporäre Auth-Fehler (`401`) | Monitoring Alert auf `kid`-Mismatch + Runbook Drill | offen | offen |

## 9) Abstimmhinweise
- Dieses Dokument enthält bewusst keine personenbezogenen Sign-offs.
- Verbindliche Betriebsfreigaben werden außerhalb dieser Vorlage geführt.
