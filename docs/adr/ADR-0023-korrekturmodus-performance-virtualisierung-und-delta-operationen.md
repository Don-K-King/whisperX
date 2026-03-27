# ADR-0023: Korrekturmodus-Performance durch Virtualisierung und Delta-Operationen

## Status
Angenommen - 2026-03-27

## Kontext
Bei sehr grossen Transkripten (mehrere tausend Segmente) reagierte der Korrekturmodus traege bis hin zu UI-Haengern.
Haupttreiber waren:
- Voll-Render aller Segmentbloecke pro Render-Zyklus,
- Listener-Bindung pro Block/Textarea,
- lineare Segmentsuche bei Media-`timeupdate`,
- Vollpayload-`set_segments` bei Save/Autosave inklusive grosser JSON-Roundtrips.

Das betraf insbesondere lange Audio/Video-Dateien, weil haeufige Re-Renders den Media-Player zusaetzlich belasteten.

## Entscheidung
- Frontend nutzt Windowing/Virtualisierung fuer den Segment-Editor (nur sichtbarer Bereich + Overscan wird gerendert).
- Frontend stellt auf Event-Delegation im Editor um (keine Listener pro Segmentblock).
- Media-Sync wird entlastet:
  - aktive Segmentbestimmung per effizienterer Suche,
  - `timeupdate` zusaetzlich gedrosselt.
- Operations-API wird erweitert:
  - neue Delta-Operation `update_text {segment_id, text}`,
  - `return_mode` fuer Operations-Responses: `ack | changed_segments | full`,
  - Default fuer Operations-Endpoint: `changed_segments`.
- Frontend-Save/Autosave nutzt Delta-Operationen statt `set_segments` im Regelfall.

## Begruendung
- Virtualisierung reduziert DOM-/Layout-Last von O(n) auf O(visible).
- Event-Delegation reduziert Listener-Anzahl und Rebind-Kosten deutlich.
- Delta-Operationen reduzieren Request-/Response-Groesse und Main-Thread-Last durch `JSON.stringify/parse`.
- `return_mode=ack` fuer haeufige Textupdates minimiert Response-Payload.

## Konsequenzen
- API bleibt endpoint-kompatibel; Operations-Verhalten ist um `update_text` und `return_mode` erweitert.
- Frontend muss Session-Patches aus `changed_segments` korrekt in lokalen Zustand mergen.
- Undo/Redo/Discard/Commit bleiben fachlich unveraendert, profitieren aber von geringerer Last im Bearbeitungsfluss.
- Testabdeckung wird erweitert um:
  - `update_text`-Validierung und Diff-Metadaten,
  - HTTP-Mapping fuer `return_mode`,
  - FastAPI-Integration fuer `ack`/`changed_segments`.
