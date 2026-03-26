# ADR-0022: Korrekturmodus mit absoluter Timeline ohne Seed-Kompaktierung

## Status
Angenommen - 2026-03-26

## Kontext
Im Korrekturmodus wurden Session-Seeds bei Timeline-Luecken kompaktiert. Dadurch wurden Pausen aus der Zeitachse entfernt und Segmentzeiten gegenueber der Original-Medienzeit verschoben. Die Abweichung wuchs mit der Gesamtdauer bzw. der kumulierten Pausenlaenge.

Fuer Review, Audio/Video-Sync und Export muss der Korrekturmodus dieselbe absolute Timeline wie die persistierte Transcript-Version verwenden.

## Entscheidung
- Session-Seed uebernimmt `start/end` unveraendert aus der Transcript-Version.
- Seed-Kompaktierung bei Timeline-Luecken wird entfernt.
- Timeline-Invarianten im Korrekturpfad werden wie folgt definiert:
  - keine Overlaps,
  - monotone Chronologie,
  - `start <= end`,
  - nur finite Zeitwerte (`NaN`/`inf` ungueltig),
  - Luecken sind erlaubt.
- `set_segments` akzeptiert Timeline-Luecken, lehnt Overlaps und ungueltige Zeitwerte weiterhin ab.
- Frontend-Block-Merge im Korrekturworkspace erfolgt nur fuer kontiguierliche Segmente mit gleichem Speaker.

## Begruendung
- Korrektur muss an die Original-Medienzeit gebunden bleiben, sonst entstehen systematische Drift-Effekte.
- Luecken sind fachlich korrekt (Pausen, VAD-Segmente) und duerfen nicht als Inkonsistenz behandelt werden.
- Die neue Invariante verhindert weiterhin fehlerhafte Segmentierung (Overlaps, ungueltige Zeitwerte), ohne reale Pausen zu zerstoeren.

## Konsequenzen
- API-Verhalten bleibt kompatibel auf Endpoint-Ebene, aendert sich aber semantisch: Timeline-Luecken sind im Korrekturpfad valide.
- Bereits historisch kompaktierte Drafts/Versionen bleiben unveraendert (fix-forward).
- In internen Timeline-Luecken kann bewusst "kein aktiver Block" markiert werden.
- Testabdeckung wird um Gap-Preservation, Overlap-Reject und finite-Timeline-Checks erweitert.
