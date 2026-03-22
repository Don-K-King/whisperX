from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from evodox.jobs.infrastructure import SQLiteJobRepository, SQLiteOutbox
from evodox.jobs.worker_pipeline_service import WorkerProcessResult
from evodox.runtime.worker_runner import (
    WorkerRuntime,
    WorkerRuntimeConfigError,
    WorkerRuntimeSettings,
    _build_whisperx_command,
)


class WorkerRunnerTests(unittest.TestCase):
    def test_settings_default_to_gpu_first_for_whisperx(self) -> None:
        settings = WorkerRuntimeSettings.from_env(
            {
                "WORKER_DB_PATH": "/tmp/jobs.db",
                "WORKER_MODE": "whisperx",
                "WORKER_ENABLE_DIARIZATION": "false",
            }
        )

        self.assertEqual(settings.whisperx_device, "cuda")
        self.assertEqual(settings.whisperx_compute_type, "float16")
        self.assertEqual(settings.whisperx_device_index, 0)
        self.assertEqual(settings.worker_allowed_queues, ())

    def test_settings_parse_device_index_and_allowed_queues(self) -> None:
        settings = WorkerRuntimeSettings.from_env(
            {
                "WORKER_DB_PATH": "/tmp/jobs.db",
                "WORKER_MODE": "whisperx",
                "WORKER_ENABLE_DIARIZATION": "false",
                "WORKER_WHISPERX_DEVICE_INDEX": "2",
                "WORKER_ALLOWED_QUEUES": "gpu-standard, gpu-long,",
            }
        )

        self.assertEqual(settings.whisperx_device_index, 2)
        self.assertEqual(settings.worker_allowed_queues, ("gpu-standard", "gpu-long"))

    def test_build_whisperx_command_includes_diarization_flags_when_enabled(self) -> None:
        settings = WorkerRuntimeSettings(
            db_path=Path("/tmp/jobs.db"),
            mode="whisperx",
            hf_token="hf_test",
            enable_diarization=True,
            diarization_model="pyannote/speaker-diarization",
            min_speakers=1,
            max_speakers=3,
        )

        command = _build_whisperx_command(
            media_path=Path("/tmp/demo.wav"),
            output_dir=Path("/tmp/out"),
            settings=settings,
            include_diarization=True,
        )

        self.assertIn("--diarize", command)
        self.assertIn("pyannote/speaker-diarization", command)
        self.assertIn("--hf_token", command)
        self.assertIn("--device_index", command)

    def test_build_whisperx_command_includes_device_index(self) -> None:
        settings = WorkerRuntimeSettings(
            db_path=Path("/tmp/jobs.db"),
            mode="whisperx",
            whisperx_device="cuda",
            whisperx_device_index=1,
            enable_diarization=False,
        )
        command = _build_whisperx_command(
            media_path=Path("/tmp/demo.wav"),
            output_dir=Path("/tmp/out"),
            settings=settings,
            include_diarization=False,
        )

        device_index_position = command.index("--device_index")
        self.assertEqual(command[device_index_position + 1], "1")

    def test_build_whisperx_command_omits_diarization_flags_when_disabled(self) -> None:
        settings = WorkerRuntimeSettings(
            db_path=Path("/tmp/jobs.db"),
            mode="whisperx",
            hf_token=None,
            enable_diarization=False,
        )

        command = _build_whisperx_command(
            media_path=Path("/tmp/demo.wav"),
            output_dir=Path("/tmp/out"),
            settings=settings,
            include_diarization=False,
            transcription_options=None,
        )

        self.assertNotIn("--diarize", command)
        self.assertNotIn("--hf_token", command)

    def test_build_whisperx_command_includes_snapshot_decoding_flags(self) -> None:
        settings = WorkerRuntimeSettings(
            db_path=Path("/tmp/jobs.db"),
            mode="whisperx",
            enable_diarization=False,
        )
        command = _build_whisperx_command(
            media_path=Path("/tmp/demo.wav"),
            output_dir=Path("/tmp/out"),
            settings=settings,
            include_diarization=False,
            transcription_options={
                "temperature": 0.3,
                "beam_size": 4,
                "patience": 1.2,
                "length_penalty": 1.1,
                "compression_ratio_threshold": 2.1,
                "logprob_threshold": -1.2,
                "no_speech_threshold": 0.55,
                "suppress_tokens": "-1,12",
                "initial_prompt": "Fachsprache",
                "condition_on_previous_text": True,
            },
        )

        self.assertIn("--temperature", command)
        self.assertIn("0.3", command)
        self.assertIn("--beam_size", command)
        self.assertIn("4", command)
        self.assertIn("--initial_prompt", command)
        self.assertIn("Fachsprache", command)
        self.assertIn("--condition_on_previous_text", command)
        self.assertIn("True", command)

    def test_build_whisperx_command_ignores_invalid_snapshot_and_uses_defaults(self) -> None:
        settings = WorkerRuntimeSettings(
            db_path=Path("/tmp/jobs.db"),
            mode="whisperx",
            enable_diarization=False,
        )
        command = _build_whisperx_command(
            media_path=Path("/tmp/demo.wav"),
            output_dir=Path("/tmp/out"),
            settings=settings,
            include_diarization=False,
            transcription_options={
                "temperature": 9.0,
                "beam_size": 999,
                "unknown_option": True,
            },
        )

        temp_index = command.index("--temperature")
        beam_index = command.index("--beam_size")
        self.assertEqual(command[temp_index + 1], "0.0")
        self.assertEqual(command[beam_index + 1], "5")
        self.assertNotIn("--unknown_option", command)

    def test_settings_require_hf_token_for_whisperx_diarization_mode(self) -> None:
        with self.assertRaises(WorkerRuntimeConfigError):
            WorkerRuntimeSettings.from_env(
                {
                    "WORKER_DB_PATH": "/tmp/jobs.db",
                    "WORKER_MODE": "whisperx",
                    "WORKER_ENABLE_DIARIZATION": "true",
                }
            )

    def test_settings_accept_whisperx_mode_when_hf_token_present(self) -> None:
        settings = WorkerRuntimeSettings.from_env(
            {
                "WORKER_DB_PATH": "/tmp/jobs.db",
                "WORKER_MODE": "whisperx",
                "WORKER_ENABLE_DIARIZATION": "true",
                "HF_TOKEN": "hf_test_token",
            }
        )

        self.assertEqual(settings.mode, "whisperx")

    def test_settings_accept_zero_whisperx_timeout(self) -> None:
        settings = WorkerRuntimeSettings.from_env(
            {
                "WORKER_DB_PATH": "/tmp/jobs.db",
                "WORKER_MODE": "whisperx",
                "WORKER_ENABLE_DIARIZATION": "true",
                "HF_TOKEN": "hf_test_token",
                "WORKER_WHISPERX_TIMEOUT_SECONDS": "0",
            }
        )
        self.assertEqual(settings.whisperx_timeout_seconds, 0)

    def test_run_once_processes_pending_outbox_event_to_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            repo.create(
                {
                    "job_id": "job_1",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "audio.wav",
                    "content_type": "audio/wav",
                    "size_bytes": 1200,
                    "retention_months": 6,
                    "status": "queued",
                    "object_key": "tenant/tenant-a/job_1/audio.wav",
                }
            )
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_1",
                    "queue": "cpu-short",
                    "object_key": "tenant/tenant-a/job_1/audio.wav",
                    "checksum_sha256": "a" * 64,
                    "upload_session_id": "up_1",
                }
            )

            runtime = WorkerRuntime(
                settings=WorkerRuntimeSettings(
                    db_path=db_path,
                    batch_size=10,
                    poll_interval_seconds=1,
                    mode="stub",
                    audit_log_path=Path(tmpdir) / "worker-audit.jsonl",
                )
            )
            result = runtime.run_once()

            self.assertEqual(result.processed, 1)
            row = repo.get("tenant-a", "job_1")
            self.assertEqual(row["status"], "completed")
            with sqlite3.connect(db_path) as conn:
                outbox_status = conn.execute("SELECT status FROM outbox_events WHERE job_id = 'job_1'").fetchone()[0]
            self.assertEqual(outbox_status, "published")

    def test_scope_violation_marks_job_failed_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            repo.create(
                {
                    "job_id": "job_2",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "audio.wav",
                    "content_type": "audio/wav",
                    "size_bytes": 1200,
                    "retention_months": 6,
                    "status": "queued",
                    "object_key": "tenant/tenant-b/job_2/audio.wav",
                }
            )
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_2",
                    "queue": "cpu-short",
                    "object_key": "tenant/tenant-b/job_2/audio.wav",
                    "checksum_sha256": "a" * 64,
                    "upload_session_id": "up_2",
                }
            )

            runtime = WorkerRuntime(
                settings=WorkerRuntimeSettings(
                    db_path=db_path,
                    batch_size=10,
                    poll_interval_seconds=1,
                    mode="stub",
                    audit_log_path=Path(tmpdir) / "worker-audit.jsonl",
                )
            )
            result = runtime.run_once()

            self.assertEqual(result.processed, 1)
            row = repo.get("tenant-a", "job_2")
            self.assertEqual(row["status"], "failed_terminal")
            with sqlite3.connect(db_path) as conn:
                outbox_status = conn.execute("SELECT status FROM outbox_events WHERE job_id = 'job_2'").fetchone()[0]
            self.assertEqual(outbox_status, "dlq")

    def test_retryable_worker_failures_are_retried_and_become_failed_terminal_after_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            repo.create(
                {
                    "job_id": "job_retry_limit",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "audio.wav",
                    "content_type": "audio/wav",
                    "size_bytes": 1200,
                    "retention_months": 6,
                    "status": "queued",
                    "object_key": "tenant/tenant-a/job_retry_limit/audio.wav",
                }
            )
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_retry_limit",
                    "queue": "cpu-short",
                    "object_key": "tenant/tenant-a/job_retry_limit/audio.wav",
                    "checksum_sha256": "a" * 64,
                    "upload_session_id": "up_retry_limit",
                }
            )

            runtime = WorkerRuntime(
                settings=WorkerRuntimeSettings(
                    db_path=db_path,
                    batch_size=10,
                    poll_interval_seconds=1,
                    mode="stub",
                    audit_log_path=Path(tmpdir) / "worker-audit.jsonl",
                    worker_max_retries=1,
                )
            )

            class _RetryablePipeline:
                def process(self, request):
                    repo.set_status(request.tenant_id, request.job_id, "failed_retryable", progress=20)
                    return WorkerProcessResult(
                        tenant_id=request.tenant_id,
                        job_id=request.job_id,
                        status="failed_retryable",
                        error_code="worker.timeout",
                    )

            runtime.pipeline = _RetryablePipeline()

            first = runtime.run_once()
            self.assertEqual(first.failed, 1)
            self.assertEqual(repo.get("tenant-a", "job_retry_limit")["status"], "failed_retryable")
            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    "SELECT status, retry_count FROM outbox_events WHERE job_id = 'job_retry_limit'"
                ).fetchone()
                self.assertEqual(row[0], "pending")
                self.assertEqual(row[1], 1)
                conn.execute(
                    "UPDATE outbox_events SET next_attempt_at = '2000-01-01T00:00:00+00:00' WHERE job_id = 'job_retry_limit'"
                )

            second = runtime.run_once()
            self.assertEqual(second.failed, 1)
            self.assertEqual(repo.get("tenant-a", "job_retry_limit")["status"], "failed_terminal")
            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    "SELECT status, dlq_reason, last_error_code FROM outbox_events WHERE job_id = 'job_retry_limit'"
                ).fetchone()
            self.assertEqual(row[0], "dlq")
            self.assertEqual(row[1], "retry_exhausted")
            self.assertEqual(row[2], "worker.timeout")

    def test_run_once_whisperx_mode_processes_event_with_injected_runtime_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            repo.create(
                {
                    "job_id": "job_3",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "meeting.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 4200,
                    "retention_months": 6,
                    "status": "queued",
                    "object_key": "tenant/tenant-a/job_3/meeting.mp4",
                }
            )
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_3",
                    "queue": "cpu-short",
                    "object_key": "tenant/tenant-a/job_3/meeting.mp4",
                    "checksum_sha256": "a" * 64,
                    "upload_session_id": "up_3",
                    "transcription_options": {
                        "temperature": 0.2,
                        "beam_size": 4,
                        "patience": 1.1,
                        "length_penalty": 1.0,
                        "compression_ratio_threshold": 2.2,
                        "logprob_threshold": -1.0,
                        "no_speech_threshold": 0.5,
                        "suppress_tokens": "-1,12",
                        "initial_prompt": "Fachsprache",
                        "condition_on_previous_text": True,
                    },
                }
            )

            media_file = Path(tmpdir) / "meeting.mp4"
            media_file.write_bytes(b"fake-video-content")

            observed_options = {}
            runtime = WorkerRuntime(
                settings=WorkerRuntimeSettings(
                    db_path=db_path,
                    batch_size=10,
                    poll_interval_seconds=1,
                    mode="whisperx",
                    audit_log_path=Path(tmpdir) / "worker-audit.jsonl",
                    hf_token="hf_test_token",
                    enable_diarization=True,
                ),
                media_fetcher=lambda _object_key: media_file,
                whisperx_runner=lambda _media_path, _settings, transcription_options=None: (
                    observed_options.update({"value": transcription_options}),
                    {
                        "transcript": {
                            "text": "Hallo zusammen",
                            "language": "de",
                            "segments": [{"start": 0.0, "end": 1.0, "text": "Hallo zusammen"}],
                        },
                        "diarization": {
                            "segments": [{"speaker": "SPEAKER_00", "start": 0.0, "end": 1.0}]
                        },
                    },
                )[1],
            )
            result = runtime.run_once()

            self.assertEqual(result.processed, 1)
            row = repo.get("tenant-a", "job_3")
            self.assertEqual(row["status"], "completed")
            self.assertEqual(observed_options["value"]["beam_size"], 4)

    def test_runtime_falls_back_to_cpu_when_cuda_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            audit_path = Path(tmpdir) / "worker-audit.jsonl"
            media_file = Path(tmpdir) / "meeting.mp4"
            media_file.write_bytes(b"fake-video-content")
            repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            repo.create(
                {
                    "job_id": "job_cuda_fallback",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "meeting.mp4",
                    "content_type": "video/mp4",
                    "size_bytes": 4200,
                    "retention_months": 6,
                    "status": "queued",
                    "object_key": "tenant/tenant-a/job_cuda_fallback/meeting.mp4",
                }
            )
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_cuda_fallback",
                    "queue": "gpu-standard",
                    "object_key": "tenant/tenant-a/job_cuda_fallback/meeting.mp4",
                    "checksum_sha256": "a" * 64,
                    "upload_session_id": "up_cuda_fallback",
                }
            )

            runtime = WorkerRuntime(
                settings=WorkerRuntimeSettings(
                    db_path=db_path,
                    batch_size=10,
                    poll_interval_seconds=1,
                    mode="whisperx",
                    whisperx_device="cuda",
                    whisperx_compute_type="float16",
                    audit_log_path=audit_path,
                    hf_token="hf_test_token",
                    enable_diarization=False,
                ),
                media_fetcher=lambda _object_key: media_file,
                whisperx_runner=lambda _media_path, settings: {
                    "transcript": {
                        "text": f"device={settings.whisperx_device}",
                        "language": "de",
                        "segments": [{"start": 0.0, "end": 1.0, "text": "ok"}],
                    },
                    "diarization": {"segments": [{"speaker": "SPEAKER_00", "start": 0.0, "end": 1.0}]},
                },
                cuda_available_fn=lambda: False,
            )

            self.assertEqual(runtime.settings.whisperx_device, "cpu")
            self.assertEqual(runtime.settings.whisperx_compute_type, "int8")
            self.assertEqual(runtime.run_once().processed, 1)

            events = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            fallback_events = [event for event in events if event.get("action") == "worker.runtime.gpu_fallback"]
            self.assertEqual(len(fallback_events), 1)

    def test_run_once_respects_allowed_queues_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            repo.create(
                {
                    "job_id": "job_gpu",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "a.wav",
                    "content_type": "audio/wav",
                    "size_bytes": 1200,
                    "retention_months": 6,
                    "status": "queued",
                    "object_key": "tenant/tenant-a/job_gpu/a.wav",
                }
            )
            repo.create(
                {
                    "job_id": "job_cpu",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "b.wav",
                    "content_type": "audio/wav",
                    "size_bytes": 1200,
                    "retention_months": 6,
                    "status": "queued",
                    "object_key": "tenant/tenant-a/job_cpu/b.wav",
                }
            )
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_cpu",
                    "queue": "cpu-short",
                    "object_key": "tenant/tenant-a/job_cpu/b.wav",
                    "checksum_sha256": "a" * 64,
                    "upload_session_id": "up_cpu",
                }
            )
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_gpu",
                    "queue": "gpu-standard",
                    "object_key": "tenant/tenant-a/job_gpu/a.wav",
                    "checksum_sha256": "a" * 64,
                    "upload_session_id": "up_gpu",
                }
            )
            runtime = WorkerRuntime(
                settings=WorkerRuntimeSettings(
                    db_path=db_path,
                    batch_size=10,
                    poll_interval_seconds=1,
                    mode="stub",
                    worker_allowed_queues=("gpu-standard",),
                    audit_log_path=Path(tmpdir) / "worker-audit.jsonl",
                )
            )

            result = runtime.run_once()
            self.assertEqual(result.processed, 1)
            self.assertEqual(repo.get("tenant-a", "job_gpu")["status"], "completed")
            self.assertEqual(repo.get("tenant-a", "job_cpu")["status"], "queued")
            pending = outbox.list_pending(limit=10)
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["job_id"], "job_cpu")

    def test_cancel_requested_has_priority_and_prevents_retry_processing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            repo.create(
                {
                    "job_id": "job_cancel_priority",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "audio.wav",
                    "content_type": "audio/wav",
                    "size_bytes": 1200,
                    "retention_months": 6,
                    "status": "cancel_requested",
                    "object_key": "tenant/tenant-a/job_cancel_priority/audio.wav",
                }
            )
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_cancel_priority",
                    "queue": "cpu-short",
                    "object_key": "tenant/tenant-a/job_cancel_priority/audio.wav",
                    "checksum_sha256": "a" * 64,
                    "upload_session_id": "up_cancel_priority",
                }
            )

            runtime = WorkerRuntime(
                settings=WorkerRuntimeSettings(
                    db_path=db_path,
                    batch_size=10,
                    poll_interval_seconds=1,
                    mode="stub",
                    audit_log_path=Path(tmpdir) / "worker-audit.jsonl",
                )
            )
            result = runtime.run_once()

            self.assertEqual(result.processed, 1)
            row = repo.get("tenant-a", "job_cancel_priority")
            self.assertEqual(row["status"], "canceled")
            with sqlite3.connect(db_path) as conn:
                outbox_status = conn.execute(
                    "SELECT status FROM outbox_events WHERE job_id = 'job_cancel_priority'"
                ).fetchone()[0]
            self.assertEqual(outbox_status, "published")

    def test_unhandled_pipeline_exception_goes_dlq_without_retry_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "jobs.db"
            repo = SQLiteJobRepository(db_path)
            outbox = SQLiteOutbox(db_path)
            repo.create(
                {
                    "job_id": "job_crash",
                    "tenant_id": "tenant-a",
                    "actor_id": "u-1",
                    "filename": "audio.wav",
                    "content_type": "audio/wav",
                    "size_bytes": 1200,
                    "retention_months": 6,
                    "status": "queued",
                    "object_key": "tenant/tenant-a/job_crash/audio.wav",
                }
            )
            outbox.append(
                {
                    "event_type": "job.queued",
                    "tenant_id": "tenant-a",
                    "job_id": "job_crash",
                    "queue": "cpu-short",
                    "object_key": "tenant/tenant-a/job_crash/audio.wav",
                    "checksum_sha256": "a" * 64,
                    "upload_session_id": "up_crash",
                }
            )
            runtime = WorkerRuntime(
                settings=WorkerRuntimeSettings(
                    db_path=db_path,
                    batch_size=10,
                    poll_interval_seconds=1,
                    mode="stub",
                    audit_log_path=Path(tmpdir) / "worker-audit.jsonl",
                )
            )

            class _BoomPipeline:
                def process(self, _request):
                    raise RuntimeError("boom")

            runtime.pipeline = _BoomPipeline()

            result = runtime.run_once()
            self.assertEqual(result.processed, 1)
            self.assertEqual(result.failed, 1)

            row = repo.get("tenant-a", "job_crash")
            self.assertEqual(row["status"], "failed_terminal")
            with sqlite3.connect(db_path) as conn:
                status, retry_count, dlq_reason = conn.execute(
                    "SELECT status, retry_count, dlq_reason FROM outbox_events WHERE job_id = 'job_crash'"
                ).fetchone()
            self.assertEqual(status, "dlq")
            self.assertEqual(retry_count, 0)
            self.assertEqual(dlq_reason, "worker.unhandled_exception")


if __name__ == "__main__":
    unittest.main()
