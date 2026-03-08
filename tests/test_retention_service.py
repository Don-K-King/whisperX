from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from evodox.jobs.retention_service import (
    InMemoryRetentionAuditLog,
    InMemoryRetentionCandidateRepository,
    InMemoryRetentionExecutionRepository,
    RetentionCandidate,
    RetentionEnforcementJob,
    RetentionPolicyInputError,
    RetentionPolicyResolver,
)


class RetentionPolicyResolverTests(unittest.TestCase):
    def test_resolves_tenant_default_when_request_absent(self) -> None:
        resolver = RetentionPolicyResolver(global_min_months=1, global_max_months=36, tenant_defaults={"tenant-a": 9})

        result = resolver.resolve(tenant_id="tenant-a", requested_months=None)

        self.assertEqual(result.months, 9)
        self.assertEqual(result.source, "tenant_default")

    def test_clamps_manipulated_values_to_global_bounds(self) -> None:
        resolver = RetentionPolicyResolver(global_min_months=3, global_max_months=24, tenant_defaults={"tenant-a": 12})

        low = resolver.resolve(tenant_id="tenant-a", requested_months=-99)
        high = resolver.resolve(tenant_id="tenant-a", requested_months=999)

        self.assertEqual(low.months, 3)
        self.assertEqual(low.reason, "clamped_to_min")
        self.assertEqual(high.months, 24)
        self.assertEqual(high.reason, "clamped_to_max")

    def test_rejects_non_int_requested_months(self) -> None:
        resolver = RetentionPolicyResolver(global_min_months=1, global_max_months=12, tenant_defaults={})

        with self.assertRaises(RetentionPolicyInputError):
            resolver.resolve(tenant_id="tenant-a", requested_months="12")  # type: ignore[arg-type]


class RetentionEnforcementJobTests(unittest.TestCase):
    def test_enforces_retention_with_tenant_isolation_and_audit(self) -> None:
        now = datetime(2026, 3, 7, tzinfo=timezone.utc)
        candidate_repo = InMemoryRetentionCandidateRepository(
            {
                "tenant-a": [
                    RetentionCandidate(
                        tenant_id="tenant-a",
                        job_id="job-1",
                        requested_retention_months=6,
                        created_at=now - timedelta(days=220),
                    )
                ],
                "tenant-b": [
                    RetentionCandidate(
                        tenant_id="tenant-b",
                        job_id="job-2",
                        requested_retention_months=6,
                        created_at=now - timedelta(days=200),
                    )
                ],
            }
        )
        execution_repo = InMemoryRetentionExecutionRepository()
        audit = InMemoryRetentionAuditLog()
        resolver = RetentionPolicyResolver(global_min_months=1, global_max_months=36, tenant_defaults={})
        job = RetentionEnforcementJob(
            tenant_ids=["tenant-a"],
            candidate_repository=candidate_repo,
            execution_repository=execution_repo,
            policy_resolver=resolver,
            audit_log=audit,
            now_factory=lambda: now,
        )

        summary = job.run(batch_size=100)

        self.assertEqual(summary.processed, 1)
        self.assertEqual(summary.deleted, 1)
        self.assertEqual(summary.failed, 0)
        self.assertEqual([item[0] for item in execution_repo.deletions], ["tenant-a"])
        self.assertTrue(any(event["action"] == "retention.decision" for event in audit.events))
        self.assertTrue(any(event["action"] == "retention.execution" for event in audit.events))

    def test_clock_skew_guard_skips_recently_expired_candidate(self) -> None:
        now = datetime(2026, 3, 7, tzinfo=timezone.utc)
        candidate = RetentionCandidate(
            tenant_id="tenant-a",
            job_id="job-1",
            requested_retention_months=1,
            created_at=now - timedelta(days=30, minutes=2),
        )
        candidate_repo = InMemoryRetentionCandidateRepository({"tenant-a": [candidate]})
        execution_repo = InMemoryRetentionExecutionRepository()
        audit = InMemoryRetentionAuditLog()
        resolver = RetentionPolicyResolver(global_min_months=1, global_max_months=12, tenant_defaults={})
        job = RetentionEnforcementJob(
            tenant_ids=["tenant-a"],
            candidate_repository=candidate_repo,
            execution_repository=execution_repo,
            policy_resolver=resolver,
            audit_log=audit,
            now_factory=lambda: now,
            clock_skew_tolerance=timedelta(minutes=5),
        )

        summary = job.run(batch_size=10)

        self.assertEqual(summary.skipped, 1)
        self.assertEqual(summary.deleted, 0)
        self.assertEqual(len(execution_repo.deletions), 0)
        self.assertTrue(any(event["decision"] == "skip_clock_skew" for event in audit.events))

    def test_records_partial_failure_when_storage_deleted_but_db_mark_fails(self) -> None:
        now = datetime(2026, 3, 7, tzinfo=timezone.utc)
        candidate = RetentionCandidate(
            tenant_id="tenant-a",
            job_id="job-1",
            requested_retention_months=1,
            created_at=now - timedelta(days=40),
        )
        candidate_repo = InMemoryRetentionCandidateRepository({"tenant-a": [candidate]})
        execution_repo = InMemoryRetentionExecutionRepository(fail_db_for={"job-1"})
        audit = InMemoryRetentionAuditLog()
        resolver = RetentionPolicyResolver(global_min_months=1, global_max_months=12, tenant_defaults={})
        job = RetentionEnforcementJob(
            tenant_ids=["tenant-a"],
            candidate_repository=candidate_repo,
            execution_repository=execution_repo,
            policy_resolver=resolver,
            audit_log=audit,
            now_factory=lambda: now,
        )

        summary = job.run(batch_size=10)

        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.deleted, 0)
        self.assertTrue(any(event["action"] == "retention.execution.failed" for event in audit.events))

    def test_records_partial_failure_when_db_marked_but_storage_delete_fails(self) -> None:
        now = datetime(2026, 3, 7, tzinfo=timezone.utc)
        candidate = RetentionCandidate(
            tenant_id="tenant-a",
            job_id="job-1",
            requested_retention_months=1,
            created_at=now - timedelta(days=40),
        )
        candidate_repo = InMemoryRetentionCandidateRepository({"tenant-a": [candidate]})
        execution_repo = InMemoryRetentionExecutionRepository(fail_storage_for={"job-1"})
        audit = InMemoryRetentionAuditLog()
        resolver = RetentionPolicyResolver(global_min_months=1, global_max_months=12, tenant_defaults={})
        job = RetentionEnforcementJob(
            tenant_ids=["tenant-a"],
            candidate_repository=candidate_repo,
            execution_repository=execution_repo,
            policy_resolver=resolver,
            audit_log=audit,
            now_factory=lambda: now,
        )

        summary = job.run(batch_size=10)

        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.deleted, 0)
        self.assertTrue(any(event["action"] == "retention.execution.failed" for event in audit.events))


if __name__ == "__main__":
    unittest.main()
