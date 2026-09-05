#!/usr/bin/env python3
import os
import sys
import json
import shutil
import tempfile
import traceback
import subprocess
import numpy as np
from pathlib import Path


def _clamp_diarization_thread_env():
    """Cap OMP/ONNX Runtime/BLAS thread pools before onnxruntime, torch, or the
    diarize package are ever imported anywhere in this process (including
    lazily, inside functions below) -- both read their thread count from
    the environment at import/init time, and on high-thread-count machines
    letting them default to one thread per logical CPU oversubscribes the
    CPU and makes diarization and linear algebra operations *slower*, not faster.
    """
    try:
        import psutil
        physical = psutil.cpu_count(logical=False) or 0
    except Exception:
        physical = 0
    if not physical:
        cpu_count = os.cpu_count() or 4
        physical = cpu_count // 2 if cpu_count > 2 else cpu_count
    capped = max(1, min(int(physical), 8))
    for var in (
        "OMP_NUM_THREADS",
        "ORT_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ.setdefault(var, str(capped))


_clamp_diarization_thread_env()

PROTOCOL_VERSION = "1.0"
CAPABILITIES = ["transcribe", "diarize"]


def emit(message_type, **payload):
    message = {"type": message_type, **payload}
    sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def emit_hello():
    emit("hello", protocol=PROTOCOL_VERSION, capabilities=CAPABILITIES)


def get_optimal_transcription_threads() -> int:
    """Calculate optimal CPU threads for faster-whisper / CTranslate2 / ONNX.
    Uses physical cores instead of logical hyperthreads to avoid SMT stalls
    and cache thrashing, capped between 1 and 8.
    """
    try:
        import psutil
        count = psutil.cpu_count(logical=False)
        if count and count > 0:
            return max(1, min(int(count), 8))
    except Exception:
        pass
    try:
        count = os.cpu_count()
        if count and count > 0:
            physical = count // 2 if count > 2 else count
            return max(1, min(physical, 8))
    except Exception:
        pass
    return 4


def transcribe_parakeet_onnx(audio_file):
    """Run the installed Parakeet TDT bundle through sherpa-onnx.

    The downloaded Parakeet model is a NeMo TDT transducer. Its encoder expects
    acoustic features, not raw PCM, and it requires encoder/decoder/joiner
    decoding. sherpa-onnx handles both the feature extraction and TDT decode.
    """
    emit("progress", percent=5, message="Loading Parakeet ONNX transcription engine...")
    try:
        import numpy as np
        import sherpa_onnx
    except Exception as exc:
        emit("error", message=("Parakeet ONNX requires the sherpa-onnx runtime, "
                               f"which could not be loaded: {type(exc).__name__}: {exc}"))
        return 3

    models_dir = os.environ.get("PRS_MODELS_DIR")
    search_dirs = []
    if models_dir:
        search_dirs.extend([Path(models_dir) / "parakeet_onnx", Path(models_dir)])
    try:
        from prs_shared import get_models_storage_dir, get_app_data_dir
        search_dirs.extend([get_models_storage_dir() / "parakeet_onnx", get_models_storage_dir(),
                            get_app_data_dir() / "models" / "parakeet_onnx",
                            get_app_data_dir() / "models"])
    except Exception:
        pass
    if sys.platform == "win32":
        for env_key in ("LOCALAPPDATA", "APPDATA"):
            val = os.environ.get(env_key)
            if val:
                search_dirs.extend([Path(val) / "RadioTVStorySegmenter" / "models" / "parakeet_onnx",
                                    Path(val) / "RadioTVSegmenter" / "models" / "parakeet_onnx",
                                    Path(val) / "RadioTVStorySegmenter" / "models",
                                    Path(val) / "RadioTVSegmenter" / "models"])
    elif sys.platform == "darwin":
        search_dirs.extend([Path.home() / "Library" / "Application Support" / "RadioTVStorySegmenter" / "models" / "parakeet_onnx",
                            Path.home() / "Library" / "Application Support" / "RadioTVSegmenter" / "models" / "parakeet_onnx"])
    else:
        search_dirs.extend([Path.home() / ".local" / "share" / "RadioTVStorySegmenter" / "models" / "parakeet_onnx",
                            Path.home() / ".local" / "share" / "RadioTVSegmenter" / "models" / "parakeet_onnx"])
    search_dirs.append(Path(__file__).resolve().parent / "models" / "parakeet_onnx")

    required = ("encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt")
    model_dir = None
    seen = set()
    for raw in search_dirs:
        try: root = Path(raw).resolve()
        except Exception: continue
        if str(root) in seen or not root.is_dir(): continue
        seen.add(str(root))
        candidates = [root] + [p for p in root.rglob("*") if p.is_dir()]
        for candidate in candidates:
            if all((candidate / name).is_file() for name in required):
                model_dir = candidate
                break
        if model_dir: break

    if model_dir is None:
        emit("error", message=("Parakeet ONNX model is incomplete. Expected encoder.int8.onnx, "
                               "decoder.int8.onnx, joiner.int8.onnx, and tokens.txt. "
                               "Please use Manage Models to repair/reinstall Parakeet ONNX."))
        return 4

    temp_dir = None
    try:
        emit("progress", percent=10, message="Preparing 16 kHz mono audio for Parakeet ONNX...")
        norm_result = normalize_audio_for_diarization(audio_file)
        if isinstance(norm_result[0], tempfile.TemporaryDirectory):
            temp_dir, norm_wav = norm_result[0], norm_result[1]
        else:
            norm_wav, temp_dir = norm_result[0], norm_result[1]
        import wave
        with wave.open(str(norm_wav), "rb") as wf:
            framerate = wf.getframerate(); nframes = wf.getnframes()
            audio_bytes = wf.readframes(nframes); channels = wf.getnchannels(); width = wf.getsampwidth()
            duration_sec = max(0.1, nframes / float(framerate))
        if framerate != 16000 or channels != 1 or width != 2:
            raise RuntimeError(f"Normalized Parakeet audio has unexpected format: {framerate} Hz, {channels} channel(s), {width * 8}-bit.")
        samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        threads = get_optimal_transcription_threads()
        # Inspect the encoder contract rather than assuming a feature size.
        # Different Parakeet ONNX exports use 80 or 128 mel bins.
        feature_dim = 80
        try:
            import onnxruntime as ort
            probe = ort.InferenceSession(str(model_dir / "encoder.int8.onnx"), providers=["CPUExecutionProvider"])
            for meta in probe.get_inputs():
                shape = getattr(meta, "shape", None) or []
                if meta.name == "audio_signal" and len(shape) >= 2:
                    candidate = shape[1]
                    if isinstance(candidate, int) and candidate in (80, 128):
                        feature_dim = candidate
                    break
        except Exception:
            pass
        emit("progress", percent=20, message=f"Initializing Parakeet ONNX engine ({threads} CPU threads, {feature_dim}-bin features)...")
        recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(model_dir / "encoder.int8.onnx"),
            decoder=str(model_dir / "decoder.int8.onnx"),
            joiner=str(model_dir / "joiner.int8.onnx"),
            tokens=str(model_dir / "tokens.txt"),
            num_threads=threads, sample_rate=16000, feature_dim=feature_dim,
            decoding_method="greedy_search", provider="cpu", model_type="nemo_transducer")

        emit("progress", percent=35, message=f"Transcribing with Parakeet ONNX ({duration_sec:.1f}s of audio)...")

        # Slice audio into ~22s chunks at low-energy pause points to stay
        # well under the Conformer positional embedding cap (1,750 frames / ~70s).
        total_samples = len(samples)
        target_chunk_samples = int(22.0 * 16000)
        max_chunk_samples = int(26.0 * 16000)
        search_radius = int(1.5 * 16000)
        frame_len = int(0.05 * 16000)  # 50ms search resolution

        start_idx = 0
        chunk_indices = []
        while start_idx < total_samples:
            if total_samples - start_idx <= max_chunk_samples:
                chunk_indices.append((start_idx, total_samples))
                break

            nominal_cut = start_idx + target_chunk_samples
            s_start = max(start_idx, nominal_cut - search_radius)
            s_end = min(total_samples, nominal_cut + search_radius)

            search_region = samples[s_start:s_end]
            usable_len = len(search_region) - (len(search_region) % frame_len)
            if usable_len >= frame_len:
                frames = search_region[:usable_len].reshape(-1, frame_len)
                energies = np.mean(frames ** 2, axis=1)
                best_frame = int(np.argmin(energies))
                cut_point = s_start + (best_frame * frame_len) + (frame_len // 2)
            else:
                cut_point = min(total_samples, nominal_cut)

            chunk_indices.append((start_idx, cut_point))
            start_idx = cut_point

        token_list = []
        timestamp_list = []
        text_parts = []
        total_chunks = len(chunk_indices)

        for chunk_idx, (c_start, c_end) in enumerate(chunk_indices):
            chunk_samples = samples[c_start:c_end]
            chunk_start_sec = c_start / 16000.0
            chunk_end_sec = c_end / 16000.0

            pct = min(95, int(35 + (c_end / total_samples) * 55))
            emit("progress", percent=pct,
                 message=f"Transcribing with Parakeet ONNX ({chunk_end_sec:.1f}s / {duration_sec:.1f}s)...")

            stream = recognizer.create_stream()
            stream.accept_waveform(16000, chunk_samples)
            recognizer.decode_stream(stream)
            res = stream.result

            c_text = str(getattr(res, "text", "") or "").strip()
            c_tokens = list(getattr(res, "tokens", []) or [])
            c_timestamps = list(getattr(res, "timestamps", []) or [])

            if c_text:
                text_parts.append(c_text)

            if c_tokens and c_timestamps and len(c_tokens) == len(c_timestamps):
                # Ensure the first token of a new chunk is parsed as a word boundary
                if token_list and not str(c_tokens[0]).startswith(("▁", " ", "\t", "\n")):
                    c_tokens[0] = " " + str(c_tokens[0])

                for tok, ts in zip(c_tokens, c_timestamps):
                    token_list.append(tok)
                    timestamp_list.append(round(chunk_start_sec + max(0.0, float(ts)), 2))

        text = " ".join(text_parts).strip() or "(silence)"

        segments = []
        words = []
        if token_list and timestamp_list and len(token_list) == len(timestamp_list):
            normalized_tokens = [str(t) for t in token_list]
            token_times = [max(0.0, float(t)) for t in timestamp_list]

            def is_word_boundary(token):
                return token.startswith(("▁", " ", "\t", "\n"))

            token_groups = []
            current = []
            for token, ts in zip(normalized_tokens, token_times):
                if is_word_boundary(token) and current:
                    token_groups.append(current)
                    current = []
                current.append((token.lstrip("▁ \t\n"), ts))
            if current:
                token_groups.append(current)

            for group_idx, group in enumerate(token_groups):
                word_text = "".join(part for part, _ in group).strip()
                if not word_text:
                    continue
                word_start = group[0][1]
                if group_idx + 1 < len(token_groups):
                    word_end = token_groups[group_idx + 1][0][1]
                else:
                    word_end = min(duration_sec, word_start + 0.35)
                if word_end <= word_start:
                    word_end = min(duration_sec, word_start + 0.05)
                words.append({
                    "word": word_text,
                    "start": round(word_start, 2),
                    "end": round(word_end, 2),
                    "probability": 0.95,
                })

            current_words = []
            for word in words:
                gap = (word["start"] - current_words[-1]["end"]) if current_words else 0.0
                current_words.append(word)
                sentence_end = word["word"].rstrip().endswith((".", "?", "!"))
                too_many = len(current_words) >= 12
                long_gap = gap >= 1.0 and len(current_words) > 1
                if sentence_end or too_many or long_gap:
                    segments.append({
                        "start": round(current_words[0]["start"], 2),
                        "end": round(min(duration_sec, max(current_words[-1]["end"], current_words[0]["start"] + 0.05)), 2),
                        "text": " ".join(w["word"] for w in current_words),
                        "words": current_words,
                    })
                    current_words = []
            if current_words:
                segments.append({
                    "start": round(current_words[0]["start"], 2),
                    "end": round(min(duration_sec, max(current_words[-1]["end"], current_words[0]["start"] + 0.05)), 2),
                    "text": " ".join(w["word"] for w in current_words),
                    "words": current_words,
                })

        if not segments:
            words_raw = text.split(); step = duration_sec / max(1, len(words_raw))
            words = [{"word": w, "start": round(i * step, 2), "end": round(min(duration_sec, (i + 1) * step), 2), "probability": 0.95}
                     for i, w in enumerate(words_raw)]
            for off in range(0, len(words), 12):
                group = words[off:off + 12]
                segments.append({"start": group[0]["start"], "end": group[-1]["end"],
                                 "text": " ".join(w["word"] for w in group), "words": group})

        for segment in segments: emit("streaming_segment", segment=segment)
        emit("progress", percent=100, message="Parakeet ONNX transcription complete.")
        emit("finished", result={"text": text, "segments": segments, "language": "en"})
        return 0
    except Exception as exc:
        emit("error", message=f"Parakeet ONNX error: {type(exc).__name__}: {exc}\n\n{traceback.format_exc()}")
        return 5
    finally:
        try:
            if temp_dir is not None: temp_dir.cleanup()
        except Exception: pass


def transcribe(audio_file, model_name, initial_prompt="", beam_size=5):
    if str(model_name).lower().startswith("parakeet"):
        return transcribe_parakeet_onnx(audio_file)

    emit("progress", percent=5, message=f"Loading local Whisper {model_name} model...")
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        emit("error", message=f"Could not load faster-whisper locally: {type(exc).__name__}: {exc}")
        return 3

    try:
        threads = get_optimal_transcription_threads()
        download_root = os.environ.get("PRS_MODELS_DIR") or None

        resolved_model_name = model_name
        if model_name == "distil-medium.en":
            resolved_model_name = "Systran/faster-distil-whisper-medium.en"
        elif model_name == "distil-large-v3":
            resolved_model_name = "Systran/faster-distil-whisper-large-v3"
        elif model_name.startswith("distil-"):
            resolved_model_name = f"Systran/faster-{model_name}"

        model_to_load = resolved_model_name
        try:
            from prs_shared import get_models_storage_dir
            mdir = get_models_storage_dir()
            candidate_dirs = [
                mdir / "huggingface" / "hub" / f"models--{resolved_model_name.replace('/', '--')}",
                mdir / f"models--{resolved_model_name.replace('/', '--')}",
                mdir / model_name,
            ]
            for cd in candidate_dirs:
                if cd.exists() and ((cd / "model.bin").is_file() or any(cd.rglob("model.bin"))):
                    model_to_load = str(cd)
                    break
        except Exception:
            pass

        preferred_device = os.environ.get("PRS_WHISPER_DEVICE", "cpu").strip().lower() or "cpu"
        preferred_compute = os.environ.get("PRS_WHISPER_COMPUTE_TYPE", "int8").strip() or "int8"
        try:
            model = WhisperModel(
                model_to_load,
                device=preferred_device,
                compute_type=preferred_compute,
                cpu_threads=threads,
                download_root=download_root,
            )
            backend = f"{preferred_device}/{preferred_compute} ({threads} threads)"
        except Exception as accel_exc:
            if preferred_device != "cpu" or preferred_compute != "int8":
                emit("progress", percent=8, message="Accelerated Whisper initialization failed; falling back to CPU INT8...")
            try:
                model = WhisperModel(
                    model_to_load,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=threads,
                    download_root=download_root,
                )
                backend = f"cpu/int8 ({threads} threads)"
            except Exception:
                raise accel_exc
        emit("progress", percent=15, message=f"Whisper {model_name} model loaded ({backend}, beam={beam_size}). Transcribing...")

        clean_prompt = initial_prompt.strip() if initial_prompt and initial_prompt.strip() else None

        segments, info = model.transcribe(
            str(audio_file),
            beam_size=int(beam_size),
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

            seg_data = {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text.strip(),
                "words": words,
            }
            formatted_segments.append(seg_data)
            emit("streaming_segment", segment=seg_data)

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
        "-vn", "-sn", "-dn",
        "-map", "0:a:0?",
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


def configure_optimal_pytorch_threads():
    """Clamp torch's intra-op/inter-op thread pools to match the
    OMP/ORT clamp set at module import time, for the torch-based Silero VAD
    step. Inter-op threads can only be configured once per process, before
    any parallel work has started.
    """
    try:
        import torch
        threads = max(1, min(int(os.environ.get("OMP_NUM_THREADS", "4")), 8))
        torch.set_num_threads(threads)
        try:
            torch.set_num_interop_threads(threads)
        except RuntimeError:
            pass
    except Exception:
        pass


def _normalize_expected_speakers(value):
    """Map a CLI/UI expected-speakers hint to one of 'auto', '1', '2', '3+'."""
    text = str(value).strip().lower()
    if text in ("1", "solo"):
        return "1"
    if text == "2":
        return "2"
    if text in ("3+", "3", "panel", "group"):
        return "3+"
    return "auto"


def _normalize_speaker_labels(segments):
    """Relabel raw diarize-package speaker ids to 'Speaker 1', 'Speaker 2',
    etc, in order of first appearance so the numbering matches playback
    order rather than the library's internal (often alphabetical) ids.
    """
    order = []
    for seg in segments:
        raw = seg.get("speaker")
        if raw not in order:
            order.append(raw)
    label_map = {raw: f"Speaker {i + 1}" for i, raw in enumerate(order)}
    for seg in segments:
        seg["speaker"] = label_map.get(seg["speaker"], seg["speaker"])
    return segments


def _diarize_solo_fast_path(audio_file):
    """Solo fast-path: a single expected speaker means there is nothing to
    embed or cluster. Run Silero VAD alone, tag every detected speech block
    as 'Speaker 1', and return in ~1-2s.
    """
    configure_optimal_pytorch_threads()
    temp_dir = None
    try:
        emit("progress", percent=5, message="Local Speaker Detection helper initialized (solo fast-path).")
        temp_dir, normalized_wav = normalize_audio_for_diarization(audio_file)
        emit("progress", percent=45, message="Detecting speech regions (solo fast-path, no clustering needed)...")

        import torch
        import soundfile as sf
        from silero_vad import load_silero_vad, get_speech_timestamps

        data, sample_rate = sf.read(str(normalized_wav), dtype="float32")
        wav = torch.from_numpy(data)
        if wav.ndim > 1:
            wav = wav.mean(dim=-1)

        model = load_silero_vad()
        timestamps = get_speech_timestamps(wav, model, sampling_rate=sample_rate, return_seconds=True)

        segments = [
            {"start": float(ts["start"]), "end": float(ts["end"]), "speaker": "Speaker 1"}
            for ts in timestamps
        ]
        audio_duration = float(len(wav)) / float(sample_rate) if sample_rate else 0.0

        output = {
            "num_speakers": 1 if segments else 0,
            "speakers": ["Speaker 1"] if segments else [],
            "audio_duration": audio_duration,
            "segments": segments,
        }
        emit("progress", percent=95, message="Speech regions detected; single speaker assigned.")
        emit("finished", result=output)
        return 0
    except Exception as exc:
        emit("error", message=f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}")
        return 4
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


SHORT_FRAGMENT_MERGE_THRESHOLD = 0.7


def diarize(audio_file, expected_speakers="auto"):
    expected_speakers = _normalize_expected_speakers(expected_speakers)

    if expected_speakers == "1":
        return _diarize_solo_fast_path(audio_file)

    configure_optimal_pytorch_threads()

    # Monkey-patch torchaudio.load and silero_vad to use soundfile directly
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

    import time
    import math
    import threading

    diarization_start_time = time.time()
    global_last_tqdm_time = [0.0]
    global_tqdm_completed = [False]

    def _format_elapsed(start_epoch):
        elapsed = time.time() - start_epoch
        mins, secs = divmod(int(elapsed), 60)
        return f"{mins:02d}m {secs:02d}s"

    try:
        import tqdm
        class ProgressTqdm(tqdm.tqdm):
            def update(self, n=1):
                super().update(n)
                now = time.time()
                global_last_tqdm_time[0] = now
                if self.total and self.total > 0:
                    frac = min(1.0, max(0.0, float(self.n) / float(self.total)))
                    pct = int(42 + frac * 32)
                    if frac >= 0.99:
                        global_tqdm_completed[0] = True
                    elapsed_str = _format_elapsed(diarization_start_time)
                    emit(
                        "progress",
                        percent=pct,
                        message=f"Extracting speaker signatures ({elapsed_str} elapsed - {pct}%)..."
                    )
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

        import wave
        with wave.open(str(normalized_wav), "rb") as wf:
            total_audio_sec = wf.getnframes() / float(wf.getframerate())
        total_audio_min = total_audio_sec / 60.0

        emit("progress", percent=36, message=f"Analyzing speech regions ({total_audio_min:.1f}m audio)...")
        emit("progress", percent=42, message="Extracting speaker acoustic embeddings...")

        stop_ticker = threading.Event()

        def ticker():
            clustering_start_t = None
            curr_pct = 42

            while not stop_ticker.wait(1.5):
                now = time.time()
                elapsed_str = _format_elapsed(diarization_start_time)

                time_since_tqdm = now - global_last_tqdm_time[0] if global_last_tqdm_time[0] > 0 else 999.0
                is_clustering = global_tqdm_completed[0] or (time_since_tqdm > 3.0 and curr_pct >= 70)

                if is_clustering:
                    if clustering_start_t is None:
                        clustering_start_t = now

                    c_elapsed = now - clustering_start_t
                    asymptotic_target = 75 + int(19.0 * (1.0 - math.exp(-c_elapsed / 120.0)))
                    curr_pct = max(curr_pct, min(94, asymptotic_target))

                    emit(
                        "progress",
                        percent=curr_pct,
                        message=f"Clustering speaker signatures ({elapsed_str} elapsed - {total_audio_min:.1f}m audio)..."
                    )
                else:
                    if curr_pct < 74:
                        curr_pct = min(74, curr_pct + 1)
                    emit(
                        "progress",
                        percent=curr_pct,
                        message=f"Extracting speaker signatures ({elapsed_str} elapsed)..."
                    )

        ticker_thread = threading.Thread(target=ticker, daemon=True)
        ticker_thread.start()

        try:
            kwargs = {}
            if expected_speakers == "2":
                kwargs["num_speakers"] = 2
            elif expected_speakers == "3+":
                kwargs["min_speakers"] = 3

            result = diarize_fn(str(normalized_wav), **kwargs)
        finally:
            stop_ticker.set()
            ticker_thread.join(timeout=1.0)

        emit("progress", percent=89, message="Post-processing and smoothing speaker transitions...")

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

            short_mask = (durations[1:-1] <= SHORT_FRAGMENT_MERGE_THRESHOLD)

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
        segments = _normalize_speaker_labels(segments)

        speakers = sorted({seg["speaker"] for seg in segments if seg.get("speaker")})
        emit(
            "progress",
            percent=93,
            message=f"Detected {len(speakers)} speaker(s); merged {merged_count} short fragment(s).",
        )

        output = {
            "num_speakers": len(speakers),
            "speakers": speakers,
            "audio_duration": float(result.audio_duration),
            "segments": segments,
        }
        emit("progress", percent=97, message="Aligning speaker boundaries with timeline...")
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
        if len(argv) < 3:
            emit("error", message="Transcription worker requires an audio-file path and model name.")
            return 2
        initial_prompt = argv[3] if len(argv) >= 4 else ""
        beam_size = int(argv[4]) if len(argv) >= 5 and str(argv[4]).isdigit() else 5
        return transcribe(argv[1], argv[2], initial_prompt, beam_size=beam_size)

    if mode == "--diarize":
        if len(argv) < 2:
            emit("error", message="Speaker Detection worker requires an audio-file path.")
            return 2
        audio_path = argv[1]
        expected_speakers = "auto"
        rest = argv[2:]
        if rest:
            if rest[0] == "--expected-speakers" and len(rest) >= 2:
                expected_speakers = rest[1]
            elif rest[0].lstrip("-").isdigit():
                expected_speakers = "auto"
            else:
                expected_speakers = rest[0]
        return diarize(audio_path, expected_speakers)

    emit("error", message=f"Unknown processing mode: {mode}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
