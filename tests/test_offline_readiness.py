from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evodox.runtime.offline_readiness import (
    REQUIRED_ALIGNMENT_MODEL_FILES,
    OfflineReadinessReport,
    check_offline_readiness,
    prepare_offline_assets,
)
from evodox.runtime.worker_runner import WorkerRuntimeSettings


class OfflineReadinessTests(unittest.TestCase):
    def _settings(self, model_dir: Path) -> WorkerRuntimeSettings:
        return WorkerRuntimeSettings(
            db_path=Path("/tmp/jobs.db"),
            mode="whisperx",
            whisperx_model_dir=model_dir,
            nltk_data_dir=model_dir / "nltk_data",
            whisperx_model="large-v3",
            diarization_model="pyannote/speaker-diarization-community-1",
            enable_diarization=True,
            hf_token="hf_test",
        )

    def test_check_offline_readiness_reports_ready_when_assets_are_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            (model_dir / "models--Systran--faster-whisper-large-v3").mkdir(parents=True)
            diar_root = model_dir / "models--pyannote--speaker-diarization-community-1"
            (diar_root / "snapshots" / "abc123").mkdir(parents=True)
            (diar_root / "refs").mkdir(parents=True)
            (diar_root / "refs" / "main").write_text("abc123", encoding="utf-8")
            for filename in REQUIRED_ALIGNMENT_MODEL_FILES:
                (model_dir / filename).write_text("x", encoding="utf-8")

            report = check_offline_readiness(
                self._settings(model_dir),
                internet_probe=lambda: False,
                punkt_available_checker=lambda: True,
            )

            self.assertEqual(
                report,
                OfflineReadinessReport(
                    ready=True,
                    missing=[],
                    internet_available=False,
                ),
            )

    def test_check_offline_readiness_reports_missing_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            report = check_offline_readiness(
                self._settings(model_dir),
                internet_probe=lambda: True,
                punkt_available_checker=lambda: False,
            )

            self.assertFalse(report.ready)
            self.assertTrue(report.internet_available)
            self.assertTrue(any("faster_whisper_cache" in item for item in report.missing))
            self.assertTrue(any("diarization_snapshot" in item for item in report.missing))
            self.assertTrue(any("nltk_punkt_tab" in item for item in report.missing))

    def test_prepare_offline_assets_returns_no_failures_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(Path(tmpdir))

            failures = prepare_offline_assets(
                settings,
                prepare_asr=lambda _settings: None,
                prepare_alignment=lambda _settings: None,
                prepare_diarization=lambda _settings: None,
                prepare_punkt=lambda: None,
            )
            self.assertEqual(failures, [])

    def test_prepare_offline_assets_collects_step_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(Path(tmpdir))

            failures = prepare_offline_assets(
                settings,
                prepare_asr=lambda _settings: None,
                prepare_alignment=lambda _settings: (_ for _ in ()).throw(RuntimeError("align failed")),
                prepare_diarization=lambda _settings: None,
                prepare_punkt=lambda: None,
            )

            self.assertEqual(len(failures), 1)
            self.assertIn("alignment", failures[0])
            self.assertIn("align failed", failures[0])


if __name__ == "__main__":
    unittest.main()
