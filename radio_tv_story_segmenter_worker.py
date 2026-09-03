#!/usr/bin/env python3
import os
import sys
import json
import shutil
import tempfile
import traceback
import subprocess
from pathlib import Path

PROTOCOL_VERSION = "1.0"
CAPABILITIES = ["transcribe", "diarize"]


def emit(message_type, **payload):
    message = {"type": message_type, **payload}
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def emit_hello():
    emit("hello", protocol=PROTOCOL_VERSION, capabilities=CAPABILITIES)


def transcribe(audio_file, model_name, initial_prompt=""):
    emit("progress", percent=5, message=f"Loading local Whisper {model_name} model...")
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        emit("error", message=f"Could not load faster-whisper locally: {type(exc).__name__}: {exc}")
        return 3

    try:
        # Prefer the configured device when one is supplied by a future
        # packaged runtime, but always recover to CPU/INT8 if accelerator
        # initialization fails. The current beta defaults to CPU.
        preferred_device = os.environ.get("PRS_WHISPER_DEVICE", "cpu").strip().lower() or "cpu"
        preferred_compute = os.environ.get("PRS_WHISPER_COMPUTE_TYPE", "int8").strip() or "int8"
        try:
            model = WhisperModel(model_name, device=preferred_device, compute_type=preferred_compute)
            backend = f"{preferred_device}/{preferred_compute}"
        except Exception as accel_exc:
            if preferred_device != "cpu" or preferred_compute != "int8":
                emit("progress", percent=8, message="Accelerated Whisper initialization failed; falling back to CPU INT8...")
            try:
                model = WhisperModel(model_name, device="cpu", compute_type="int8")
                backend = "cpu/int8"
            except Exception:
                raise accel_exc
        emit("progress", percent=15, message=f"Whisper {model_name} model loaded ({backend}). Transcribing...")

        clean_prompt = initial_prompt.strip() if initial_prompt and initial_prompt.strip() else None

        segments, info = model.transcribe(
            str(audio_file),
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
            initial_prompt=clean_prompt
        )

        formatted_segments = []
        total_duration = max(0.1, float(info.duration)) if hasattr(info, "duration") and info.duration else 1.0

        for seg in segments:
            pct = min(95, int(15 + (seg.end / total_duration) * 80))
            emit("progress", percent=pct, message=f"Transcribing ({seg.end:.1f}s / {total_duration:.1f}s)...")

            words = []
            if getattr(seg, "words", None):
                for w in seg.words:
                    words.append({
                        "word": w.word,
                        "start": float(w.start),
                        "end": float(w.end),
                        "probability": float(w.probability)
                    })

            formatted_segments.append({
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text.strip(),
                "words": words
            })

        output = {
            "text": " ".join([s["text"] for s in formatted_segments]),
            "segments": formatted_segments,
            "language": getattr(info, "language", "en")
        }

        emit("progress", percent=100, message="Transcription complete.")
        emit("finished", result=output)
        return 0

    except Exception as exc:
        emit("error", message=f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}")
        return 4


def normalize_audio_for_diarization(source_path):
    """Extract a normalized 16 kHz mono WAV using the local FFmpeg binary."""
    ffmpeg = None
    filename = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    candidates = [
        Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "runtime" / "bin" / filename,
        Path(sys.executable).resolve().parent / "runtime" / "bin" / filename,
        Path(__file__).resolve().parent / "runtime" / "bin" / filename,
    ]
    for candidate in candidates:
        if candidate.is_file():
            ffmpeg = str(candidate)
            break
    if ffmpeg is None:
        ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "FFmpeg could not be found on PATH. Speaker Detection requires the "
            "local FFmpeg installation to decode this media file."
        )

    source = Path(source_path).resolve()
    temp_dir = tempfile.TemporaryDirectory(prefix="prs_diarization_")
    wav_path = Path(temp_dir.name) / "audio_16khz_mono.wav"

    emit("progress", percent=18, message="Extracting and normalizing audio with local FFmpeg...")
    command = [
        ffmpeg,
        "-y",
        "-v", "error",
        "-i", str(source),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(wav_path),
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
        )
    except subprocess.TimeoutExpired as exc:
        temp_dir.cleanup()
        raise RuntimeError("FFmpeg audio normalization timed out after 15 minutes.") from exc
    if result.returncode != 0 or not wav_path.exists() or wav_path.stat().st_size == 0:
        detail = result.stderr.strip() or "FFmpeg did not produce an audio file."
        temp_dir.cleanup()
        raise RuntimeError(f"FFmpeg could not extract an audio stream: {detail}")

    emit("progress", percent=32, message="Audio extracted and normalized to 16 kHz mono WAV.")
    return temp_dir, wav_path


def diarize(audio_file, sensitivity=8):
    # Monkey-patch torchaudio.load and silero_vad to use soundfile directly on Windows
    try:
        import torch
        import soundfile as sf
        import torchaudio

        def safe_torchaudio_load(filepath, *args, **kwargs):
            data, sample_rate = sf.read(str(filepath), dtype="float32")
            tensor = torch.from_numpy(data)
            if tensor.ndim == 1:
                tensor = tensor.unsqueeze(0)
            else:
                tensor = tensor.T
            return tensor, sample_rate

        torchaudio.load = safe_torchaudio_load

        # Patch silero_vad to bypass sox_effects on Windows
        try:
            import silero_vad.utils_vad as silero_utils
            def safe_silero_read_audio(path: str, sampling_rate: int = 16000):
                data, sr = sf.read(str(path), dtype="float32")
                wav = torch.from_numpy(data)
                if wav.ndim > 1:
                    wav = wav.mean(dim=-1)
                if sr != sampling_rate:
                    transform = torchaudio.transforms.Resample(orig_freq=sr, new_freq=sampling_rate)
                    wav = transform(wav)
                return wav

            silero_utils.read_audio = safe_silero_read_audio
        except Exception:
            pass

    except Exception as exc:
        emit("warning", message=f"Could not patch torchaudio.load: {exc}")

    try:
        from diarize import diarize as diarize_fn
    except Exception as exc:
        emit("error", message=f"Could not load the local diarization package: {type(exc).__name__}: {exc}")
        return 3

    # Intercept tqdm progress updates from deep inside diarize/torch/pyannote if present
    try:
        import tqdm
        class ProgressTqdm(tqdm.tqdm):
            def update(self, n=1):
                super().update(n)
                if self.total and self.total > 0:
                    frac = min(1.0, max(0.0, float(self.n) / float(self.total)))
                    pct = int(42 + frac * 34)
                    emit("progress", percent=pct, message=f"Detecting speakers ({self.n}/{self.total} segments - {int(frac * 100)}%)...")
        tqdm.tqdm = ProgressTqdm
        if hasattr(tqdm, "auto"):
            tqdm.auto.tqdm = ProgressTqdm
    except Exception:
        pass

    temp_dir = None
    try:
        emit("progress", percent=5, message="Local Speaker Detection helper initialized.")
        emit("progress", percent=12, message="Loading local VAD and speaker-embedding models...")
        temp_dir, normalized_wav = normalize_audio_for_diarization(audio_file)
        emit("progress", percent=36, message="Analyzing speech regions and voice activity...")

        sensitivity = max(1, min(10, int(sensitivity)))
        short_fragment_threshold = max(0.45, 1.5 - (sensitivity * 0.10))
        emit(
            "progress",
            percent=42,
            message=f"Extracting speaker acoustic embeddings (Sensitivity: {sensitivity * 10}%)...",
        )

        import threading
        import time

        stop_ticker = threading.Event()

        def ticker():
            start_t = time.time()
            curr_pct = 42
            while not stop_ticker.wait(1.5):
                elapsed = time.time() - start_t
                if curr_pct < 74:
                    curr_pct = min(74, curr_pct + 1 + int(2 / (1 + elapsed * 0.04)))
                    emit("progress", percent=curr_pct, message=f"Analyzing speaker signatures ({int(elapsed)}s elapsed)...")

        ticker_thread = threading.Thread(target=ticker, daemon=True)
        ticker_thread.start()

        try:
            result = diarize_fn(str(normalized_wav))
        finally:
            stop_ticker.set()
            ticker_thread.join(timeout=1.0)

        emit("progress", percent=78, message="Clustering speaker signatures and acoustic vectors...")

        segments = []
        for segment in result.segments:
            segments.append({
                "start": float(segment.start),
                "end": float(segment.end),
                "speaker": str(segment.speaker),
            })

        merged_count = 0
        if len(segments) > 2:
            import numpy as np

            starts = np.array([s["start"] for s in segments], dtype=np.float64)
            ends = np.array([s["end"] for s in segments], dtype=np.float64)
            durations = np.maximum(0.0, ends - starts)
            speakers = [s["speaker"] for s in segments]

            short_mask = (durations[1:-1] <= short_fragment_threshold)
            
            for offset_i, is_short in enumerate(short_mask):
                i = offset_i + 1
                if is_short and speakers[i - 1] == speakers[i + 1] and speakers[i] != speakers[i - 1]:
                    segments[i]["speaker"] = speakers[i - 1]
                    speakers[i] = speakers[i - 1]
                    merged_count += 1

        merged_segments = []
        for segment in segments:
            if (
                merged_segments
                and merged_segments[-1]["speaker"] == segment["speaker"]
                and segment["start"] <= merged_segments[-1]["end"] + 0.02
            ):
                merged_segments[-1]["end"] = max(merged_segments[-1]["end"], segment["end"])
            else:
                merged_segments.append(segment)
        segments = merged_segments

        speakers = sorted({seg["speaker"] for seg in segments if seg.get("speaker")})
        emit(
            "progress",
            percent=88,
            message=f"Detected {len(speakers)} speaker(s); merged {merged_count} short fragment(s).",
        )

        output = {
            "num_speakers": len(speakers),
            "speakers": speakers,
            "audio_duration": float(result.audio_duration),
            "segments": segments,
        }
        emit("progress", percent=95, message="Aligning speaker boundaries with timeline...")
        emit("finished", result=output)
        return 0
    except Exception as exc:
        emit("error", message=f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}")
        return 4
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    emit_hello()
    if len(argv) < 1:
        emit("error", message="No processing mode was specified.")
        return 2

    mode = argv[0]
    if mode == "--transcribe":
        if len(argv) not in (3, 4):
            emit("error", message="Transcription worker requires an audio-file path and Whisper model name.")
            return 2
        initial_prompt = argv[3] if len(argv) == 4 else ""
        return transcribe(argv[1], argv[2], initial_prompt)

    if mode == "--diarize":
        if len(argv) not in (2, 3):
            emit("error", message="Speaker Detection worker requires an audio-file path and optional sensitivity.")
            return 2
        sensitivity = argv[2] if len(argv) >= 3 else "8"
        return diarize(argv[1], sensitivity)

    emit("error", message=f"Unknown processing mode: {mode}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())