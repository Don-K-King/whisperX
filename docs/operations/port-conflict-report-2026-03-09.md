# Port-Konfliktanalyse Zielinstanz vs. EvidoX Deploy-Compose (2026-03-09)

## Eingangslage
Auf der Zielinstanz sind folgende **Host-Ports bereits belegt** (gemäss `docker ps`):
- `80`, `443` (Reverse Proxy)
- `3000`, `3001` (Open WebUI)
- `4123` (Chatterbox TTS)
- `4321` (Frontend)
- `8080` (Keycloak)

Weitere Container-Ports ohne Host-Publish (intern) wurden ebenfalls gemeldet, z. B. `5000`, `8000`, `9000-9001`, `11434`.

## Analyse der Repository-Konfiguration
Datei: `deploy/docker-compose.target.yml`.

- Das Compose-File veröffentlicht standardmäßig **keine Host-Ports** (`ports:` fehlt bewusst).
- Es nutzt jedoch interne Service-Ports für Healthchecks und Service-zu-Service-Kommunikation.
- Vor der Anpassung waren dies:
  - Keycloak intern auf `8080`
  - API intern auf `8000`

## Konfliktbewertung
- **Direkter Host-Port-Konflikt:** aktuell nicht vorhanden (kein Host-Publish in Compose).
- **Architektur-/Betriebsrisiko:** Wenn künftig `ports:` ergänzt oder `network_mode: host` verwendet wird, würden `8080` und ggf. `8000` mit bestehender Zielinstanz kollidieren.

## Umgesetzte Anpassung (Konfliktprävention)
- Keycloak intern auf `18080` umgestellt (`start-dev --http-port=18080`).
- API intern auf `18000` umgestellt (`uvicorn --port 18000`).
- Healthchecks und lokale ENV-Referenzen entsprechend aktualisiert.

## Security-/Betriebsimplikationen
- Keine zusätzliche Angriffsfläche: Es wurden weiterhin **keine Host-Port-Mappings** aktiviert.
- Geringeres Fehlkonfigurationsrisiko bei späteren Betriebsänderungen (z. B. versehentliches Port-Publish).
- Tenant-/AuthN/AuthZ-Logik unverändert; nur interne Netz-Ports angepasst.
