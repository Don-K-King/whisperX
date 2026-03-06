# Test Matrix (inkl. Edge-/Abuse-Schwerpunkte)

| Bereich | Unit | Integration | E2E | Security/Abuse | Regression Pflicht |
|---|---|---|---|---|---|
| Tenant-Isolation | Ja | Ja | Ja | Cross-Tenant Zugriff, Claim-Manipulation | Ja |
| Auth/OIDC | Ja | Ja | Ja | Token Replay, Expiry, Audience/Issuer Mismatch | Ja |
| Upload großer Dateien | Nein | Ja | Ja | MIME Spoofing, Chunk-Tampering, Oversize, Rate-Limit | Ja |
| Queue/Retry/DLQ | Ja | Ja | Optional | Poison Messages, Duplicate Delivery, Retry-Storm | Ja |
| Transcript-Edit/Export | Ja | Ja | Ja | XSS/Injection, Export-AuthZ, Unicode Edge Cases | Bei Architekturänderung |
| Prompt-Injection Resilienz | Ja | Ja | Optional | „Ignore instructions“-Payloads als Daten behandeln | Ja |
| Retention-Logik | Ja | Ja | Optional | Manipulation `retention_months`, Audit-Vollständigkeit | Ja |
| On-Prem Docker Betrieb | Nein | Ja | Optional | Fehlkonfig, offene Ports, Secret-Leaks | Ja |
