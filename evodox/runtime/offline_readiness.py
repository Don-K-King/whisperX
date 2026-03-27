from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import socket
from typing import Callable

from evodox.runtime.worker_runner import (
    WorkerRuntimeConfigError,
    WorkerRuntimeSettings,
    _resolve_local_diarization_model_path,
)

REQUIRED_ALIGNMENT_MODEL_FILES = (
    "wav2vec2_voxpopuli_base_10k_asr_de.pt",
    "wav2vec2_fairseq_base_ls960_asr_ls960.pth",
)


@dataclass(frozen=True)
class OfflineReadinessReport:
    ready: bool
    missing: list[str]
    internet_available: bool


def check_offline_readiness(
    settings: WorkerRuntimeSettings,
    *,
    internet_probe: Callable[[], bool] | None = None,
    punkt_available_checker: Callable[[], bool] | None = None,
) -> OfflineReadinessReport:
    probe = internet_probe or _probe_internet_connectivity
    has_punkt = punkt_available_checker or _is_punkt_tab_available
    missing: list[str] = []

    model_dir = settings.whisperx_model_dir
    settings.nltk_data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["NLTK_DATA"] = str(settings.nltk_data_dir)
    if not model_dir.exists():
        missing.append(f"model_dir_missing:{model_dir}")

    if not _has_faster_whisper_cache(settings):
        missing.append(f"faster_whisper_cache:{settings.whisperx_model}")

    for filename in REQUIRED_ALIGNMENT_MODEL_FILES:
        if not (model_dir / filename).exists():
            missing.append(f"alignment_model_file:{filename}")

    if settings.enable_diarization:
        resolved = _resolve_local_diarization_model_path(
            model_name=settings.diarization_model,
            model_dir=model_dir,
        )
        if resolved is None:
            missing.append(f"diarization_snapshot:{settings.diarization_model}")

    if not has_punkt():
        missing.append("nltk_punkt_tab:tokenizers/punkt_tab/english.pickle")

    internet_available = bool(probe())
    return OfflineReadinessReport(
        ready=len(missing) == 0,
        missing=missing,
        internet_available=internet_available,
    )


def prepare_offline_assets(
    settings: WorkerRuntimeSettings,
    *,
    prepare_asr: Callable[[WorkerRuntimeSettings], None] | None = None,
    prepare_alignment: Callable[[WorkerRuntimeSettings], None] | None = None,
    prepare_diarization: Callable[[WorkerRuntimeSettings], None] | None = None,
    prepare_punkt: Callable[[], None] | None = None,
) -> list[str]:
    asr_step = prepare_asr or _prepare_asr_model
    align_step = prepare_alignment or _prepare_alignment_models
    diarization_step = prepare_diarization or _prepare_diarization_model
    punkt_step = prepare_punkt or _prepare_punkt_tab

    settings.whisperx_model_dir.mkdir(parents=True, exist_ok=True)
    settings.nltk_data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["NLTK_DATA"] = str(settings.nltk_data_dir)

    failures: list[str] = []
    steps: list[tuple[str, Callable[[], None]]] = [
        ("asr", lambda: asr_step(settings)),
        ("alignment", lambda: align_step(settings)),
        ("diarization", lambda: diarization_step(settings)),
        ("nltk_punkt_tab", punkt_step),
    ]
    for name, action in steps:
        try:
            action()
        except Exception as exc:
            failures.append(f"{name}:{type(exc).__name__}:{exc}")
    return failures


def _prepare_asr_model(settings: WorkerRuntimeSettings) -> None:
    from whisperx.asr import load_model

    model = load_model(
        whisper_arch=settings.whisperx_model,
        device="cpu",
        device_index=0,
        compute_type="int8",
        download_root=str(settings.whisperx_model_dir),
        local_files_only=False,
        vad_method=settings.whisperx_vad_method,
        language="de",
        use_auth_token=settings.hf_token,
    )
    del model


def _prepare_alignment_models(settings: WorkerRuntimeSettings) -> None:
    from whisperx.alignment import load_align_model

    for language in ("de", "en"):
        model, _metadata = load_align_model(
            language_code=language,
            device="cpu",
            model_dir=str(settings.whisperx_model_dir),
            model_cache_only=False,
        )
        del model


def _prepare_diarization_model(settings: WorkerRuntimeSettings) -> None:
    if not settings.enable_diarization:
        return
    from whisperx.diarize import DiarizationPipeline

    pipeline = DiarizationPipeline(
        model_name=settings.diarization_model,
        token=settings.hf_token,
        device="cpu",
        cache_dir=str(settings.whisperx_model_dir),
    )
    del pipeline


def _prepare_punkt_tab() -> None:
    import nltk

    nltk.download("punkt_tab", quiet=True)


def _has_faster_whisper_cache(settings: WorkerRuntimeSettings) -> bool:
    model_name = str(settings.whisperx_model or "").strip()
    if not model_name:
        return False
    model_dir = settings.whisperx_model_dir
    candidates = []
    if "/" in model_name:
        candidates.append(model_dir / f"models--{model_name.replace('/', '--')}")
    else:
        candidates.append(model_dir / f"models--Systran--faster-whisper-{model_name}")
    return any(path.exists() for path in candidates)


def _is_punkt_tab_available() -> bool:
    try:
        from nltk.data import load as nltk_load
    except Exception:
        return False
    try:
        nltk_load("tokenizers/punkt_tab/english.pickle")
    except LookupError:
        return False
    return True


def _probe_internet_connectivity() -> bool:
    try:
        with socket.create_connection(("huggingface.co", 443), timeout=2.0):
            return True
    except OSError:
        return False


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline-Readiness und Auto-Prepare fuer EvidoX Worker.")
    parser.add_argument("command", choices=["check", "prepare"], help="Auszufuehrender Schritt.")
    parser.add_argument("--json", action="store_true", dest="as_json", help="JSON-Ausgabe erzwingen.")
    return parser


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()

    try:
        settings = WorkerRuntimeSettings.from_env()
    except WorkerRuntimeConfigError as exc:
        payload = {"ready": False, "missing": [f"config_error:{exc}"], "internet_available": False}
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    if args.command == "prepare":
        failures = prepare_offline_assets(settings)
        report = check_offline_readiness(settings)
        payload = {
            "prepared_failures": failures,
            **asdict(report),
        }
        print(json.dumps(payload, ensure_ascii=True))
        if failures or not report.ready:
            return 2
        return 0

    report = check_offline_readiness(settings)
    print(json.dumps(asdict(report), ensure_ascii=True))
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
