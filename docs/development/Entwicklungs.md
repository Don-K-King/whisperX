# Entwicklungsplan Referenz

**Single Point of Truth:** Der Entwicklungsplan wird ausschließlich in der Repository-Wurzel gepflegt: [`/Entwicklungs.md`](../../Entwicklungs.md).

Dieses Dokument enthält bewusst keine inhaltliche Duplizierung, um Divergenzen zwischen zwei Planständen zu vermeiden.

## Verbindliche Referenzstellen
- Vorgeschaltetes AuthN/AuthZ-Gate: Abschnitt „Verbindlicher vorgeschalteter Teilschritt 3A“ in `/Entwicklungs.md`.
- Nächster Realisierungsschritt: Abschnitt „Schritt 3: Auth + Upload Vertical Slice“ in `/Entwicklungs.md`.
- Ergänzende Frontend-Umsetzungsspezifikation: `docs/product/frontend-ui-spec-v1.md`.

## Planungsleitlinie bis Realisierungsphase
Die Frontend-Umsetzung wird über `docs/product/frontend-ui-spec-v1.md` konkretisiert; Primärquelle für Contracts bleiben die v1-Spezifikationen.
Verpflichtend gilt ein **Contract-Check Frontend ↔ API** gegen (`api-spec-v1`, `security-spec-v1`, `test-spec-v1`) vor Implementierungsstart.

- Verbindliche Ausführungsanweisung/Gates: `docs/development/implementation-playbook-v1.md`.
