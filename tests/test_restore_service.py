from __future__ import annotations

import unittest

from evodox.jobs.restore_service import (
    InMemoryRestoreAuditLog,
    InMemoryRestoreRepository,
    InMemoryTenantGraphRepository,
    RestoreConsistencyChecker,
    RestoreExecutionInput,
    RestoreValidationError,
    execute_restore,
)


class RestoreServiceTests(unittest.TestCase):
    def test_restore_rejects_cross_tenant_payload(self) -> None:
        repo = InMemoryRestoreRepository()
        graph = InMemoryTenantGraphRepository()
        audit = InMemoryRestoreAuditLog()

        with self.assertRaises(RestoreValidationError) as ctx:
            execute_restore(
                RestoreExecutionInput(
                    tenant_id="tenant-b",
                    backup_id="bck-1",
                    tables=["jobs"],
                    object_keys=["tenant/tenant-b/job-1/audio.wav"],
                ),
                tenant_id="tenant-a",
                actor_id="admin-1",
                restore_repository=repo,
                graph_repository=graph,
                audit_log=audit,
            )
        self.assertEqual(ctx.exception.error_code, "restore.tenant_mismatch")

    def test_restore_enforces_tenant_scoped_object_keys(self) -> None:
        repo = InMemoryRestoreRepository()
        graph = InMemoryTenantGraphRepository()
        audit = InMemoryRestoreAuditLog()

        with self.assertRaises(RestoreValidationError) as ctx:
            execute_restore(
                RestoreExecutionInput(
                    tenant_id="tenant-a",
                    backup_id="bck-1",
                    tables=["jobs"],
                    object_keys=["tenant/tenant-b/job-1/audio.wav"],
                ),
                tenant_id="tenant-a",
                actor_id="admin-1",
                restore_repository=repo,
                graph_repository=graph,
                audit_log=audit,
            )
        self.assertEqual(ctx.exception.error_code, "restore.object_scope_invalid")

    def test_restore_executes_defined_order_and_passes_consistency_check(self) -> None:
        repo = InMemoryRestoreRepository()
        graph = InMemoryTenantGraphRepository(
            jobs={"job-1"},
            transcript_job_links={"job-1"},
            export_job_links={"job-1"},
            audit_job_links={"job-1"},
        )
        audit = InMemoryRestoreAuditLog()

        result = execute_restore(
            RestoreExecutionInput(
                tenant_id="tenant-a",
                backup_id="bck-2",
                tables=["transcript_versions", "jobs", "export_artifacts", "transcripts", "audit_events"],
                object_keys=["tenant/tenant-a/job-1/export.srt"],
            ),
            tenant_id="tenant-a",
            actor_id="admin-1",
            restore_repository=repo,
            graph_repository=graph,
            audit_log=audit,
        )

        self.assertEqual(
            repo.table_restores,
            [
                ("tenant-a", "bck-2", "jobs"),
                ("tenant-a", "bck-2", "transcripts"),
                ("tenant-a", "bck-2", "transcript_versions"),
                ("tenant-a", "bck-2", "export_artifacts"),
                ("tenant-a", "bck-2", "audit_events"),
            ],
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.consistency_issues, [])
        self.assertTrue(any(evt["action"] == "restore.completed" for evt in audit.events))

    def test_restore_reports_consistency_violations(self) -> None:
        repo = InMemoryRestoreRepository()
        graph = InMemoryTenantGraphRepository(
            jobs={"job-1"},
            transcript_job_links={"job-1", "job-missing"},
            export_job_links={"job-1"},
            audit_job_links={"job-1", "job-missing"},
        )
        audit = InMemoryRestoreAuditLog()

        result = execute_restore(
            RestoreExecutionInput(
                tenant_id="tenant-a",
                backup_id="bck-3",
                tables=["jobs", "transcripts", "audit_events"],
                object_keys=[],
            ),
            tenant_id="tenant-a",
            actor_id="admin-1",
            restore_repository=repo,
            graph_repository=graph,
            audit_log=audit,
        )

        self.assertEqual(result.status, "completed_with_findings")
        self.assertGreaterEqual(len(result.consistency_issues), 1)
        self.assertTrue(any(issue.error_code == "restore.consistency.missing_job_reference" for issue in result.consistency_issues))


if __name__ == "__main__":
    unittest.main()
