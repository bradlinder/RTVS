"""Translation plugin worker.

All OPUS-MT/Transformers/CTranslate2 translation implementation lives here,
so the core application does not import translation-only ML packages.
"""
from __future__ import annotations

import copy
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

try:
    from PySide6.QtCore import QObject, Signal
except ImportError:
    class _SignalInstance:
        def __init__(self):
            self._callbacks = []

        def connect(self, callback):
            self._callbacks.append(callback)

        def disconnect(self, callback=None):
            if callback is None:
                self._callbacks.clear()
            elif callback in self._callbacks:
                self._callbacks.remove(callback)

        def emit(self, *args, **kwargs):
            for cb in list(self._callbacks):
                try:
                    cb(*args, **kwargs)
                except Exception:
                    pass

    class Signal:
        def __init__(self, *types):
            self._types = types

        def __set_name__(self, owner, name):
            self._name = f"_sig_{name}"

        def __get__(self, instance, owner=None):
            if instance is None:
                return self
            if not hasattr(instance, self._name):
                setattr(instance, self._name, _SignalInstance())
            return getattr(instance, self._name)

    class QObject:
        def __init__(self, parent=None):
            self._parent = parent

from plugins.translation.support import get_models_storage_dir, setup_windows_dll_directories

class TranslationWorker(QObject):
    """Local OPUS-MT translation/model-management worker."""
    progress = Signal(int, str)
    checkpoint = Signal(object, str, int)
    finished = Signal(object, str)
    cancelled = Signal(object, str)
    error = Signal(str)
    model_status = Signal(str, str, bool, str)
    model_status_finished = Signal()

    MODEL_REPOS = {
        "tiny": {("en", "es"): "Helsinki-NLP/opus-mt_tiny_eng-spa", ("es", "en"): "Helsinki-NLP/opus-mt_tiny_spa-eng"},
        "standard": {("en", "es"): "Helsinki-NLP/opus-mt-en-es", ("es", "en"): "Helsinki-NLP/opus-mt-es-en"},
        "opus-mt": {("en", "es"): "Helsinki-NLP/opus-mt-en-es", ("es", "en"): "Helsinki-NLP/opus-mt-es-en"},
    }
    MODEL_FILES = (
        "config.json",
        "generation_config.json",
        "model.safetensors",
        "source.spm",
        "target.spm",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "added_tokens.json",
        "vocab.json",
        "vocab.spm",
    )

    def __init__(
        self,
        segments=None,
        from_code="en",
        to_code="es",
        install_if_missing=False,
        installation_only=False,
        resume_results=None,
        model_variant="standard",
        status_only=False,
        parent=None,
        transcript=None,
        variant=None,
        device="cpu",
        **kwargs,
    ):
        # Force parent to None so Qt doesn't bind this object to the GUI thread
        super().__init__(None)

        if transcript is not None:
            if isinstance(transcript, dict):
                segments = transcript.get("segments", [])
            elif isinstance(transcript, list):
                segments = transcript
        elif isinstance(segments, dict):
            segments = segments.get("segments", [])

        self.segments = list(segments) if segments is not None else []
        self.from_code = from_code
        self.to_code = to_code
        self.install_if_missing = install_if_missing
        self.installation_only = installation_only
        self.resume_results = resume_results or []

        eff_variant = variant or model_variant or "standard"
        if eff_variant == "opus-mt":
            eff_variant = "standard"
        self.model_variant = eff_variant
        self.status_only = status_only
        self.translation_device = device
        self._cancelled = False
        self._is_cancelled = False
        
        # Defer model handles so they instantiate inside run() on the QThread
        self.model = None
        self.tokenizer = None
        if kwargs.get("models_dir"):
            os.environ["RTVS_MODELS_DIR"] = str(kwargs.get("models_dir"))

    @classmethod
    def model_root(cls, variant="tiny"):
        return get_models_storage_dir() / f"opus-mt-{variant}"

    @classmethod
    def model_dir(cls, from_code, to_code, variant="tiny"):
        canonical = cls.model_root(variant) / f"{from_code}-{to_code}"
        if cls._model_is_installed_in_dir(canonical):
            return canonical
        try:
            from plugins.translation.support import get_legacy_models_storage_dirs
            for legacy_root in get_legacy_models_storage_dirs():
                legacy_dir = legacy_root / f"opus-mt-{variant}" / f"{from_code}-{to_code}"
                if cls._model_is_installed_in_dir(legacy_dir):
                    return legacy_dir
        except Exception:
            pass
        return canonical

    @classmethod
    def _has_required_model_files(cls, directory):
        directory = Path(directory)
        required = ["config.json", "tokenizer_config.json", "source.spm", "target.spm"]
        if not all((directory / name).is_file() and (directory / name).stat().st_size > 0 for name in required):
            return False
        weights = [directory / "model.safetensors", directory / "pytorch_model.bin"]
        if not any(path.is_file() and path.stat().st_size > 0 for path in weights):
            return False
        return True

    @classmethod
    def _model_is_installed_in_dir(cls, directory):
        directory = Path(directory)
        if not directory.is_dir():
            return False
        if not cls._has_required_model_files(directory):
            return False
        marker = directory / ".complete"
        if not marker.is_file():
            try:
                marker.write_text("verified\n", encoding="utf-8")
            except Exception:
                pass
        return True

    @classmethod
    def model_is_installed(cls, from_code, to_code, variant="tiny"):
        return cls._model_is_installed_in_dir(cls.model_dir(from_code, to_code, variant))

    @classmethod
    def model_repo(cls, from_code, to_code, variant="tiny"):
        return cls.MODEL_REPOS.get(variant, {}).get((from_code, to_code))

    def cancel(self):
        self._cancelled = True

    def _download_file(self, repo, filename, destination, progress_start, progress_end, label):
        import urllib.request
        import urllib.error

        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_name(destination.name + ".download")
        url = f"https://huggingface.co/{repo}/resolve/main/{filename}?download=true"
        request = urllib.request.Request(url, headers={"User-Agent": "Radio-TV-Story-Segmenter/60-opus-mt-tiny"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response, temp.open("wb") as out:
                total = int(response.headers.get("Content-Length") or 0)
                downloaded = 0
                while True:
                    if self._cancelled:
                        raise InterruptedError("Model download canceled.")
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        fraction = min(1.0, downloaded / total)
                        pct = int(progress_start + (progress_end - progress_start) * fraction)
                        self.progress.emit(pct, f"{label} ({downloaded / (1024 * 1024):.0f} / {total / (1024 * 1024):.0f} MB)")
                out.flush()
                os.fsync(out.fileno())
            if not temp.exists() or temp.stat().st_size == 0:
                raise RuntimeError(f"Downloaded model file '{filename}' is empty.")
            os.replace(temp, destination)
        except InterruptedError:
            try:
                temp.unlink(missing_ok=True)
            except Exception:
                pass
            raise
        except Exception as exc:
            try:
                temp.unlink(missing_ok=True)
            except Exception:
                pass
            if isinstance(exc, urllib.error.HTTPError):
                raise RuntimeError(f"Could not download {filename} (HTTP {exc.code}).") from exc
            raise RuntimeError(f"Could not download {filename}: {exc}") from exc

    def _ensure_model_installed(self):
        """Download a complete Hugging Face snapshot into a staging directory and publish atomically."""
        from_code, to_code = self.from_code, self.to_code
        repo = self.model_repo(from_code, to_code, self.model_variant)
        if not repo:
            raise RuntimeError(f"No OPUS-MT {self.model_variant} model is configured for {from_code.upper()} → {to_code.upper()}.")
        if self.model_is_installed(from_code, to_code, self.model_variant) and not self.installation_only:
            self.progress.emit(5, f"OPUS-MT {self.model_variant} model is installed; loading it…")
            return self.model_dir(from_code, to_code, self.model_variant)

        final_dir = self.model_dir(from_code, to_code, self.model_variant)
        staging_dir = final_dir.with_name(final_dir.name + ".installing")
        backup_dir = final_dir.with_name(final_dir.name + ".backup")
        self.progress.emit(2, f"Preparing OPUS-MT {self.model_variant} model download…")
        try:
            if staging_dir.exists(): shutil.rmtree(staging_dir, ignore_errors=True)
            staging_dir.mkdir(parents=True, exist_ok=True)

            # Discover model files from Hugging Face API or fall back to standard file list
            import urllib.request
            import urllib.error
            import json

            target_files = []
            try:
                api_url = f"https://huggingface.co/api/models/{repo}"
                req = urllib.request.Request(api_url, headers={"User-Agent": "Radio-TV-Story-Segmenter/60-opus-mt"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    api_data = json.loads(resp.read().decode("utf-8"))
                    siblings = [s.get("rfilename", "") for s in api_data.get("siblings", []) if s.get("rfilename")]
                    # Include required configs, tokenizers, and weights while skipping unneeded formats
                    skip_exts = (".tflite", ".msgpack", ".h5", ".npz", ".yml", ".md", ".gitattributes")
                    for fname in siblings:
                        if fname.startswith("."):
                            continue
                        if any(fname.endswith(ext) for ext in skip_exts):
                            continue
                        target_files.append(fname)
            except Exception:
                pass

            if not target_files:
                target_files = [
                    "config.json",
                    "generation_config.json",
                    "tokenizer_config.json",
                    "source.spm",
                    "target.spm",
                    "special_tokens_map.json",
                    "model.safetensors",
                    "pytorch_model.bin",
                    "vocab.json",
                    "vocab.spm",
                ]

            total_files = len(target_files)
            downloaded_count = 0
            for idx, fname in enumerate(target_files):
                if self._cancelled:
                    raise InterruptedError("Model download canceled.")
                p_start = 5 + int(80 * (idx / total_files))
                p_end = 5 + int(80 * ((idx + 1) / total_files))
                try:
                    self._download_file(
                        repo,
                        fname,
                        staging_dir / fname,
                        p_start,
                        p_end,
                        f"Downloading {fname}",
                    )
                    downloaded_count += 1
                except Exception as dl_err:
                    # Optional weights or auxiliary files can be skipped if another weight file exists
                    if fname in ("pytorch_model.bin", "model.safetensors", "generation_config.json", "special_tokens_map.json", "added_tokens.json", "vocab.spm", "vocab.json"):
                        continue
                    # For critical files, if download fails, log and let verification catch if required
                    continue

            if self._cancelled: raise InterruptedError("Model download canceled.")
            marker = staging_dir / ".complete"
            marker.write_text(f"{repo}\n{self.model_variant}\n{datetime.now().isoformat()}\n", encoding="utf-8")
            self.progress.emit(90, f"Verifying OPUS-MT {self.model_variant} model files…")
            if not self._model_is_installed_in_dir(staging_dir):
                raise RuntimeError(f"The translation model download for {repo} completed, but required model files (config, tokenizer, weights) are missing or incomplete.")
            if backup_dir.exists(): shutil.rmtree(backup_dir, ignore_errors=True)
            if final_dir.exists(): final_dir.rename(backup_dir)
            staging_dir.rename(final_dir)
            if backup_dir.exists(): shutil.rmtree(backup_dir, ignore_errors=True)
            self.progress.emit(100, f"OPUS-MT {self.model_variant} model installed and verified.")
            return final_dir
        except Exception:
            try:
                if staging_dir.exists(): shutil.rmtree(staging_dir, ignore_errors=True)
            except Exception: pass
            raise

    def _get_optimal_cpu_threads(self) -> int:
        """Compute optimal thread count for translation on CPU (capped to 4-8)."""
        import os
        try:
            import psutil
            count = psutil.cpu_count(logical=False) or os.cpu_count() or 4
        except Exception:
            count = os.cpu_count() or 4
        return max(1, min(8, count))

    def _ensure_ctranslate2_model(self, model_dir: Path) -> Path:
        """Ensure an INT8-quantized CTranslate2 model exists in model_dir / 'ct2_int8'.
        
        Converts the Hugging Face OPUS-MT PyTorch/Safetensors model if not already cached.
        """
        ct2_dir = model_dir / "ct2_int8"
        marker = ct2_dir / ".complete"
        if ct2_dir.is_dir() and marker.is_file() and (ct2_dir / "model.bin").is_file():
            return ct2_dir

        # Convert HF model to CTranslate2 INT8 model
        self.progress.emit(7, "Optimizing translation engine for fast CPU execution…")
        setup_windows_dll_directories()
        os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
        import ctranslate2
        from ctranslate2.converters import TransformersConverter

        staging_ct2 = model_dir / "ct2_int8.converting"
        if staging_ct2.exists():
            import shutil
            shutil.rmtree(staging_ct2, ignore_errors=True)
        staging_ct2.mkdir(parents=True, exist_ok=True)

        converter = TransformersConverter(str(model_dir))
        converter.convert(
            str(staging_ct2),
            quantization="int8",
            force=True,
        )

        marker_file = staging_ct2 / ".complete"
        marker_file.write_text("ct2_int8_complete", encoding="utf-8")

        if ct2_dir.exists():
            import shutil
            shutil.rmtree(ct2_dir, ignore_errors=True)
        staging_ct2.rename(ct2_dir)
        return ct2_dir

    def _load_local_translation(self):
        if not self.model_is_installed(self.from_code, self.to_code, self.model_variant):
            return None

        model_dir = Path(self.model_dir(self.from_code, self.to_code, self.model_variant))
        self.model_dir_path = model_dir

        setup_windows_dll_directories()

        # Try fast CTranslate2 engine first
        try:
            import ctranslate2
            from transformers import AutoTokenizer

            ct2_dir = self._ensure_ctranslate2_model(model_dir)
            tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True, use_fast=False)

            num_threads = self._get_optimal_cpu_threads()
            translator = ctranslate2.Translator(
                str(ct2_dir),
                device="cpu",
                compute_type="int8",
                inter_threads=1,
                intra_threads=num_threads,
            )
            self.translation_device = "cpu"
            return "ctranslate2", tokenizer, translator, None
        except Exception as ct2_exc:
            # Fallback to PyTorch/Transformers pipeline if CTranslate2 fails or is unavailable
            try:
                import torch
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            except Exception as exc:
                raise RuntimeError(
                    f"OPUS-MT {self.model_variant} requires translation prerequisites (ctranslate2 / transformers). "
                    f"Details: {ct2_exc} / {exc}"
                ) from exc

            tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True, use_fast=False)
            model = AutoModelForSeq2SeqLM.from_pretrained(str(model_dir), local_files_only=True)
            model.eval()
            device = "cpu"
            model = model.to(device)
            self.translation_device = device
            return "transformers", tokenizer, model, torch

    def _translate_batches(self, engine_type, tokenizer, model_or_translator, torch_mod):
        results = list(self.resume_results)
        start_index = len(results)
        total = max(1, len(self.segments))
        if start_index > len(self.segments):
            results = []
            start_index = 0

        # Process in macro-chunks to maintain sequential progress and allow cancellation
        batch_size = 32 if engine_type == "ctranslate2" else 8

        for batch_start in range(start_index, len(self.segments), batch_size):
            if self._cancelled:
                self.cancelled.emit(results, f"{self.from_code}-{self.to_code}")
                return None

            batch = self.segments[batch_start:batch_start + batch_size]
            texts = [str(seg.get("text", "")).strip() for seg in batch]

            self.progress.emit(
                10 + int((batch_start / total) * 85),
                f"Translating segments {batch_start + 1}–{min(batch_start + len(batch), len(self.segments))} of {total}…",
            )

            nonempty_indices = [i for i, text in enumerate(texts) if text]
            translated_by_index = {i: "" for i in range(len(batch))}

            if nonempty_indices:
                nonempty_texts = [texts[i] for i in nonempty_indices]

                if engine_type == "ctranslate2":
                    try:
                        # Prepare input tokens using the HF tokenizer associated with the converted model
                        # MarianTokenizer encodes text into token IDs ending with </s> (EOS)
                        # convert_ids_to_tokens converts token IDs into strings matching the model vocabulary
                        source_tokens = [
                            tokenizer.convert_ids_to_tokens(
                                tokenizer.encode(text, truncation=True, max_length=512)
                            )
                            for text in nonempty_texts
                        ]

                        translations = model_or_translator.translate_batch(
                            source_tokens,
                            beam_size=2,
                            patience=1.0,
                            max_batch_size=32,
                            batch_type="examples",
                            repetition_penalty=1.2,
                            no_repeat_ngram_size=3,
                            max_decoding_length=256,
                            replace_unknowns=True,
                        )

                        for idx, res in zip(nonempty_indices, translations):
                            hyp_tokens = res.hypotheses[0] if res.hypotheses else []
                            token_ids = tokenizer.convert_tokens_to_ids(hyp_tokens)
                            try:
                                decoded_text = tokenizer.decode(token_ids, skip_special_tokens=True)
                            except Exception:
                                decoded_text = tokenizer.convert_tokens_to_string(hyp_tokens)
                            translated_by_index[idx] = decoded_text.strip()
                    except Exception:
                        # Fallback to robust transformers pipeline if ctranslate2 execution fails
                        model_dir = getattr(self, "model_dir_path", None)
                        if model_dir is None:
                            model_dir = Path(self.model_dir(self.from_code, self.to_code, self.model_variant))
                            self.model_dir_path = model_dir
                        import torch
                        from transformers import AutoModelForSeq2SeqLM
                        if not hasattr(self, "_fallback_hf_model"):
                            self._fallback_hf_model = AutoModelForSeq2SeqLM.from_pretrained(str(model_dir), local_files_only=True).eval()
                        hf_model = self._fallback_hf_model

                        encoded = tokenizer(
                            nonempty_texts,
                            return_tensors="pt",
                            padding=True,
                            truncation=True,
                            max_length=512,
                        )
                        with torch.inference_mode():
                            generated = hf_model.generate(
                                **encoded,
                                num_beams=2,
                                max_new_tokens=256,
                                repetition_penalty=1.2,
                                no_repeat_ngram_size=3,
                                early_stopping=True,
                            )
                        decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
                        for idx, text in zip(nonempty_indices, decoded):
                            translated_by_index[idx] = text.strip()
                else:
                    # PyTorch/Transformers fallback
                    encoded = tokenizer(
                        nonempty_texts,
                        return_tensors="pt",
                        padding=True,
                        truncation=True,
                        max_length=512,
                    )

                    if getattr(self, "translation_device", "cpu") != "cpu":
                        try:
                            encoded = {k: v.to(self.translation_device) for k, v in encoded.items()}
                        except Exception:
                            self.translation_device = "cpu"

                    with torch_mod.inference_mode():
                        generated = model_or_translator.generate(
                            **encoded,
                            num_beams=2,
                            max_new_tokens=256,
                            repetition_penalty=1.2,
                            no_repeat_ngram_size=3,
                            early_stopping=True,
                        )

                    decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
                    for idx, text in zip(nonempty_indices, decoded):
                        translated_by_index[idx] = text.strip()

            # Reconstruct 1:1 segment mappings preserving all original metadata and timestamps
            for i, segment in enumerate(batch):
                translated = translated_by_index[i]
                new_seg = copy.deepcopy(segment) if isinstance(segment, dict) else {}
                new_seg["text"] = translated if translated else segment.get("text", "")
                new_seg["start"] = float(segment.get("start", 0))
                new_seg["end"] = float(segment.get("end", 0))
                results.append(new_seg)

            completed = batch_start + len(batch)
            pct = 10 + int((completed / total) * 85)
            self.progress.emit(pct, f"Translated {completed} of {total} segments…")
            self.checkpoint.emit(results, f"{self.from_code}-{self.to_code}", completed)

        return results

    def run(self):
        try:
            if self.status_only:
                try:
                    for from_code, to_code in self.status_pairs:
                        if self._cancelled:
                            return
                        ok = self.model_is_installed(from_code, to_code, self.model_variant)
                        message = f"OPUS-MT {self.model_variant} installed" if ok else f"OPUS-MT {self.model_variant} not installed"
                        self.model_status.emit(from_code, to_code, ok, message)
                except Exception as exc:
                    for from_code, to_code in self.status_pairs:
                        self.model_status.emit(from_code, to_code, False, f"Unavailable: {exc}")
                finally:
                    self.model_status_finished.emit()
                return

            model_dir = self._ensure_model_installed()
            if self._cancelled or model_dir is None:
                self.cancelled.emit(self.resume_results, f"{self.from_code}-{self.to_code}")
                return
            if self.installation_only:
                self.progress.emit(100, "OPUS-MT model installed and ready.")
                self.finished.emit([], f"{self.from_code}-{self.to_code}")
                return

            self.progress.emit(5, "Loading OPUS-MT model into memory…")
            engine_type, tokenizer, model_or_translator, torch_mod = self._load_local_translation()
            if self._cancelled:
                self.cancelled.emit(self.resume_results, f"{self.from_code}-{self.to_code}")
                return
            results = self._translate_batches(engine_type, tokenizer, model_or_translator, torch_mod)
            if results is not None and not self._cancelled:
                self.progress.emit(100, "Translation complete.")
                self.finished.emit(results, f"{self.from_code}-{self.to_code}")
        except Exception as exc:
            if not self._cancelled:
                self.error.emit(str(exc))
            else:
                self.cancelled.emit(self.resume_results, f"{self.from_code}-{self.to_code}")