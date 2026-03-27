# Test Strategy (TDD)

Verbindliche Freeze-Referenz: `docs/testing/test-spec-v1.md`.

## 1) Rollen der Testdoku
- `test-strategy.md` beschreibt den Prozess und die Gates.
- `test-matrix.md` beschreibt die fachliche Abdeckung.
- `regression-log.md` beschreibt die ausgefuhrten Nachweise und Resultate.

## 2) Verbindlicher Ablauf je Arbeitspaket
1. Akzeptanzkriterien und Security-Akzeptanzkriterien festlegen.
2. Edge-Case-Katalog fuer das Paket definieren.
3. Failing Tests zuerst schreiben (Red).
4. Minimal implementieren (Green).
5. Refactor ohne Verhaltensaenderung.
6. Security-Review und Doku-Update als DoD-Pflicht.

## 3) Testebenen
- Unit: Business-Regeln, Tenant-Scoping, Retention, Statuswechsel, Validatoren.
- Integration: API-DB, API-Queue, Worker-Storage, Auth-Flow gegen Keycloak-Testumgebung.
- Contract: API- und Event-Schema-Tests.
- E2E: Upload -> Queue -> Verarbeitung -> Edit -> Export.
- Security/Abuse: AuthZ-Bypass, Rate-Limit-Evasion, Payload-Manipulation, Prompt-Injection-Resilienz.

## 4) Globaler Edge-/Abuse-Katalog
- Prompt-Injection/Instruction-Injection:
  - Transkript- und Metadateninhalte mit Mustern wie `ignore previous instructions`, Script-Tags oder Command-Strings duerfen keine privilegierten Aktionen ausloesen.
  - Inhalte werden immer als Daten behandelt, nie als Steueranweisung.
- Rate-Limiting und Abuse:
  - Burst- und Sustained-Traffic-Tests pro Tenant, Benutzer und IP.
  - Retry-Stuerme duerfen System oder Worker nicht destabilisieren.
- Unkonventionelle Eingaben:
  - Sehr lange Dateinamen, Unicode/RTL, Nullbytes, doppelte Extensions, ungueltige MIME-Header.
  - Korruptes Media, unvollstaendige Chunks, Out-of-order Chunks.
- Eingabevalidierung:
  - Schema-Validation fuer API-Inputs und Parameter-Whitelists.
  - Path Traversal, SQLi-/NoSQLi-Muster, Header Injection und JSON Bombs.

## 5) Entwicklungsschritt-spezifische Testlogik
- Architektur- und Governance-Festlegung:
  - DoR: Security- und Testanforderungen pro Komponente dokumentiert.
  - Tests: Dokumentations-Qualitaetschecks auf Vollstaendigkeit und Konsistenz.
- Repo-/Infra-Struktur:
  - Integration: Container-Netzwerk, Secrets-Mounts, Healthchecks.
  - Edge/Security: Fehlkonfigurationen, offene Ports und Default-Passwoerter muessen fehlschlagen.
- Auth + Upload:
  - Integration/E2E: OIDC Login, Tenant-Claims, Token-Expiry/Refresh, Chunked Upload.
  - Edge/Security: Cross-Tenant IDs, Claim-Manipulation, MIME-Spoofing, Oversize, ungueltige Chunks.
- Processing Pipeline:
  - Integration: Queue-Routing, Retry/Backoff/DLQ, lange Jobs unter Last.
  - Edge/Security: Poison Messages, Duplicate Delivery, Worker-Restart-Recovery, Tenant-Fairness.
- Transcript Edit + Export:
  - E2E: Versionierung, optimistic locking, Export-Erzeugung.
  - Edge/Security: XSS/HTML-Injection, Unicode-/Control-Character-Faelle, Export-AuthZ.
- Retention, Compliance, Betriebshaertung:
  - Integration: Default- und Override-Policy, Loeschjobs, Audit-Nachweis.
  - Edge/Security: Manipulationen an Retention-Werten, Restore-Konsistenz, Incident-Drills.

## 6) Screenshot-Governance fuer UI- und Interaktionsaenderungen
- Pflichtpfad fuer Artefakte: `docs/testing/screenshots/`.
- Namensschema: `<screen>-<state>.png`, zum Beispiel `correction-shell-default.png`.
- Pflichtzustand pro UI-Aenderung:
  - Default-Zustand.
  - Fehler- oder Validierungszustand.
  - Responsive Zustand, wenn Layout oder Interaktion betroffen ist.
- Wenn ein Screenshot technisch nicht erzeugbar ist, muss der Grund im Regression-Log stehen und die Reproduktionsschritte muessen genannt werden.
- Es duerfen nur referenzierende Hinweise in der Testdoku stehen; die eigentlichen Bildnachweise bleiben in `regression-log.md`.

## 7) Regression-Gates
- Vollstaendige Regression bei Aenderungen an Pipeline, Build, Architektur, Mandantenmodell und Queueing.
- Fuer reine Doku-Aenderungen keine Runtime-Regression, aber Konsistenzchecks der Doku sind verpflichtend.

## 8) Freeze-Gates fuer Implementierungsstart
- Keine offenen Muss-Anforderungen.
- API-Operationen vollstaendig mit AuthZ, Tenant und Validierung dokumentiert.
- Datenentitaeten vollstaendig mit Retention- und Audit-Regeln dokumentiert.
- Kritische Risiken mit Gegenmassnahmen und Testfaellen hinterlegt.

## 9) Gate-Profile je Entwicklungsschritt
- Schritt 3 Auth + Upload: Lint/Schema, Unit, Integration, Contract, Security/Abuse.
- Schritt 4 Pipeline + Queue + Worker: Lint/Schema, Unit, Integration, Contract, Security/Abuse, Regression.
- Schritt 5 Edit + Export: Lint/Schema, Unit, Integration, Contract, Security/Abuse, E2E.
- Schritt 6 Retention + Compliance: Lint/Schema, Unit, Integration, Security/Abuse, E2E/Operations-Drills, Regression.

