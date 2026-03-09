from __future__ import annotations

from pathlib import Path
import unittest


class TargetPortAllocationTests(unittest.TestCase):
    def test_compose_uses_non_conflicting_service_ports(self) -> None:
        compose = Path("deploy/docker-compose.target.yml").read_text(encoding="utf-8")

        self.assertIn('"--http-port=18080"', compose)
        self.assertIn('http://localhost:18080/health/ready', compose)
        self.assertIn('"--port", "18000"', compose)
        self.assertIn('http://localhost:18000/docs', compose)

    def test_env_examples_reference_auth_internal_port_18080(self) -> None:
        env_example = Path(".env.example").read_text(encoding="utf-8")
        env_prod = Path(".env.production.example").read_text(encoding="utf-8")

        self.assertIn("API_AUTH_ISSUER=http://auth:18080/realms/evodox", env_example)
        self.assertIn("API_AUTH_ISSUER=https://auth.example.com/realms/evodox", env_prod)


if __name__ == "__main__":
    unittest.main()
