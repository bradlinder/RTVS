#!/usr/bin/env python3
import os
import sys
import json
import shutil
import tempfile
import traceback
import subprocess
try:
    import numpy as np
except ImportError:
    np = None
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

_GLOBAL_WORKER_DLL_HANDLES = []


def _setup_windows_dll_directories():
    """Register native DLL directories (PyTorch, CTranslate2, ONNX Runtime, etc.)
    on Windows before importing C-extensions or ML frameworks.
    """
    if sys.platform != "win32":
        return

    candidate_dirs = set()

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            meipass_path = Path(meipass)
            candidate_dirs.add(meipass_path)
            candidate_dirs.add(meipass_path / "torch" / "lib")
            candidate_dirs.add(meipass_path / "torch")
            candidate_dirs.add(meipass_path / "torchaudio" / "lib")
            candidate_dirs.add(meipass_path / "ctranslate2")
            candidate_dirs.add(meipass_path / "onnxruntime" / "capi")
            candidate_dirs.add(meipass_path / "sherpa_onnx" / "lib")
            candidate_dirs.add(meipass_path / "sherpa_onnx")

        exe_dir = Path(sys.executable).parent
        candidate_dirs.add(exe_dir)
        candidate_dirs.add(exe_dir / "_internal")
        candidate_dirs.add(exe_dir / "_internal" / "torch" / "lib")
        candidate_dirs.add(exe_dir / "_internal" / "torch")
        candidate_dirs.add(exe_dir / "_internal" / "torchaudio" / "lib")
        candidate_dirs.add(exe_dir / "_internal" / "ctranslate2")
        candidate_dirs.add(exe_dir / "_internal" / "onnxruntime" / "capi")
        candidate_dirs.add(exe_dir / "_internal" / "sherpa_onnx" / "lib")
        candidate_dirs.add(exe_dir / "torch" / "lib")
        candidate_dirs.add(exe_dir / "torch")

    for entry in list(sys.path):
        if not entry:
            continue
        try:
            p = Path(entry)
            if not p.is_dir():
                continue
            candidate_dirs.add(p)
            candidate_dirs.add(p / "torch" / "lib")
            candidate_dirs.add(p / "torch")
            candidate_dirs.add(p / "torchaudio" / "lib")
            candidate_dirs.add(p / "ctranslate2")
            candidate_dirs.add(p / "onnxruntime" / "capi")
            candidate_dirs.add(p / "sherpa_onnx" / "lib")
            candidate_dirs.add(p / "sherpa_onnx")
        except Exception:
            continue

    try:
        prefix = Path(sys.prefix)
        candidate_dirs.add(prefix / "bin")
        candidate_dirs.add(prefix / "Library" / "bin")
        candidate_dirs.add(prefix / "Lib" / "site-packages" / "torch" / "lib")
        candidate_dirs.add(prefix / "Lib" / "site-packages" / "torchaudio" / "lib")
        candidate_dirs.add(prefix / "Lib" / "site-packages" / "ctranslate2")
        candidate_dirs.add(prefix / "Lib" / "site-packages" / "onnxruntime" / "capi")
    except Exception:
        pass

    try:
        import importlib.util
        spec = importlib.util.find_spec("torch")
        if spec and spec.origin:
            torch_root = Path(spec.origin).parent
            candidate_dirs.add(torch_root / "lib")
            candidate_dirs.add(torch_root)
    except Exception:
        pass

    added_paths = []
    for d in candidate_dirs:
        try:
            resolved = d.resolve()
            if resolved.is_dir():
                str_path = str(resolved)
                if hasattr(os, "add_dll_directory"):
                    try:
                        handle = os.add_dll_directory(str_path)
                        _GLOBAL_WORKER_DLL_HANDLES.append(handle)
                    except Exception:
                        pass
                added_paths.append(str_path)
        except Exception:
            continue

    if added_paths:
        current_path = os.environ.get("PATH", "")
        os.environ["PATH"] = os.pathsep.join(added_paths) + os.pathsep + current_path

    # Native libraries are made discoverable through os.add_dll_directory/PATH above.

_setup_windows_dll_directories()


def _safe_tensor_from_numpy(arr):
    """Safely convert a numpy float32 array into a PyTorch tensor.
    Works even if PyTorch's native C-extension numpy bridge fails to locate
    the NumPy C-API symbols ('numpy.core._multiarray_umath') or if the array is read-only.
    """
    import torch
    import numpy as np
    try:
        if isinstance(arr, np.ndarray):
            if not arr.flags.writeable or not arr.flags.c_contiguous:
                arr = np.ascontiguousarray(arr, dtype=np.float32).copy()
        return torch.from_numpy(arr)
    except (RuntimeError, UserWarning, AttributeError, Exception):
        pass
    try:
        return torch.as_tensor(arr, dtype=torch.float32)
    except (RuntimeError, UserWarning, AttributeError, Exception):
        pass
    return torch.tensor(arr.tolist(), dtype=torch.float32)


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

        def is_word_boundary(token_str):
            return str(token_str).startswith(("▁", " ", "\t", "\n"))

        all_segments = []
        all_words = []
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

            chunk_words = []
            if c_tokens and c_timestamps and len(c_tokens) == len(c_timestamps):
                # Ensure the first token of a new chunk is parsed as a word boundary
                if not is_word_boundary(c_tokens[0]):
                    c_tokens[0] = " " + str(c_tokens[0])

                token_groups = []
                current = []
                for tok, ts in zip(c_tokens, c_timestamps):
                    s_tok = str(tok)
                    abs_ts = round(chunk_start_sec + max(0.0, float(ts)), 2)
                    if is_word_boundary(s_tok) and current:
                        token_groups.append(current)
                        current = []
                    current.append((s_tok.lstrip("▁ \t\n"), abs_ts))
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
                        word_end = min(duration_sec, min(chunk_end_sec, word_start + 0.35))
                    if word_end <= word_start:
                        word_end = min(duration_sec, word_start + 0.05)
                    chunk_words.append({
                        "word": word_text,
                        "start": round(word_start, 2),
                        "end": round(word_end, 2),
                        "probability": 0.95,
                    })
            elif c_text:
                raw_words = c_text.split()
                step = max(0.05, (chunk_end_sec - chunk_start_sec) / max(1, len(raw_words)))
                for i, w in enumerate(raw_words):
                    w_start = chunk_start_sec + (i * step)
                    w_end = min(duration_sec, chunk_start_sec + ((i + 1) * step))
                    chunk_words.append({
                        "word": w,
                        "start": round(w_start, 2),
                        "end": round(w_end, 2),
                        "probability": 0.95,
                    })

            if chunk_words:
                all_words.extend(chunk_words)
                current_words = []
                for word in chunk_words:
                    gap = (word["start"] - current_words[-1]["end"]) if current_words else 0.0
                    current_words.append(word)
                    sentence_end = word["word"].rstrip().endswith((".", "?", "!"))
                    too_many = len(current_words) >= 12
                    long_gap = gap >= 1.0 and len(current_words) > 1
                    if sentence_end or too_many or long_gap:
                        seg_data = {
                            "start": round(current_words[0]["start"], 2),
                            "end": round(min(duration_sec, max(current_words[-1]["end"], current_words[0]["start"] + 0.05)), 2),
                            "text": " ".join(w["word"] for w in current_words),
                            "words": current_words,
                        }
                        all_segments.append(seg_data)
                        emit("streaming_segment", segment=seg_data)
                        current_words = []
                if current_words:
                    seg_data = {
                        "start": round(current_words[0]["start"], 2),
                        "end": round(min(duration_sec, max(current_words[-1]["end"], current_words[0]["start"] + 0.05)), 2),
                        "text": " ".join(w["word"] for w in current_words),
                        "words": current_words,
                    }
                    all_segments.append(seg_data)
                    emit("streaming_segment", segment=seg_data)

        text = " ".join(text_parts).strip() or "(silence)"

        if not all_segments:
            words_raw = text.split()
            step = duration_sec / max(1, len(words_raw)) if words_raw else 1.0
            words = [{"word": w, "start": round(i * step, 2), "end": round(min(duration_sec, (i + 1) * step), 2), "probability": 0.95}
                     for i, w in enumerate(words_raw)]
            if words:
                for off in range(0, len(words), 12):
                    group = words[off:off + 12]
                    seg_data = {
                        "start": group[0]["start"],
                        "end": group[-1]["end"],
                        "text": " ".join(w["word"] for w in group),
                        "words": group,
                    }
                    all_segments.append(seg_data)
                    emit("streaming_segment", segment=seg_data)
            else:
                seg_data = {
                    "start": 0.0,
                    "end": round(duration_sec, 2),
                    "text": "(silence)",
                    "words": [],
                }
                all_segments.append(seg_data)
                emit("streaming_segment", segment=seg_data)

        emit("progress", percent=100, message="Parakeet ONNX transcription complete.")
        emit("finished", result={"text": text, "segments": all_segments, "language": "en"})
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
        "-af", "highpass=f=85,lowpass=f=7500",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(wav_path),
    ]
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
            creationflags=creationflags,
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


def _diarize_solo_fast_path(audio_file, transcript_file=None):
    """Solo fast-path: a single expected speaker means there is nothing to
    embed or cluster. If an existing transcript is provided, map segments
    directly in memory. Otherwise run Silero VAD alone, tag every detected
    speech block as 'Speaker 1', and return in ~1-2s.
    """
    if transcript_file and os.path.exists(transcript_file):
        try:
            with open(transcript_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            t_segs = data.get("segments", [])
            if t_segs:
                segments = [
                    {
                        "start": float(seg["start"]),
                        "end": float(seg["end"]),
                        "speaker": "Speaker 1",
                    }
                    for seg in t_segs
                    if "start" in seg and "end" in seg and float(seg["end"]) > float(seg["start"])
                ]
                if segments:
                    last_end = max(s["end"] for s in segments)
                    output = {
                        "num_speakers": 1,
                        "speakers": ["Speaker 1"],
                        "audio_duration": float(last_end),
                        "segments": segments,
                    }
                    emit("progress", percent=95, message="Transcript-guided solo assignment complete.")
                    emit("finished", result=output)
                    return 0
        except Exception:
            pass

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
        wav = _safe_tensor_from_numpy(data)
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


def fast_cluster_ahc(embeddings, k):
    """Agglomerative Hierarchical Clustering with cosine metric and average linkage (O(N^2)).
    Eliminates O(N^3) Spectral Clustering Laplacian eigenvalue scaling bottlenecks.
    Groups speech vectors on unit hypersphere in seconds without accuracy loss.
    """
    import numpy as np
    n = len(embeddings)
    if n == 0:
        return np.array([], dtype=int)
    k = max(1, min(int(k), n))
    if k == 1:
        return np.zeros(n, dtype=int)

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    norm_emb = embeddings / norms

    from sklearn.cluster import AgglomerativeClustering
    try:
        clusterer = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average")
    except TypeError:
        clusterer = AgglomerativeClustering(n_clusters=k, affinity="cosine", linkage="average")
    labels = clusterer.fit_predict(norm_emb)

    try:
        from diarize.clustering import _refine_labels_spherical
        labels = _refine_labels_spherical(embeddings, labels)
    except Exception:
        pass
    return labels


def apply_clustering_patches():
    """Globally monkey-patch SpectralClustering and diarize.clustering to use O(N^2) AHC."""
    try:
        import sklearn.cluster

        class PatchedSpectralClustering:
            def __init__(self, n_clusters=2, *args, **kwargs):
                self.n_clusters = n_clusters
                self.labels_ = None
                self.affinity = kwargs.get("affinity", "cosine")

            def fit(self, X, y=None):
                self.labels_ = fast_cluster_ahc(X, self.n_clusters)
                return self

            def fit_predict(self, X, y=None):
                self.fit(X, y)
                return self.labels_

        sklearn.cluster.SpectralClustering = PatchedSpectralClustering
    except Exception:
        pass

    try:
        import diarize.clustering
        diarize.clustering.cluster_spectral = fast_cluster_ahc
    except Exception:
        pass

    try:
        import diarize
        diarize.cluster_spectral = fast_cluster_ahc
    except Exception:
        pass


def extract_embeddings_batched(
    audio_path,
    speech_segments,
    batch_size=32,
    min_segment_duration=0.4,
    embedding_window=1.2,
    embedding_step=0.6,
    progress_callback=None,
):
    """Extract 256-dim speaker embeddings using WeSpeaker ResNet34-LM (ONNX)
    with in-memory Fbank computation and batched ONNX session inference (batch size 16-32).
    Completely eliminates disk temp file I/O and maximizes SIMD/AVX-512 register utilization.
    """
    import numpy as np
    import soundfile as sf
    import torch
    import torchaudio.compliance.kaldi as kaldi
    from diarize.utils import SubSegment
    import wespeakerruntime as wespeaker_rt

    model = wespeaker_rt.Speaker(lang="en")
    session = model.session

    audio_data, sr = sf.read(str(audio_path), dtype="float32")
    if audio_data.ndim > 1:
        audio_data = audio_data.mean(axis=1)

    if sr != 16000:
        import torchaudio
        resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=16000)
        base_tensor = _safe_tensor_from_numpy(audio_data).unsqueeze(0)
        audio_tensor = resampler(base_tensor).squeeze(0)
        audio_data = audio_tensor.detach().cpu().numpy()
        sr = 16000
    else:
        audio_tensor = _safe_tensor_from_numpy(audio_data)

    window_slices = []

    for idx, seg in enumerate(speech_segments):
        seg_duration = getattr(seg, "duration", float(seg.end) - float(seg.start))
        if seg_duration < min_segment_duration:
            continue

        if seg_duration <= embedding_window * 1.5:
            windows = [(float(seg.start), float(seg.end))]
        else:
            windows = []
            win_start = float(seg.start)
            seg_end = float(seg.end)
            while win_start + min_segment_duration < seg_end:
                win_end = min(win_start + embedding_window, seg_end)
                windows.append((win_start, win_end))
                win_start += embedding_step

        for win_start, win_end in windows:
            start_sample = int(win_start * sr)
            end_sample = int(win_end * sr)
            if end_sample <= start_sample:
                continue
            window_slices.append((win_start, win_end, start_sample, end_sample, idx))

    if not window_slices:
        return np.empty((0, 256), dtype=np.float32), []

    all_feats = []
    valid_subsegments = []

    for win_start, win_end, start_samp, end_samp, parent_idx in window_slices:
        chunk = audio_tensor[start_samp:end_samp]
        if len(chunk) < int(0.1 * sr):
            continue
        try:
            chunk_wave = chunk.unsqueeze(0) * (1 << 15)
            mat = kaldi.fbank(
                chunk_wave,
                num_mel_bins=80,
                frame_length=25,
                frame_shift=10,
                dither=0.0,
                sample_frequency=sr,
                window_type="hamming",
                use_energy=False,
            )
            mat = mat.numpy()
            mat = mat - np.mean(mat, axis=0)
            all_feats.append(mat)
            valid_subsegments.append(SubSegment(start=win_start, end=win_end, parent_idx=parent_idx))
        except Exception:
            continue

    if not all_feats:
        return np.empty((0, 256), dtype=np.float32), []

    embeddings = []
    total_feats = len(all_feats)
    total_batches = (total_feats + batch_size - 1) // batch_size

    for b in range(total_batches):
        batch_slice = all_feats[b * batch_size : (b + 1) * batch_size]
        max_t = max(f.shape[0] for f in batch_slice)
        batch_feats = np.zeros((len(batch_slice), max_t, 80), dtype=np.float32)
        for i, f in enumerate(batch_slice):
            batch_feats[i, : f.shape[0], :] = f

        try:
            embs = session.run(output_names=["embs"], input_feed={"feats": batch_feats})[0]
            for emb in embs:
                embeddings.append(emb)
        except Exception:
            for f in batch_slice:
                single_in = np.expand_dims(f, 0).astype(np.float32)
                emb = session.run(output_names=["embs"], input_feed={"feats": single_in})[0][0]
                embeddings.append(emb)

        if progress_callback:
            progress_callback(len(embeddings), total_feats)

    X = np.stack(embeddings)
    return X, valid_subsegments


def run_vad_two_pass(
    audio_path,
    threshold=0.60,
    min_speech_duration_ms=250,
    min_silence_duration_ms=300,
    speech_pad_ms=10,
    bridge_pause_threshold_sec=0.10,
):
    """Silero VAD with Pass 1 Pause Bridging (< 100ms).
    Merges adjacent VAD speech intervals separated by pauses under 100ms,
    eliminating micro-slicing while preserving natural phrase boundaries.
    """
    import soundfile as sf
    import torch
    from silero_vad import get_speech_timestamps, load_silero_vad
    from diarize.utils import SpeechSegment

    data, sample_rate = sf.read(str(audio_path), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=-1)

    if sample_rate != 16000:
        try:
            from scipy.signal import resample_poly
            from math import gcd
            g = gcd(sample_rate, 16000)
            data = resample_poly(data, 16000 // g, sample_rate // g).astype("float32")
            sample_rate = 16000
        except Exception:
            try:
                import torchaudio
                t_wav = _safe_tensor_from_numpy(data)
                resampler = torchaudio.transforms.Resample(orig_freq=sample_rate, new_freq=16000)
                data = resampler(t_wav).detach().cpu().numpy()
                sample_rate = 16000
            except Exception:
                pass

    wav = _safe_tensor_from_numpy(data)

    try:
        vad_model = load_silero_vad(onnx=True)
    except Exception:
        vad_model = load_silero_vad()
    speech_timestamps = get_speech_timestamps(
        wav,
        vad_model,
        sampling_rate=16000,
        threshold=threshold,
        min_speech_duration_ms=min_speech_duration_ms,
        min_silence_duration_ms=min_silence_duration_ms,
        speech_pad_ms=speech_pad_ms,
        return_seconds=True,
    )

    if not speech_timestamps:
        return []

    speech_timestamps.sort(key=lambda ts: float(ts["start"]))

    merged_timestamps = [
        {"start": float(speech_timestamps[0]["start"]), "end": float(speech_timestamps[0]["end"])}
    ]
    for ts in speech_timestamps[1:]:
        curr_start = float(ts["start"])
        curr_end = float(ts["end"])
        prev = merged_timestamps[-1]
        gap = curr_start - prev["end"]
        if gap < bridge_pause_threshold_sec:
            prev["end"] = max(prev["end"], curr_end)
        else:
            merged_timestamps.append({"start": curr_start, "end": curr_end})

    return [SpeechSegment(start=ts["start"], end=ts["end"]) for ts in merged_timestamps]


def assign_short_segments_to_centroids(
    short_segments,
    audio_path,
    centroids,
    label_values,
    raw_segments=None,
    min_confidence=0.45,
):
    """Extract acoustic embeddings for short segments (< 0.8s, e.g. quick interjections
    such as 'no', 'yes', 'exactly') with symmetric audio context padding, and assign them
    to the nearest speaker centroid via cosine similarity.
    Mitigates inaccuracy for quick utterances without polluting the primary clustering matrix.
    """
    import numpy as np
    import soundfile as sf
    import torch
    import torchaudio.compliance.kaldi as kaldi
    import wespeakerruntime as wespeaker_rt

    if len(centroids) == 0:
        return []

    model = wespeaker_rt.Speaker(lang="en")
    session = model.session

    audio_data, sr = sf.read(str(audio_path), dtype="float32")
    if audio_data.ndim > 1:
        audio_data = audio_data.mean(axis=1)

    if sr != 16000:
        import torchaudio
        resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=16000)
        base_tensor = _safe_tensor_from_numpy(audio_data).unsqueeze(0)
        audio_tensor = resampler(base_tensor).squeeze(0)
        sr = 16000
    else:
        audio_tensor = _safe_tensor_from_numpy(audio_data)

    total_samples = len(audio_tensor)
    assigned = []

    for seg in short_segments:
        start_sec = float(seg.start if hasattr(seg, "start") else seg["start"])
        end_sec = float(seg.end if hasattr(seg, "end") else seg["end"])
        duration = end_sec - start_sec

        target_dur = max(0.4, duration)
        pad_needed = min(0.05, max(0.0, target_dur - duration) / 2.0)
        pad_start = max(0.0, start_sec - pad_needed)
        pad_end = min(float(total_samples) / float(sr), end_sec + pad_needed)

        start_samp = int(pad_start * sr)
        end_samp = int(pad_end * sr)
        chunk = audio_tensor[start_samp:end_samp]

        emb = None
        if len(chunk) >= int(0.15 * sr):
            try:
                chunk_wave = chunk.unsqueeze(0) * (1 << 15)
                mat = kaldi.fbank(
                    chunk_wave,
                    num_mel_bins=80,
                    frame_length=25,
                    frame_shift=10,
                    dither=0.0,
                    sample_frequency=sr,
                    window_type="hamming",
                    use_energy=False,
                )
                mat = mat.numpy()
                mat = mat - np.mean(mat, axis=0)
                single_in = np.expand_dims(mat, 0).astype(np.float32)
                emb = session.run(output_names=["embs"], input_feed={"feats": single_in})[0][0]
            except Exception:
                emb = None

        chosen_speaker = None
        if emb is not None:
            norm = np.linalg.norm(emb)
            if norm > 0:
                norm_emb = emb / norm
                sims = norm_emb @ centroids.T
                best_idx = int(np.argmax(sims))
                if sims[best_idx] >= min_confidence or len(label_values) == 1:
                    chosen_speaker = f"SPEAKER_{label_values[best_idx]:02d}"

        if not chosen_speaker and raw_segments:
            seg_mid = (start_sec + end_sec) / 2.0
            best_dist = float("inf")
            for raw in raw_segments:
                raw_mid = (raw.start + raw.end) / 2.0
                dist = abs(seg_mid - raw_mid)
                if dist < best_dist:
                    best_dist = dist
                    chosen_speaker = raw.speaker

        if not chosen_speaker:
            chosen_speaker = f"SPEAKER_{label_values[0]:02d}" if len(label_values) > 0 else "SPEAKER_00"

        from diarize import _RawSegment
        assigned.append(_RawSegment(start=start_sec, end=end_sec, speaker=chosen_speaker))

    return assigned


def run_transcript_guided_diarization(
    normalized_wav,
    transcript_file,
    expected_speakers="auto",
    progress_callback=None,
):
    """Execute transcript-guided speaker diarization:
    Bypasses Silero VAD entirely and extracts acoustic voice embeddings directly
    from Whisper/Parakeet sentence boundaries.
    Subdivides sentences > 6s, isolates short interjections (< 0.8s) for centroid
    cosine assignment, and groups speech turns via fast AHC clustering in seconds.
    """
    import json
    import numpy as np
    from diarize.utils import SpeechSegment
    from diarize.clustering import cluster_speakers
    from diarize import _RawSegment, _merge_adjacent_segments, DiarizeResult

    with open(transcript_file, "r", encoding="utf-8") as f:
        t_data = json.load(f)
    raw_transcript_segments = t_data.get("segments", [])

    valid_segments = []
    for s in raw_transcript_segments:
        if "start" in s and "end" in s:
            st = float(s["start"])
            en = float(s["end"])
            if en - st > 0.05:
                valid_segments.append({"start": st, "end": en, "text": s.get("text", "")})

    valid_segments.sort(key=lambda x: x["start"])
    if not valid_segments:
        return None

    primary_speech_segments = []
    short_speech_segments = []

    for s in valid_segments:
        st = s["start"]
        en = s["end"]
        dur = en - st

        if dur < 0.8:
            short_speech_segments.append(SpeechSegment(start=st, end=en))
        elif dur > 6.0:
            curr_start = st
            while curr_start + 1.0 < en:
                curr_end = min(curr_start + 3.0, en)
                primary_speech_segments.append(SpeechSegment(start=curr_start, end=curr_end))
                curr_start += 1.5
        else:
            primary_speech_segments.append(SpeechSegment(start=st, end=en))

    if len(primary_speech_segments) < 2 and short_speech_segments:
        primary_speech_segments.extend(short_speech_segments)
        short_speech_segments = []

    if progress_callback:
        progress_callback(45, "Extracting acoustic embeddings from transcript boundaries...")

    embeddings, subsegments = extract_embeddings_batched(
        normalized_wav,
        primary_speech_segments,
        batch_size=32,
        min_segment_duration=0.4,
    )

    if len(embeddings) == 0:
        raw_segments = [_RawSegment(start=s["start"], end=s["end"], speaker="SPEAKER_00") for s in valid_segments]
        merged = _merge_adjacent_segments(raw_segments)
        return DiarizeResult(
            segments=merged,
            audio_path=str(normalized_wav),
            audio_duration=valid_segments[-1]["end"],
            estimation_details=None,
        )

    cluster_kwargs = {}
    if expected_speakers == "2":
        cluster_kwargs["num_speakers"] = 2
    elif expected_speakers == "3+":
        cluster_kwargs["min_speakers"] = 3

    if progress_callback:
        progress_callback(78, "Grouping speaker signatures with fast AHC...")

    labels, estimation_details = cluster_speakers(embeddings, **cluster_kwargs)

    unique_labels = sorted(np.unique(labels))
    centroids_list = []
    label_values = []

    for l_val in unique_labels:
        cluster_embs = embeddings[labels == l_val]
        mean_emb = np.mean(cluster_embs, axis=0)
        norm = np.linalg.norm(mean_emb)
        if norm > 0:
            mean_emb = mean_emb / norm
        centroids_list.append(mean_emb)
        label_values.append(int(l_val))

    centroids = np.array(centroids_list)

    from diarize import _build_diarization_segments
    raw_segments = _build_diarization_segments(primary_speech_segments, subsegments, labels, embeddings)

    if short_speech_segments:
        short_assigned = assign_short_segments_to_centroids(
            short_speech_segments,
            normalized_wav,
            centroids,
            label_values,
            raw_segments=raw_segments,
        )
        raw_segments.extend(short_assigned)
        raw_segments.sort(key=lambda s: s.start)

    merged = _merge_adjacent_segments(raw_segments)
    audio_dur = max((s.end for s in merged), default=valid_segments[-1]["end"])

    return DiarizeResult(
        segments=merged,
        audio_path=str(normalized_wav),
        audio_duration=audio_dur,
        estimation_details=estimation_details,
    )


def diarize(audio_file, expected_speakers="auto", transcript_file=None):
    expected_speakers = _normalize_expected_speakers(expected_speakers)

    if expected_speakers == "1":
        return _diarize_solo_fast_path(audio_file, transcript_file=transcript_file)

    configure_optimal_pytorch_threads()

    try:
        import torch
        import soundfile as sf
        import torchaudio

        def safe_torchaudio_load(filepath, *args, **kwargs):
            data, sample_rate = sf.read(str(filepath), dtype="float32")
            tensor = _safe_tensor_from_numpy(data)
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
                wav = _safe_tensor_from_numpy(data)
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
        import diarize
        import diarize.embeddings
        import diarize.vad
        from diarize import diarize as diarize_fn

        apply_clustering_patches()
        diarize.embeddings.extract_embeddings = extract_embeddings_batched
        diarize.extract_embeddings = extract_embeddings_batched
        diarize.vad.run_vad = run_vad_two_pass
        diarize.run_vad = run_vad_two_pass
        if hasattr(diarize_fn, "__globals__"):
            diarize_fn.__globals__["run_vad"] = run_vad_two_pass
            diarize_fn.__globals__["extract_embeddings"] = extract_embeddings_batched
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

        is_transcript_guided = bool(transcript_file and os.path.exists(transcript_file))
        if is_transcript_guided:
            emit(
                "progress",
                percent=36,
                message=f"Transcript-guided analysis ({total_audio_min:.1f}m audio, bypassing raw VAD)..."
            )
        else:
            emit(
                "progress",
                percent=36,
                message=f"Analyzing speech regions with Two-Pass VAD ({total_audio_min:.1f}m audio)..."
            )

        emit("progress", percent=42, message="Extracting batched speaker acoustic embeddings...")

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
                        message=f"Clustering speaker signatures (AHC O(N^2) - {elapsed_str} elapsed)..."
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
            result = None
            if is_transcript_guided:
                try:
                    result = run_transcript_guided_diarization(
                        normalized_wav,
                        transcript_file,
                        expected_speakers=expected_speakers,
                        progress_callback=lambda p, msg: emit("progress", percent=p, message=msg),
                    )
                except Exception as tg_exc:
                    emit(
                        "warning",
                        message=f"Transcript-guided diarization fallback to standalone VAD: {tg_exc}"
                    )
                    result = None

            if result is None:
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
                and segment["start"] <= merged_segments[-1]["end"] + 0.05
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
    if mode == "--self-test":
        failures = []
        checks = []
        def _check(label, fn):
            try:
                value = fn()
                checks.append(f"[SELF-TEST] {label}: PASS" + (f" ({value})" if value else ""))
            except Exception as exc:
                failures.append((label, exc))
                checks.append(f"[SELF-TEST] {label}: FAIL: {type(exc).__name__}: {exc}")
        def _torch_location_diagnostic():
            import importlib.util
            spec = importlib.util.find_spec("torch._C")
            return str(spec.origin if spec and spec.origin else "not-found")
        _check("PyTorch _C module discovery", _torch_location_diagnostic)
        _check("PyTorch", lambda: __import__("torch").__version__)
        _check("PyTorch C extension", lambda: str(__import__("torch")._C))
        _check("PyTorch tensor operation", lambda: str(__import__("torch").tensor([1, 2, 3]).tolist()))
        _check("torchaudio", lambda: __import__("torchaudio").__version__)
        _check("CTranslate2", lambda: __import__("ctranslate2").__version__)
        _check("Silero VAD", lambda: __import__("silero_vad").__name__)
        _check("diarize", lambda: __import__("diarize").__name__)
        _check("NumPy", lambda: __import__("numpy").__version__)
        try:
            import transformers
            checks.append(f"[SELF-TEST] Transformers (Optional/Plugin): PASS ({transformers.__version__})")
        except ImportError:
            checks.append("[SELF-TEST] Transformers (Optional/Plugin): Skipped (Isolated in translation plugin runtime)")
        for line in checks:
            print(line, flush=True)
        return 1 if failures else 0

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
        transcript_file = None
        i = 2
        while i < len(argv):
            arg = argv[i]
            if arg == "--expected-speakers" and i + 1 < len(argv):
                expected_speakers = argv[i + 1]
                i += 2
            elif arg == "--transcript-file" and i + 1 < len(argv):
                transcript_file = argv[i + 1]
                i += 2
            elif not arg.startswith("--"):
                expected_speakers = arg
                i += 1
            else:
                i += 1
        return diarize(audio_path, expected_speakers, transcript_file=transcript_file)

    emit("error", message=f"Unknown processing mode: {mode}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
