import unittest

from evodox.jobs.worker_pipeline_service import (
    InMemoryArtifactStore,
    InMemoryJobStateStore,
    InMemoryWorkerAuditLog,
    RetryableWorkerError,
    TerminalWorkerError,
    WorkerPipeline,
    WorkerProcessInput,
)


class WorkerPipelineTests(unittest.TestCase):
    def test_happy_path_processes_job_and_persists_tenant_scoped_artifact(self):
        jobs = InMemoryJobStateStore(
            {
                ("tenant-a", "job_1"): {
                    "tenant_id": "tenant-a",
                    "job_id": "job_1",
                    "status": "queued",
                    "object_key": "tenant/tenant-a/job_1/audio.wav",
                }
            }
        )
        artifacts = InMemoryArtifactStore()
        audit = InMemoryWorkerAuditLog()
        pipeline = WorkerPipeline(
            job_store=jobs,
            artifact_store=artifacts,
            audit_log=audit,
            asr_engine=lambda object_key: {"text": "hello"},
            align_engine=lambda transcript: {"segments": [{"start": 0.0, "end": 1.0, "text": transcript["text"]}]},
            diarize_engine=lambda aligned: {"speakers": [{"speaker": "spk_1", "segments": aligned["segments"]}]},
        )

        result = pipeline.process(WorkerProcessInput(tenant_id="tenant-a", job_id="job_1"))

        self.assertEqual(result.status, "completed")
        self.assertEqual(jobs.get("tenant-a", "job_1")["status"], "completed")
        artifact = artifacts.get("tenant-a", "job_1")
        self.assertIsNotNone(artifact)
        self.assertEqual(artifact["tenant_id"], "tenant-a")
        self.assertEqual(len(audit.events), 2)

    def test_malformed_media_is_terminal_and_does_not_retry(self):
        jobs = InMemoryJobStateStore(
            {
                ("tenant-a", "job_bad"): {
                    "tenant_id": "tenant-a",
                    "job_id": "job_bad",
                    "status": "queued",
                    "object_key": "tenant/tenant-a/job_bad/audio.xyz",
                }
            }
        )
        artifacts = InMemoryArtifactStore()
        audit = InMemoryWorkerAuditLog()
        pipeline = WorkerPipeline(
            job_store=jobs,
            artifact_store=artifacts,
            audit_log=audit,
            asr_engine=lambda object_key: (_ for _ in ()).throw(TerminalWorkerError("media.malformed")),
            align_engine=lambda transcript: transcript,
            diarize_engine=lambda aligned: aligned,
        )

        result = pipeline.process(WorkerProcessInput(tenant_id="tenant-a", job_id="job_bad"))

        self.assertEqual(result.status, "failed_terminal")
        self.assertEqual(result.error_code, "media.malformed")
        self.assertEqual(jobs.get("tenant-a", "job_bad")["status"], "failed_terminal")
        self.assertIsNone(artifacts.get("tenant-a", "job_bad"))


    def test_rejects_non_tenant_scoped_object_key(self):
        jobs = InMemoryJobStateStore(
            {
                ("tenant-a", "job_x"): {
                    "tenant_id": "tenant-a",
                    "job_id": "job_x",
                    "status": "queued",
                    "object_key": "tenant/tenant-b/job_x/audio.wav",
                }
            }
        )
        pipeline = WorkerPipeline(
            job_store=jobs,
            artifact_store=InMemoryArtifactStore(),
            audit_log=InMemoryWorkerAuditLog(),
            asr_engine=lambda object_key: {"text": "never"},
            align_engine=lambda transcript: transcript,
            diarize_engine=lambda aligned: aligned,
        )

        result = pipeline.process(WorkerProcessInput(tenant_id="tenant-a", job_id="job_x"))

        self.assertEqual(result.status, "failed_terminal")
        self.assertEqual(result.error_code, "job.object_key_scope_violation")

    def test_transient_processing_error_sets_failed_retryable(self):
        jobs = InMemoryJobStateStore(
            {
                ("tenant-a", "job_retry"): {
                    "tenant_id": "tenant-a",
                    "job_id": "job_retry",
                    "status": "queued",
                    "object_key": "tenant/tenant-a/job_retry/audio.wav",
                }
            }
        )
        pipeline = WorkerPipeline(
            job_store=jobs,
            artifact_store=InMemoryArtifactStore(),
            audit_log=InMemoryWorkerAuditLog(),
            asr_engine=lambda object_key: (_ for _ in ()).throw(RetryableWorkerError("worker.timeout")),
            align_engine=lambda transcript: transcript,
            diarize_engine=lambda aligned: aligned,
        )

        result = pipeline.process(WorkerProcessInput(tenant_id="tenant-a", job_id="job_retry"))

        self.assertEqual(result.status, "failed_retryable")
        self.assertEqual(jobs.get("tenant-a", "job_retry")["status"], "failed_retryable")

    def test_milestone_progress_is_updated_during_processing(self):
        jobs = InMemoryJobStateStore(
            {
                ("tenant-a", "job_progress"): {
                    "tenant_id": "tenant-a",
                    "job_id": "job_progress",
                    "status": "queued",
                    "object_key": "tenant/tenant-a/job_progress/audio.wav",
                }
            }
        )
        artifacts = InMemoryArtifactStore()
        audit = InMemoryWorkerAuditLog()

        def asr_engine(_object_key: str):
            self.assertEqual(jobs.get("tenant-a", "job_progress")["progress"], 20)
            return {"text": "progress"}

        def align_engine(transcript: dict):
            self.assertEqual(jobs.get("tenant-a", "job_progress")["progress"], 60)
            return {"segments": [{"start": 0.0, "end": 1.0, "text": transcript["text"]}]}

        def diarize_engine(aligned: dict):
            self.assertEqual(jobs.get("tenant-a", "job_progress")["progress"], 60)
            return {"speakers": [{"speaker": "spk_1", "segments": aligned["segments"]}]}

        pipeline = WorkerPipeline(
            job_store=jobs,
            artifact_store=artifacts,
            audit_log=audit,
            asr_engine=asr_engine,
            align_engine=align_engine,
            diarize_engine=diarize_engine,
        )

        result = pipeline.process(WorkerProcessInput(tenant_id="tenant-a", job_id="job_progress"))

        self.assertEqual(result.status, "completed")
        self.assertEqual(jobs.get("tenant-a", "job_progress")["status"], "completed")
        self.assertEqual(jobs.get("tenant-a", "job_progress")["progress"], 100)
        self.assertIsNotNone(artifacts.get("tenant-a", "job_progress"))

    def test_pause_requested_transitions_job_to_paused_without_completing(self):
        jobs = InMemoryJobStateStore(
            {
                ("tenant-a", "job_pause"): {
                    "tenant_id": "tenant-a",
                    "job_id": "job_pause",
                    "status": "queued",
                    "object_key": "tenant/tenant-a/job_pause/audio.wav",
                }
            }
        )
        artifacts = InMemoryArtifactStore()
        audit = InMemoryWorkerAuditLog()

        def asr_engine(_object_key: str):
            jobs.set_status("tenant-a", "job_pause", "pause_requested", progress=20)
            return {"text": "pause-me"}

        pipeline = WorkerPipeline(
            job_store=jobs,
            artifact_store=artifacts,
            audit_log=audit,
            asr_engine=asr_engine,
            align_engine=lambda transcript: transcript,
            diarize_engine=lambda aligned: aligned,
        )

        result = pipeline.process(WorkerProcessInput(tenant_id="tenant-a", job_id="job_pause"))

        self.assertEqual(result.status, "paused")
        self.assertEqual(jobs.get("tenant-a", "job_pause")["status"], "paused")
        self.assertEqual(jobs.get("tenant-a", "job_pause")["progress"], 20)
        self.assertIsNone(artifacts.get("tenant-a", "job_pause"))


if __name__ == "__main__":
    unittest.main()
