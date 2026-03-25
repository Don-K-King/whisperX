# ADR-0021: Korrekturmodus mit Session-basiertem Draft, Timeline-Guards und Final-Status

## Status
Angenommen - 2026-03-24

## Kontext
Der bisherige Transcript-Pfad deckte nur Voll-Updates und Speaker-Alias-Pflege ab. Fuer den Korrekturmodus werden undo/redo-faehige Draft-Bearbeitung, statusgefuehrte Pruefung und konsistente Timeline-Regeln benoetigt, ohne bestehende Versionierung zu brechen.

## Entscheidung
- Korrekturarbeit erfolgt in tenant-/actor-scoped Correction-Sessions (`transcript_correction_sessions`) mit Working-History und Pointer.
- Autosave speichert nur den Session-Draft, erzeugt keine neue persistierte Transcript-Version.
- Persistente Transcript-Versionen entstehen nur durch explizites Commit einer Session.
- Timeline-Invarianten werden fuer Session-Operationen durchgesetzt: keine Overlaps, keine Luecken, `start <= end`.
- Transcript-Status wird separat gefuehrt (`transcript_status`) mit `review_status` und `is_final`.
- Final bleibt bei Folgeedits bestehen; Folgeaenderungen bleiben ueber Session-/Audit-Events nachvollziehbar.

## Begruendung
- Session-History erlaubt deterministisches Undo/Redo und Verwerfen auf den letzten gespeicherten Stand.
- Draft-only Autosave reduziert Version-Churn und Konfliktrate.
- Separate Statusfuehrung entkoppelt fachliche Freigabe von Textversionen.
- Harte Timeline-Guards verhindern inkonsistente Sprecher-/Text-Operationen.

## Alternativen
- Autosave erzeugt jede Version: verworfen wegen hoher Versionflut.
- Kein Sessionmodell, nur direkte Version-Updates: verworfen wegen fehlendem Undo/Redo und schlechtem Review-UX.
- Final wird bei jeder Folgeaenderung automatisch entfernt: verworfen zugunsten expliziter Nachvollziehbarkeit mit stabilem Final-Marker.

## Konsequenzen
- API wurde um Session-Endpunkte (create/get/patch/apply/undo/redo/discard/commit) und Status-Endpoint erweitert.
- Frontend erhielt dedizierten Korrektur-Workspace mit Popup/New-Tab-Start ohne In-Tab-Fallback.
- Start-Handover nutzt kurzlebigen, single-use Store (TTL + sofortiger Consume) fuer tabuebergreifenden Start.
- Testumfang erweitert: Session-Lifecycle, Timeline-Abuse-Faelle, Status-/Final-Pfade.
