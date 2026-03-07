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
| Login | OIDC Flow (extern), geschützte API-Calls | Bearer Token, `tenant_id`, `roles` | `401`: Re-Login; `403`: Zugriff verweigert + Korrelation-ID | Default-Deny, tenant-scope aus Claim | Auth Abuse, Tenant-Isolation | open |
| Job anlegen | `POST /api/v1/jobs` | `filename`, `content_type`, `size_bytes`, `retention_months` | `422`: Validation inline; `413`: Datei zu groß; `429`: Retry-Hinweis | nur `user/reviewer/admin` im eigenen Tenant | Upload Validation + API Contract | open |
| Upload abschließen | `POST /api/v1/jobs/{id}/complete-upload` | `upload_session_id`, `object_key`, `checksum_sha256` | `409/422`: Upload inkonsistent; `403/404`: kein Leak über fremde IDs | idempotent, tenant-scoped | Idempotenz + Replay Abuse | open |
| Status anzeigen | `GET /api/v1/jobs/{id}` | `status`, `progress`, `retention_until` | `404`: neutral behandelt, keine Existenzinformation | tenant-scoped read only | Integration/E2E Tenant Tests | open |
| Audit-Ansicht | `GET /api/v1/audit` | Filter (`action`, `from`, `to`) und Eventfelder | `403`: Ansicht blockiert; kein Datenzugriff | nur `admin` tenant-lokal | RBAC/Tenant-Isolation | open |

## Offene Deltas (must-fix before implementation)
1. Exakter Polling-/Refresh-Vertrag für `progress` und mögliche `eta`-Semantik.
2. Einheitliche Fehlertextstrategie (`error_code`, `correlation_id`, sanitisiertes `detail`) für alle UI-Fehlerkomponenten.
3. Finale Festlegung der Frontend-Rate-Limit-UX für `429` und Retry-Backoff-Anzeige.

## Abnahme
- Keine offenen Deltas: ☐
- API Lead: ☐
- Frontend Lead: ☐
- Security Lead: ☐
- QA Lead: ☐
