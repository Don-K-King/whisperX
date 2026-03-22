# Schritt-3 Arbeitsnotizen zu Risiken und Abhängigkeiten v1

## Zweck
Diese Datei dient als technische Risiko-/Abhängigkeitsnotiz für die Umsetzung von Schritt 3 (WP-3.1 bis WP-3.4), ohne formale Gate- oder Freigabeentscheidung.

## Arbeitsrelevante Abhängigkeiten
- AuthN/AuthZ-Parameter aus `docs/security/keycloak-integration-profile-v1.md`
- Integrationsparameter aus `docs/security/keycloak-integration-inputs-v1.md`
- API-/Security-/Test-Contracts aus den v1-Spezifikationen

## Architektur- und Sicherheitsrisiken (laufend zu prüfen)
1. Tenant-Leak-Risiko bei uneinheitlicher Claim-Auswertung
2. Replay-/Duplicate-Risiko bei `complete-upload`
3. Informationsleck über Fehlerprofile (`401/403/404/422`)
4. Upload-Abuse bei unzureichender serverseitiger Validierung

## Maßnahmenlinie für die Umsetzung
- TDD-Reihenfolge WP-3.1 → WP-3.4 einhalten
- Threat→Control→Test-Mapping pro WP im jeweiligen PR dokumentieren
- Architekturabweichungen unmittelbar benennen und mit ADR absichern
