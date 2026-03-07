# Keycloak-Integration Inputs v1 (Schritt 3A Vorlage)

## Status
- **Dokumenttyp:** Verbindliche Abstimmungsvorlage für Schritt 3A.
- **Nutzung:** Muss vollständig ausgefüllt und signiert sein, bevor Schritt 3 startet.

## 1) Metadaten
- Owner Security:
- Owner API:
- Owner IAM/Keycloak:
- SLA Auth-Service:
- Letzte Aktualisierung:

## 2) Realm/Client-Parameter je Umgebung
### dev
- Realm:
- Frontend Client-ID:
- API Audience:
- Redirect URI(s):
- Post Logout URI(s):
- Web Origins:

### stage
- Realm:
- Frontend Client-ID:
- API Audience:
- Redirect URI(s):
- Post Logout URI(s):
- Web Origins:

### prod
- Realm:
- Frontend Client-ID:
- API Audience:
- Redirect URI(s):
- Post Logout URI(s):
- Web Origins:

## 3) Security-Parameter
- Issuer URI(s):
- JWKS URI(s):
- Access Token TTL:
- Refresh Token TTL:
- Not Before / Revocation Policy:
- Clock Skew:
- Key Rotation Strategie:

## 4) Claim-Spezifikation
- `tenant_id` Quelle:
- Konfliktregel bei mehreren Tenant-Quellen:
- Rollenmapping (`user/reviewer/admin`):
- Admin-Scope (tenant-lokal): bestätigt ☐

## 5) JWT-Beispiele (Pflicht)
- `user` Tenant A: eingebracht ☐
- `reviewer` Tenant A: eingebracht ☐
- `admin` Tenant B: eingebracht ☐

## 6) Session/Logout/MFA
- Session Idle Timeout:
- Absolute Session Timeout:
- Logout-Flow:
- MFA/Step-up Regelung:

## 7) Nicht-produktive Testzugänge
- Testnutzer Tenant A:
- Testnutzer Tenant B:
- Rollenabdeckung:

## 8) Offene Risiken + Zieltermine
| Risiko | Auswirkung | Gegenmaßnahme | Zieltermin | Owner |
|---|---|---|---|---|
| | | | | |

## 9) Sign-off (Gate)
- Keycloak-Team Sign-off (Name/Datum):
- API-Team Sign-off (Name/Datum):
- Security-Team Sign-off (Name/Datum):
- Gate-Status: ☐ offen / ☐ freigegeben
