# Keycloak-Integrationsprofil v1 (Schritt 3A Gate)

## Status
- **Dokumenttyp:** Verbindliches Sicherheits-/Integrationsprofil für AuthN/AuthZ.
- **Geltung:** Schritt 3A Gate vor Implementierungsstart von Schritt 3.
- **Freigabestatus:** In Prüfung, Sign-off ausstehend (siehe `docs/security/keycloak-integration-inputs-v1.md`).

## 1) Ziel und Scope
Dieses Profil definiert die technische Integration zwischen Frontend/API und Keycloak für OIDC Authorization Code + PKCE in Phase 1.

## 2) Realm- und Client-Modell
- Realm: `evodox`
- Clients:
  - `evodox-frontend` (public client, PKCE required)
  - `evodox-api` (resource server / bearer-only Validierung)
- Rollenmodell (tenant-lokal): `user`, `reviewer`, `admin`
- Kein globaler Root-Admin in Phase 1.

## 3) Umgebungsspezifische Parameter (verbindliche Struktur)
| Umgebung | Issuer | JWKS URI | Frontend Redirect URI(s) | Logout URI(s) | Web Origins | Audience |
|---|---|---|---|---|---|---|
| dev | `https://keycloak.dev/realms/evodox` | `https://keycloak.dev/realms/evodox/protocol/openid-connect/certs` | `https://app.dev.evidox.local/*` | `https://app.dev.evidox.local/*` | `https://app.dev.evidox.local` | `evodox-api` |
| stage | `https://keycloak.stage/realms/evodox` | `https://keycloak.stage/realms/evodox/protocol/openid-connect/certs` | `https://app.stage.evidox.local/*` | `https://app.stage.evidox.local/*` | `https://app.stage.evidox.local` | `evodox-api` |
| prod | `https://keycloak.prod/realms/evodox` | `https://keycloak.prod/realms/evodox/protocol/openid-connect/certs` | `https://app.evidox.local/*` | `https://app.evidox.local/*` | `https://app.evidox.local` | `evodox-api` |

## 4) Token- und Session-Policy
- Access Token TTL: 10 Minuten
- Refresh Token TTL: 30 Minuten idle / 8 Stunden max
- Allowed Clock Skew: ±60 Sekunden
- `nbf`, `iat`, `exp` sind verpflichtend zu prüfen
- Algorithmen: nur freigegebene Signaturalgorithmen gemäß Security-Baseline

## 5) Key Rotation und Recovery
- JWKS-Cache mit kurzer TTL und Fallback-Refetch bei unbekannter `kid`.
- Rotation-Runbook mit abgestimmtem Zeitfenster und Rollback-Prozedur.
- `not-before`-Strategie: zentral gesteuert, mit Audit-Event.

## 6) Claim-Mapping (Default Deny)
| Claim | Quelle | Pflicht | Nutzung |
|---|---|---|---|
| `sub` | Keycloak | Ja | `actor_id` |
| `tenant_id` | Token Claim | Ja | Tenant-Scoping in API/DB/Storage |
| `roles` | Realm/Client Roles | Ja | RBAC Entscheidung |
| `aud` | Token | Ja | API Audience-Prüfung |
| `iss` | Token | Ja | Issuer-Prüfung |
| `exp` | Token | Ja | Ablaufprüfung |

Regeln:
- Fehlender `tenant_id` → `403` (Default Deny).
- Mehrdeutige Tenant-Claims → `403` + Audit `authz.deny`.
- Rollen ohne passenden Tenant-Kontext sind ungültig.

## 7) Beispiel-JWT-Claims (strukturell)
### user (tenant-a)
```json
{
  "sub": "u-1001",
  "tenant_id": "tenant-a",
  "roles": ["user"],
  "iss": "https://keycloak.prod/realms/evodox",
  "aud": "evodox-api",
  "exp": 1770000000
}
```

### reviewer (tenant-a)
```json
{
  "sub": "u-2001",
  "tenant_id": "tenant-a",
  "roles": ["reviewer"],
  "iss": "https://keycloak.prod/realms/evodox",
  "aud": "evodox-api",
  "exp": 1770000000
}
```

### admin (tenant-b)
```json
{
  "sub": "u-3001",
  "tenant_id": "tenant-b",
  "roles": ["admin"],
  "iss": "https://keycloak.prod/realms/evodox",
  "aud": "evodox-api",
  "exp": 1770000000
}
```

## 8) Fehlerverhalten
- Token ungültig/abgelaufen/signaturfehlerhaft → `401`
- Token gültig, aber Scope/Rolle/Tenant unzulässig → `403`
- Antworten mit `correlation_id`, ohne interne Secrets/Stacktrace

## 9) Verifikation (Pflichttests)
- Integration: JWT/JWKS-Validierung (inkl. Rotation)
- Abuse: Claim-Manipulation, Cross-Tenant-Zugriffe, Replay
- Contract: konsistente `401/403` mit normiertem Fehlerobjekt

## 10) Sign-off
- Security Lead: ☐ offen
- API Lead: ☐ offen
- Keycloak Lead: ☐ offen
- Geplantes Sign-off-Datum: `YYYY-MM-DD`
