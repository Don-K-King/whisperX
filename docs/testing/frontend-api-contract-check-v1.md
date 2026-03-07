# Frontend ↔ API Contract-Check v1 (Phase 1)

## Zweck
Verifizierbarer Nachweis, dass Frontend-Flows mit den bindenden API-/Security-/Test-Spezifikationen konsistent sind.

## Referenzen
- `docs/architecture/api-spec-v1.md`
- `docs/security/security-spec-v1.md`
- `docs/testing/test-spec-v1.md`
- `docs/testing/test-matrix.md`
- `docs/product/frontend-ui-spec-v1.md`

## Mapping-Matrix
| UI-Flow | Endpoint(s) | Payload/Response Kernfelder | Fehlercodes & UI-Behandlung | Tenant/AuthZ Verhalten | Test-Referenz | Status |
|---|---|---|---|---|---|---|
| Login | OIDC Flow (extern), geschützte API-Calls | Bearer Token, `tenant_id`, `roles` | `401`: Re-Login; `403`: Zugriff verweigert + Korrelation-ID | Default-Deny, tenant-scope aus Claim | Auth Abuse, Tenant-Isolation | signed |
| Job anlegen | `POST /api/v1/jobs` | `filename`, `content_type`, `size_bytes`, `retention_months` | `422`: Validation inline; `413`: Datei zu groß; `429`: Retry-Hinweis mit Backoff | nur `user/reviewer/admin` im eigenen Tenant | Upload Validation + API Contract | signed |
| Upload abschließen | `POST /api/v1/jobs/{id}/complete-upload` | `upload_session_id`, `object_key`, `checksum_sha256` | `409/422`: Upload inkonsistent; `403/404`: kein Leak über fremde IDs | idempotent, tenant-scoped | Idempotenz + Replay Abuse | signed |
| Status anzeigen | `GET /api/v1/jobs/{id}` | `status`, `progress`, `retention_until`, optional `eta_seconds` | `404`: neutral behandelt, keine Existenzinformation | tenant-scoped read only | Integration/E2E Tenant Tests | signed |
| Audit-Ansicht | `GET /api/v1/audit` | Filter (`action`, `from`, `to`) und Eventfelder | `403`: Ansicht blockiert; kein Datenzugriff | nur `admin` tenant-lokal | RBAC/Tenant-Isolation | signed |

## Delta-Auflösung (must-fix geschlossen)
1. **Progress/Polling-Vertrag finalisiert**
   - Pollingintervall Frontend: 5 Sekunden (exponentielles Backoff bis max. 30 Sekunden bei `429`).
   - API liefert `progress` (0..100) und optional `eta_seconds` wenn berechenbar.
2. **Einheitliche Fehlertextstrategie finalisiert**
   - Pflichtfelder in allen Fehlerantworten: `type`, `title`, `status`, `error_code`, `correlation_id`.
   - `detail` bleibt sanitisiert und enthält keine internen Stacktraces.
3. **Rate-Limit UX (`429`) finalisiert**
   - UI zeigt Retry-Hinweis inkl. Backoff-Zeit und übernimmt serverseitigen `Retry-After` wenn vorhanden.

## Abnahme
- Keine offenen Deltas: ☑
- API Lead: bestätigt
- Frontend Lead: bestätigt
- Security Lead: bestätigt
- QA Lead: bestätigt
