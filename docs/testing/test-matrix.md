# Test Matrix

Die Matrix beschreibt die fachliche Abdeckung. Der Prozess steht in `test-strategy.md`, die Evidenz in `regression-log.md`.

| Anforderung | Unit | Integration | Contract | E2E | Security/Abuse | Prioritaet | Gate |
|---|---|---|---|---|---|---|---|
| OIDC Login + Rollen | Ja | Ja | Ja | Ja | Token Replay, Expiry, Audience/Issuer Mismatch | P0 | Muss gruen |
| Tenant-Isolation | Ja | Ja | Nein | Ja | Cross-Tenant Zugriff, Claim-Manipulation | P0 | Muss gruen |
| Upload grosser Dateien | Ja | Ja | Ja | Ja | MIME Spoofing, Chunk-Tampering, Oversize, Rate-Limit | P0 | Muss gruen |
| Queue/Retry/DLQ | Ja | Ja | Ja | Optional | Poison Messages, Duplicate Delivery, Retry-Storm | P0 | Muss gruen |
| Verarbeitung (ASR + Alignment + Diarization) | Nein | Ja | Nein | Ja | Malformed Media, Worker-Restart | P0 | Muss gruen |
| Transcript-Edit / Versionierung | Ja | Ja | Nein | Ja | XSS/Injection, Unicode Edge Cases | P1 | Muss gruen |
| Speaker-Alias + Blockbildung | Ja | Ja | Ja | Ja | Alias-Injection, Cross-Tenant, Control Characters, falsche Blockfusion | P1 | Muss gruen |
| Export (TXT/JSON/SRT/VTT) | Ja | Ja | Ja | Ja | Export-AuthZ, Format-Manipulation | P1 | Muss gruen |
| Retention + Audit | Ja | Ja | Nein | Optional | Manipulation `retention_months`, Audit-Vollstaendigkeit | P0 | Muss gruen |
| Prompt-Injection-Resilienz | Ja | Ja | Nein | Optional | Payloads bleiben Daten und duerfen keine Steuerlogik ausloesen | P0 | Muss gruen |
| On-Prem Docker Betrieb | Nein | Ja | Nein | Optional | Fehlkonfig, offene Ports, Secret-Leaks | P1 | Muss gruen |
| Korrekturmodus Virtualisierung + Seek + Autofokus | Ja | Ja | Ja | Ja | Empty-Window, Follow-Drift, stale forced ranges, ungueltige Timeline-Spruenge | P0 | Muss gruen |
| Dashboard/Jobdetail Progress-UI | Ja | Ja | Nein | Ja | Freeze, stale heartbeat, falsche 100%-Anzeige vor Abschluss | P1 | Muss gruen |

## Gate-Reihenfolge und Freigabenachweis
1. Lint/Schema-Validation
2. Unit
3. Integration
4. Contract
5. Security/Abuse
6. E2E/Regression bei Pipeline-, Build-, Architektur- oder Strukturveraenderungen

### Nachweispflicht pro Gate
- Verantwortliches Team
- Verwendete Testumgebung
- Commit SHA und Build-Artefakt
- Ergebnis und ggf. Risikoeinschaetzung

## Korrekturmodus-Matrix
| Anforderung | Unit | Integration | Contract | E2E | Security/Abuse | Prioritaet | Gate |
|---|---|---|---|---|---|---|---|
| Correction Sessions (Draft / Undo / Redo / Discard / Commit) | Ja | Ja | Ja | Ja | Session-Hijack, stale base_version, actor mismatch | P0 | Muss gruen |
| Timeline-Integritaet bei Korrekturen | Ja | Ja | Nein | Ja | Overlap/Gap Injection, invalid Char-Ranges | P0 | Muss gruen |
| Transcript-Status (`review_status`, `is_final`) | Ja | Ja | Ja | Ja | Unautorisierte Statusaenderung, Audit-Luecken | P1 | Muss gruen |
| Korrektur-Workspace (Popup/New-Tab, kein Fallback) | Ja | Ja | Nein | Ja | Popup-Blocker, handoff expiry, single-use misuse | P1 | Muss gruen |
| Suche/Ersetzen + Sprecherfilter | Ja | Ja | Nein | Ja | Replace-Missbrauch, no-match Fehlpfade | P1 | Muss gruen |

