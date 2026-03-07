# Entwicklungsplan Referenz

**Single Point of Truth:** Der Entwicklungsplan wird ausschließlich in der Repository-Wurzel gepflegt: [`/Entwicklungs.md`](../../Entwicklungs.md).

Dieses Dokument enthält bewusst keine inhaltliche Duplizierung, um Divergenzen zwischen zwei Planständen zu vermeiden.

## Verbindliche Referenzstellen
- Vorgeschaltetes AuthN/AuthZ-Gate: Abschnitt „Verbindlicher vorgeschalteter Teilschritt 3A“ in `/Entwicklungs.md`.
- Nächster Realisierungsschritt: Abschnitt „Schritt 3: Auth + Upload Vertical Slice“ in `/Entwicklungs.md`.

## Planungsleitlinie bis Realisierungsphase
Eine separate, zweite Frontend-Spezifikation als neues Primärdokument wird nicht eingeführt.
Stattdessen gilt ein **Contract-Check Frontend ↔ API** gegen die bestehenden v1-Spezifikationen (`api-spec-v1`, `security-spec-v1`, `test-spec-v1`) als Pflicht vor Implementierungsstart.
