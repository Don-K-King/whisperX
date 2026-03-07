import unittest

from evodox.auth.context import AuthzError, authorize_request


class AuthorizeRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base_claims = {
            "sub": "u-1001",
            "tenant_id": "tenant-a",
            "roles": ["user"],
            "iss": "https://keycloak.prod/realms/evodox",
            "aud": "evodox-api",
            "exp": 2_000_000_000,
            "iat": 1_999_999_000,
            "nbf": 1_999_999_000,
        }

    def test_valid_claims_return_context(self):
        context = authorize_request(
            claims=self.base_claims,
            expected_issuer="https://keycloak.prod/realms/evodox",
            expected_audience="evodox-api",
            now=1_999_999_500,
            requested_tenant="tenant-a",
            required_roles={"user", "reviewer", "admin"},
        )

        self.assertEqual(context.actor_id, "u-1001")
        self.assertEqual(context.tenant_id, "tenant-a")
        self.assertEqual(context.roles, frozenset({"user"}))
        self.assertTrue(context.correlation_id)

    def test_missing_required_claim_is_401(self):
        claims = dict(self.base_claims)
        claims.pop("sub")

        with self.assertRaises(AuthzError) as exc_info:
            authorize_request(
                claims=claims,
                expected_issuer="https://keycloak.prod/realms/evodox",
                expected_audience="evodox-api",
                now=1_999_999_500,
            )

        self.assertEqual(exc_info.exception.status_code, 401)
        self.assertEqual(exc_info.exception.error_code, "auth.invalid_token")

    def test_missing_tenant_claim_is_403_default_deny(self):
        claims = dict(self.base_claims)
        claims.pop("tenant_id")

        with self.assertRaises(AuthzError) as exc_info:
            authorize_request(
                claims=claims,
                expected_issuer="https://keycloak.prod/realms/evodox",
                expected_audience="evodox-api",
                now=1_999_999_500,
            )

        self.assertEqual(exc_info.exception.status_code, 403)
        self.assertEqual(exc_info.exception.error_code, "authz.deny")

    def test_tenant_mismatch_is_403(self):
        with self.assertRaises(AuthzError) as exc_info:
            authorize_request(
                claims=self.base_claims,
                expected_issuer="https://keycloak.prod/realms/evodox",
                expected_audience="evodox-api",
                now=1_999_999_500,
                requested_tenant="tenant-b",
            )

        self.assertEqual(exc_info.exception.status_code, 403)
        self.assertEqual(exc_info.exception.error_code, "authz.deny")

    def test_expired_token_is_401(self):
        claims = dict(self.base_claims)
        claims["exp"] = 1_999_999_400

        with self.assertRaises(AuthzError) as exc_info:
            authorize_request(
                claims=claims,
                expected_issuer="https://keycloak.prod/realms/evodox",
                expected_audience="evodox-api",
                now=1_999_999_500,
            )

        self.assertEqual(exc_info.exception.status_code, 401)
        self.assertEqual(exc_info.exception.error_code, "auth.expired")

    def test_invalid_audience_is_401(self):
        claims = dict(self.base_claims)
        claims["aud"] = ["other-service"]

        with self.assertRaises(AuthzError) as exc_info:
            authorize_request(
                claims=claims,
                expected_issuer="https://keycloak.prod/realms/evodox",
                expected_audience="evodox-api",
                now=1_999_999_500,
            )

        self.assertEqual(exc_info.exception.status_code, 401)
        self.assertEqual(exc_info.exception.error_code, "auth.invalid_token")

    def test_missing_required_role_is_403(self):
        with self.assertRaises(AuthzError) as exc_info:
            authorize_request(
                claims=self.base_claims,
                expected_issuer="https://keycloak.prod/realms/evodox",
                expected_audience="evodox-api",
                now=1_999_999_500,
                required_roles={"admin"},
            )

        self.assertEqual(exc_info.exception.status_code, 403)
        self.assertEqual(exc_info.exception.error_code, "authz.deny")


if __name__ == "__main__":
    unittest.main()
