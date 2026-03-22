import unittest

from evodox.jobs.worker_pipeline_service import (
    InMemoryArtifactStore,
    InMemoryCheckpointStore,
    InMemoryJobStateStore,
    InMemoryWorkerAuditLog,
    RetryableWorkerError,
    TerminalWorkerError,
    WorkerInterruptionRequested,
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
            checkpoint_store=InMemoryCheckpointStore(),
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
            checkpoint_store=InMemoryCheckpointStore(),
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
            checkpoint_store=InMemoryCheckpointStore(),
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
            checkpoint_store=InMemoryCheckpointStore(),
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
            checkpoint_store=InMemoryCheckpointStore(),
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
        checkpoints = InMemoryCheckpointStore()
        audit = InMemoryWorkerAuditLog()

        def asr_engine(_object_key: str):
            jobs.set_status("tenant-a", "job_pause", "pause_requested", progress=20)
            return {
                "text": "pause-me",
                "segments": [{"start": 0.0, "end": 1.0, "text": "pause-me"}],
            }

        pipeline = WorkerPipeline(
            job_store=jobs,
            artifact_store=artifacts,
            checkpoint_store=checkpoints,
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
        checkpoint = checkpoints.get("tenant-a", "job_pause")
        self.assertIsNotNone(checkpoint)
        self.assertEqual(checkpoint["stage"], "asr_started")
        self.assertEqual(checkpoint["stage_offset"], 1)

    def test_resume_uses_checkpoint_offset_and_skips_already_processed_segments(self):
        jobs = InMemoryJobStateStore(
            {
                ("tenant-a", "job_resume_cp"): {
                    "tenant_id": "tenant-a",
                    "job_id": "job_resume_cp",
                    "status": "queued",
                    "object_key": "tenant/tenant-a/job_resume_cp/audio.wav",
                }
            }
        )
        artifacts = InMemoryArtifactStore()
        checkpoints = InMemoryCheckpointStore()
        checkpoints.upsert(
            tenant_id="tenant-a",
            job_id="job_resume_cp",
            stage="asr_started",
            stage_offset=2,
            payload={
                "transcript": {
                    "text": "seg-0 seg-1",
                    "language": "de",
                    "segments": [
                        {"start": 0.0, "end": 1.0, "text": "seg-0"},
                        {"start": 1.0, "end": 2.0, "text": "seg-1"},
                    ],
                }
            },
        )
        seen_offsets: list[int] = []

        def asr_engine(_object_key: str, *, stage_offset: int = 0):
            seen_offsets.append(stage_offset)
            return {
                "text": "seg-2 seg-3",
                "language": "de",
                "segments": [
                    {"start": 2.0, "end": 3.0, "text": "seg-2"},
                    {"start": 3.0, "end": 4.0, "text": "seg-3"},
                ],
            }

        pipeline = WorkerPipeline(
            job_store=jobs,
            artifact_store=artifacts,
            checkpoint_store=checkpoints,
            audit_log=InMemoryWorkerAuditLog(),
            asr_engine=asr_engine,
            align_engine=lambda transcript: {"segments": transcript["segments"]},
            diarize_engine=lambda aligned: {"segments": [{"speaker": "spk_1"} for _ in aligned["segments"]]},
        )

        result = pipeline.process(WorkerProcessInput(tenant_id="tenant-a", job_id="job_resume_cp"))

        self.assertEqual(result.status, "completed")
        self.assertEqual(seen_offsets, [2])
        artifact = artifacts.get("tenant-a", "job_resume_cp")
        self.assertIsNotNone(artifact)
        assert artifact is not None
        self.assertEqual(len(artifact["transcript"]["segments"]), 4)
        self.assertEqual(artifact["transcript"]["segments"][0]["text"], "seg-0")
        self.assertEqual(artifact["transcript"]["segments"][3]["text"], "seg-3")

    def test_resume_deduplicates_when_asr_engine_ignores_offset(self):
        jobs = InMemoryJobStateStore(
            {
                ("tenant-a", "job_resume_no_offset"): {
                    "tenant_id": "tenant-a",
                    "job_id": "job_resume_no_offset",
                    "status": "queued",
                    "object_key": "tenant/tenant-a/job_resume_no_offset/audio.wav",
                }
            }
        )
        artifacts = InMemoryArtifactStore()
        checkpoints = InMemoryCheckpointStore()
        checkpoints.upsert(
            tenant_id="tenant-a",
            job_id="job_resume_no_offset",
            stage="asr_started",
            stage_offset=2,
            payload={
                "transcript": {
                    "text": "seg-0 seg-1",
                    "language": "de",
                    "segments": [
                        {"start": 0.0, "end": 1.0, "text": "seg-0"},
                        {"start": 1.0, "end": 2.0, "text": "seg-1"},
                    ],
                }
            },
        )

        def asr_engine(_object_key: str):
            # Simuliert eine Engine ohne stage_offset-Unterstuetzung, die erneut ab Segment 0 liefert.
            return {
                "text": "seg-0 seg-1 seg-2 seg-3",
                "language": "de",
                "segments": [
                    {"start": 0.0, "end": 1.0, "text": "seg-0"},
                    {"start": 1.0, "end": 2.0, "text": "seg-1"},
                    {"start": 2.0, "end": 3.0, "text": "seg-2"},
                    {"start": 3.0, "end": 4.0, "text": "seg-3"},
                ],
            }

        pipeline = WorkerPipeline(
            job_store=jobs,
            artifact_store=artifacts,
            checkpoint_store=checkpoints,
            audit_log=InMemoryWorkerAuditLog(),
            asr_engine=asr_engine,
            align_engine=lambda transcript: {"segments": transcript["segments"]},
            diarize_engine=lambda aligned: {"segments": [{"speaker": "spk_1"} for _ in aligned["segments"]]},
        )

        result = pipeline.process(WorkerProcessInput(tenant_id="tenant-a", job_id="job_resume_no_offset"))

        self.assertEqual(result.status, "completed")
        artifact = artifacts.get("tenant-a", "job_resume_no_offset")
        self.assertIsNotNone(artifact)
        assert artifact is not None
        self.assertEqual(len(artifact["transcript"]["segments"]), 4)
        self.assertEqual([segment["text"] for segment in artifact["transcript"]["segments"]], ["seg-0", "seg-1", "seg-2", "seg-3"])

    def test_cancel_requested_stops_pipeline_and_marks_job_canceled(self):
        jobs = InMemoryJobStateStore(
            {
                ("tenant-a", "job_cancel"): {
                    "tenant_id": "tenant-a",
                    "job_id": "job_cancel",
                    "status": "queued",
                    "object_key": "tenant/tenant-a/job_cancel/audio.wav",
                }
            }
        )
        artifacts = InMemoryArtifactStore()
        checkpoints = InMemoryCheckpointStore()

        def asr_engine(_object_key: str):
            jobs.set_status("tenant-a", "job_cancel", "cancel_requested", progress=25)
            return {
                "text": "cancel-me",
                "segments": [{"start": 0.0, "end": 1.0, "text": "cancel-me"}],
            }

        pipeline = WorkerPipeline(
            job_store=jobs,
            artifact_store=artifacts,
            checkpoint_store=checkpoints,
            audit_log=InMemoryWorkerAuditLog(),
            asr_engine=asr_engine,
            align_engine=lambda transcript: transcript,
            diarize_engine=lambda aligned: aligned,
        )

        result = pipeline.process(WorkerProcessInput(tenant_id="tenant-a", job_id="job_cancel"))

        self.assertEqual(result.status, "canceled")
        self.assertEqual(jobs.get("tenant-a", "job_cancel")["status"], "canceled")
        self.assertIsNone(artifacts.get("tenant-a", "job_cancel"))

    def test_interrupt_check_can_pause_long_running_asr(self):
        jobs = InMemoryJobStateStore(
            {
                ("tenant-a", "job_pause_interrupt"): {
                    "tenant_id": "tenant-a",
                    "job_id": "job_pause_interrupt",
                    "status": "queued",
                    "progress": 20,
                    "object_key": "tenant/tenant-a/job_pause_interrupt/audio.wav",
                }
            }
        )
        artifacts = InMemoryArtifactStore()
        checkpoints = InMemoryCheckpointStore()

        def asr_engine(_object_key: str, *, interrupt_check=None, stage_offset: int = 0):
            del stage_offset
            jobs.set_status("tenant-a", "job_pause_interrupt", "pause_requested", progress=20)
            if callable(interrupt_check):
                requested = interrupt_check()
                if requested:
                    raise WorkerInterruptionRequested(requested)
            return {"text": "never"}

        pipeline = WorkerPipeline(
            job_store=jobs,
            artifact_store=artifacts,
            checkpoint_store=checkpoints,
            audit_log=InMemoryWorkerAuditLog(),
            asr_engine=asr_engine,
            align_engine=lambda transcript: transcript,
            diarize_engine=lambda aligned: aligned,
        )

        result = pipeline.process(WorkerProcessInput(tenant_id="tenant-a", job_id="job_pause_interrupt"))
        self.assertEqual(result.status, "paused")
        self.assertEqual(jobs.get("tenant-a", "job_pause_interrupt")["status"], "paused")
        self.assertIsNone(artifacts.get("tenant-a", "job_pause_interrupt"))

    def test_interrupt_check_handles_deleted_status(self):
        jobs = InMemoryJobStateStore(
            {
                ("tenant-a", "job_deleted_interrupt"): {
                    "tenant_id": "tenant-a",
                    "job_id": "job_deleted_interrupt",
                    "status": "queued",
                    "progress": 20,
                    "object_key": "tenant/tenant-a/job_deleted_interrupt/audio.wav",
                }
            }
        )
        artifacts = InMemoryArtifactStore()
        checkpoints = InMemoryCheckpointStore()

        def asr_engine(_object_key: str, *, interrupt_check=None, stage_offset: int = 0):
            del stage_offset
            jobs.set_status("tenant-a", "job_deleted_interrupt", "deleted", progress=100)
            if callable(interrupt_check):
                requested = interrupt_check()
                if requested:
                    raise WorkerInterruptionRequested(requested)
            return {"text": "never"}

        pipeline = WorkerPipeline(
            job_store=jobs,
            artifact_store=artifacts,
            checkpoint_store=checkpoints,
            audit_log=InMemoryWorkerAuditLog(),
            asr_engine=asr_engine,
            align_engine=lambda transcript: transcript,
            diarize_engine=lambda aligned: aligned,
        )

        result = pipeline.process(WorkerProcessInput(tenant_id="tenant-a", job_id="job_deleted_interrupt"))
        self.assertEqual(result.status, "deleted")
        self.assertEqual(jobs.get("tenant-a", "job_deleted_interrupt")["status"], "deleted")
        self.assertIsNone(artifacts.get("tenant-a", "job_deleted_interrupt"))


if __name__ == "__main__":
    unittest.main()
