# Dokumentation Overview

Diese Seite ist der Navigator fuer die EvidoX-Dokumentation. Sie zeigt den empfohlenen Lesepfad und verweist auf die jeweilige Source of Truth.

## Lesepfad
1. Zuerst [../README.md](../README.md) lesen fuer Produktkontext und Einstieg.
2. Danach die fachliche Basis in Produkt, Architektur und Security lesen.
3. Fuer Umsetzung und Betrieb auf die Development-, Testing- und Operations-Dokumente wechseln.
4. Historische Step-Dokumente nur als Hintergrund verwenden, nicht als normativen Primartext.

## Themenbereiche

### Produkt
- [product/requirements.md](product/requirements.md)
- [product/phase1-fachliche-spezifikation-v1.md](product/phase1-fachliche-spezifikation-v1.md)
- [product/changelog.md](product/changelog.md)

### Architektur
- [architecture/system-context.md](architecture/system-context.md)
- [architecture/container-view.md](architecture/container-view.md)
- [architecture/data-flow.md](architecture/data-flow.md)
- [architecture/api-spec-v1.md](architecture/api-spec-v1.md)
- [architecture/data-model-v1.md](architecture/data-model-v1.md)
- [architecture/event-contracts-v1.md](architecture/event-contracts-v1.md)

### Security
- [security/security-spec-v1.md](security/security-spec-v1.md)
- [security/security-controls.md](security/security-controls.md)
- [security/threat-model.md](security/threat-model.md)
- [security/incident-response.md](security/incident-response.md)
- [security/keycloak-integration-profile-v1.md](security/keycloak-integration-profile-v1.md)
- [security/keycloak-integration-inputs-v1.md](security/keycloak-integration-inputs-v1.md)

### Testing
- [testing/test-strategy.md](testing/test-strategy.md)
- [testing/test-matrix.md](testing/test-matrix.md)
- [testing/test-spec-v1.md](testing/test-spec-v1.md)
- [testing/regression-log.md](testing/regression-log.md)
- [testing/frontend-api-contract-check-v1.md](testing/frontend-api-contract-check-v1.md)
- [testing/screenshots/](testing/screenshots/)

### Development
- [development/Entwicklungs.md](development/Entwicklungs.md)
- [development/roadmap.md](development/roadmap.md)
- [development/decisions-log.md](development/decisions-log.md)
- [development/implementation-playbook-v1.md](development/implementation-playbook-v1.md)

### Operations
- [operations/runbooks.md](operations/runbooks.md)
- [operations/monitoring-alerting.md](operations/monitoring-alerting.md)
- [operations/backup-restore.md](operations/backup-restore.md)

### ADR
- [adr/README.md](adr/README.md)
- einzelne ADRs in [adr/](adr/)

### Archiv
- [archive/README.md](archive/README.md)
- Historische Development-Step-Dokumente (siehe Archivrichtlinie)
- Historische Incident-Reports (siehe Archivrichtlinie)

## Source of Truth Regeln
- Architekturentscheidungen stehen in den ADRs und werden im Decisions Log nur kurz referenziert.
- API-Vertraege sind in `architecture/api-spec-v1.md` normativ.
- Status- und Datenmodell-Regeln werden nur in `architecture/data-model-v1.md` als primare Wahrheit gepflegt.
- Security-Regeln sind in `security/security-spec-v1.md` und `security/security-controls.md` normativ.
- Testing-Prozess und Abdeckung sind in `testing/test-strategy.md` und `testing/test-matrix.md` normativ.
- Operations-Schritte stehen in `operations/runbooks.md`; historische Incidents bleiben dort oder in separaten Reports, aber nicht als Ersatz fuer Runbooks.

## Was hier bewusst nicht dupliziert wird
- Keine vollstaendige Wiederholung von API-Schemata.
- Keine neuen Statusmodelle ausserhalb der Datenmodell-Doku.
- Keine operativen Step-by-Step-Drills ausser als Verweis.
- Keine alternativen Sicherheitsregeln neben den normativen Security-Dokumenten.

## Doku-Qualitaetsziel
- Ein Thema = ein normatives Hauptdokument.
- Historische oder schrittweise Dokumente bleiben als Nachvollziehbarkeit erhalten.
- Widersprueche sollen in ADRs oder den normativen Hauptdokumenten aufgeloest werden, nicht durch parallele Versionen.
