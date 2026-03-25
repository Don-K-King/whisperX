# ADR-0019: Versionierte Speaker-Aliase und Blockbildung in der Transcript-Ansicht

## Status
Angenommen - 2026-03-22

## Kontext
In der Task View werden Transcript-Segmente aktuell einzeln dargestellt. Das erschwert die Lesbarkeit, wenn mehrere aufeinanderfolgende Segmente denselben Speaker haben. Zusaetzlich fehlt eine persistente Moeglichkeit, technische Speaker-Labels wie `SPEAKER_01` in fachliche Bezeichnungen wie `Patrick` umzubenennen, ohne die Reproduzierbarkeit von Versionen und Exporten zu verlieren.

## Entscheidung
- Speaker-Aliase werden pro `tenant_id`, `job_id` und `transcript_version` als Snapshot gespeichert.
- Die Transcript-Ansicht gruppiert aufeinanderfolgende Segmente mit gleichem Roh-Speaker zu einem Block.
- Der Block-Header zeigt den Alias, falls vorhanden, sonst das Roh-Label.
- Eine Alias-Aenderung erzeugt eine neue Transcript-Version mit identischem Segmentinhalt und neuem Alias-Snapshot.
- Der neue Schreibpfad ist tenant-scoped und verwendet Optimistic Locking ueber `base_version`.
- Export und UI lesen Alias-Snapshots versioniert aus, damit Anzeige und Export reproduzierbar bleiben.

## Begruendung
- Die Blockbildung verbessert die Lesbarkeit ohne fachliche Information zu verlieren.
- Versionierte Aliase verhindern Lost Updates und halten historische Exporte nachvollziehbar.
- Eine Speicherung nur im Browser oder nur als Laufzeit-Mapping wuerde Reproduzierbarkeit und Multi-Device-Nutzung brechen.
- Tenant- und Versionsbezug schliesst Cross-Tenant- und Cross-Version-Leaks aus.

## Alternativen
- Nur Frontend-Mapping ohne Persistenz: abgelehnt, weil Export und andere Clients dann inkonsistent waeren.
- Globales Job-Mapping ohne Versionierung: abgelehnt, weil alte Versionen dann nachtraeglich umgedeutet wuerden.
- Vollstaendiges Umschreiben aller Segment-Speaker: abgelehnt, weil Rohdaten und Alias dann vermischt wuerden.

## Konsequenzen
- Die API benoetigt einen separaten Schreibpfad fuer Speaker-Aliase.
- Das Datenmodell muss Alias-Snapshots pro Transcript-Version speichern.
- Frontend- und Export-Logik muessen Blockbildung und Alias-Fallback identisch umsetzen.
- Sicherheits- und Abuse-Tests muessen Alias-Input, Tenant-Isolation und HTML-Escaping abdecken.
