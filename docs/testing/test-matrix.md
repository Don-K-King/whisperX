# Test Matrix (inkl. Edge-/Abuse-Schwerpunkte)

| Anforderung | Unit | Integration | Contract | E2E | Security/Abuse | Priorität | Gate |
|---|---|---|---|---|---|---|---|
| OIDC Login + Rollen | Ja | Ja | Ja | Ja | Token Replay, Expiry, Audience/Issuer Mismatch | P0 | Muss grün |
| Tenant-Isolation | Ja | Ja | Nein | Ja | Cross-Tenant Zugriff, Claim-Manipulation | P0 | Muss grün |
| Upload großer Dateien | Ja | Ja | Ja | Ja | MIME Spoofing, Chunk-Tampering, Oversize, Rate-Limit | P0 | Muss grün |
| Queue/Retry/DLQ | Ja | Ja | Ja | Optional | Poison Messages, Duplicate Delivery, Retry-Storm | P0 | Muss grün |
| Verarbeitung (ASR+Alignment+Diarization) | Nein | Ja | Nein | Ja | Malformed Media, Worker-Restart | P0 | Muss grün |
| Transcript-Edit/Versionierung | Ja | Ja | Nein | Ja | XSS/Injection, Unicode Edge Cases | P1 | Muss grün |
| Export (TXT/JSON/SRT/VTT) | Ja | Ja | Ja | Ja | Export-AuthZ, Format-Manipulation | P1 | Muss grün |
| Retention + Audit | Ja | Ja | Nein | Optional | Manipulation `retention_months`, Audit-Vollständigkeit | P0 | Muss grün |
| Prompt-Injection-Resilienz | Ja | Ja | Nein | Optional | „Ignore instructions“-Payloads als Daten behandeln | P0 | Muss grün |
| On-Prem Docker Betrieb | Nein | Ja | Nein | Optional | Fehlkonfig, offene Ports, Secret-Leaks | P1 | Muss grün |


## Gate-Reihenfolge und Freigabenachweis
1. Lint/Schema-Validation
2. Unit
3. Integration
4. Contract
5. Security/Abuse
6. E2E/Regression (verpflichtend bei Pipeline/Build/Architektur/Strukturänderungen)

### Nachweispflicht pro Gate
- Verantwortliches Team
- Verwendete Testumgebung
- Commit SHA und Build-Artefakt
- Ergebnis (Pass/Fail) und ggf. Risikoeinschätzung
