"""Radio & TV Segmenter v1.1.1 — project export responsibilities.

Methods intentionally retain the MainWindow-facing API so behavior remains
maintaining the established MainWindow-facing API while responsibilities are isolated.
"""

from prs_shared import *
import webbrowser
import zipfile
from wordpress_export import generate_wp_excerpt, WordPressSettingsDialog, _get_wp_password


from export.pdf import TranscriptPdfWriter
from export.subtitles import (
    seconds_to_cue_time,
    generate_cue_sheet,
    generate_youtube_chapters,
    generate_srt_content,
    generate_vtt_content,
    generate_cue_content,
)
from export.docx import create_story_docx
from export.dialog import UnifiedExportDialog
from plugins.youtube.guide_dialog import YouTubeAssistedUploadGuideDialog


def show_export_completion_dialog(parent, title: str, message: str, export_path: str = ""):
    """Displays export completion with an actionable 'Open Folder' button (Milestone 3.11)."""
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(message)
    box.setIcon(QMessageBox.Icon.Information)

    open_btn = box.addButton("Open Folder", QMessageBox.ButtonRole.ActionRole)
    close_btn = box.addButton("Close", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(close_btn)

    box.exec()
    if box.clickedButton() == open_btn and export_path:
        folder_to_open = Path(export_path)
        if folder_to_open.is_file():
            folder_to_open = folder_to_open.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder_to_open)))


class ProjectExportMixin:
    def close_project(self, prompt=True):
        if prompt and self.project_dirty:
            answer = QMessageBox.question(
                self,
                "Close Project",
                "Close current project? Unsaved changes will be lost.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False

        try:
            if not self.stop_video_thumbnail_worker():
                QMessageBox.warning(self, "Thumbnail Worker Still Running", "Video thumbnails are still being generated. Please wait a few seconds and close again.")
                return False
        except Exception:
            pass
        if not self.stop_all_processing(timeout_ms=5000):
            QMessageBox.warning(self, "Close Project", "A processing worker could not be stopped safely. The project was not closed.")
            return False
        self.media_generation += 1
        self.story_job_token += 1

        if self.player:
            self.player.stop()
            self.player.setSource(QUrl())

        self.audio_file = None
        self.project_file = None
        self.transcript = None
        self.diarization = None
        self.speaker_names = {}
        self.segment_speaker_overrides = {}
        self.stories = []
        self.current_selected_story_indices = []
        self.duration = 0
        self.current_position = 0

        self.undo_stack.clear()
        self.activity_snapshots.clear()

        self.set_tools_actions_enabled(False)
        self.save_action.setEnabled(False)
        self.save_as_action.setEnabled(False)

        self.play_button.setText("▶ Play")
        self.time_label.setText("00:00.000 / 00:00.000")
        self.speaker_status.setText("Speaker detection has not been run.")

        self.transcript_view.clear()
        self.transcript_view.set_char_timestamp_map([])
        self.story_list.clear()
        self.activity_list.clear()

        self.start_input.clear()
        self.end_input.clear()
        self.title_input.clear()
        if hasattr(self, "story_boundary_container"):
            self.story_boundary_container.setVisible(False)

        self.timeline.set_duration(1)
        self.timeline.set_position(0)
        self.timeline.set_stories([])
        self.timeline.set_waveform_peaks([])
        self.timeline.set_zoom(1.0)
        self.timeline.scroll_offset = 0.0
        self.timeline.set_audio_filename(None)
        if hasattr(self.timeline, "set_video_thumbnails"):
            self.timeline.set_video_thumbnails([])
        self.video_thumbnail_dir = None

        self.update_window_title()
        try:
            cleanup_old_thumbnail_cache(24)
        except Exception:
            pass
        self.log_activity("[FILE] Project closed.", mark_dirty=False)
        self.statusBar().showMessage("Project closed.")
        return True

    def new_project(self):
        if self.close_project(prompt=True):
            self.open_audio()

    def project_audio_reference(self):
        if not self.audio_file:
            return None
        try:
            if self.project_file:
                return os.path.relpath(self.audio_file, self.project_file.parent)
        except ValueError:
            pass
        return str(self.audio_file)

    def project_data(self):
        return {
            "format": "Radio & TV Story Segmenter Project",
            "version": PROJECT_VERSION,
            "audio_file": self.project_audio_reference(),
            "audio_file_abs": str(Path(self.audio_file).resolve()) if self.audio_file else None,
            "duration": self.duration,
            "transcript": self.transcript,
            "transcript_notes": getattr(self, "transcript_notes", ""),
            "diarization": self.diarization,
            "speaker_names": self.speaker_names,
            "segment_speaker_overrides": self.segment_speaker_overrides,
            "translations": self.translations,
            "translation_display_mode": self.translation_display_mode,
            "stories": [story.to_dict() for story in self.stories],
            "plugins_data": getattr(self, "plugins_project_data", {}),
            "settings": {
                "auto_save_minutes": self.auto_save_minutes,
                "skip_seconds": self.skip_seconds,
                "whisper_model": self.whisper_model,
                "translation_model_variant": self.translation_model_variant,
                "silence_threshold": self.silence_threshold,
                "lead_in_padding": self.lead_in_padding,
                "expected_speakers": getattr(self, "expected_speakers", "auto"),
                "show_speaker_labels": self.show_speaker_labels,
                "show_timestamps": self.show_timestamps,
                "language": self.language,
            },
            "processing_status": dict(self.processing_status),
            "session": {
                "position": self.current_position,
                "timeline_zoom": getattr(self.timeline, "zoom_level", 1.0),
                "timeline_scroll_offset": getattr(self.timeline, "scroll_offset", 0.0),
                "selected_story_indices": list(self.current_selected_story_indices),
                "video_preview_visible": bool(self.video_preview_dialog and self.video_preview_dialog.isVisible()),
            },
        }

    def _write_project_file(self, file_path: str):
        """Writes project state dictionary directly to disk."""
        destination = Path(file_path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.project_file = destination

        # Determine media ingest mode (ask vs copy vs reference)
        media_mode = str(self.settings_store.value("media_ingest_mode", "reference")).strip().lower()
        copy_media = str(self.settings_store.value("copy_media_to_project_folder", "false")).lower() in {"1", "true", "yes"} or media_mode == "copy"

        if media_mode == "ask" and self.audio_file and Path(self.audio_file).exists():
            src_media = Path(self.audio_file).resolve()
            if src_media.parent != destination.parent and src_media.parent != (destination.parent / "Media"):
                res = QMessageBox.question(
                    self,
                    "Copy Media to Project Folder?",
                    f"Would you like to copy the media file ('{src_media.name}') into the project bundle folder for portability?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Yes,
                )
                if res == QMessageBox.StandardButton.Cancel:
                    return False
                copy_media = (res == QMessageBox.StandardButton.Yes)

        if copy_media and self.audio_file and Path(self.audio_file).exists():
            src_media = Path(self.audio_file).resolve()
            media_subfolder = destination.parent / "Media"
            if media_subfolder.is_dir() or str(self.settings_store.value("create_project_subfolders", "true")).lower() in {"1", "true", "yes"}:
                media_subfolder.mkdir(parents=True, exist_ok=True)
                target_media = media_subfolder / src_media.name
            else:
                target_media = destination.parent / src_media.name

            if target_media.resolve() != src_media:
                try:
                    shutil.copy2(src_media, target_media)
                    self.audio_file = target_media
                    self.log_activity(f"[PROJECT] Copied media file to project folder: {target_media.name}", mark_dirty=False)
                except Exception as exc:
                    self.log_activity(f"[WARNING] Could not copy media to project folder: {exc}", mark_dirty=False)

        # Ensure dedicated waveform peak cache is saved alongside project inside .cache/peaks/
        if self.audio_file and getattr(self.timeline, "waveform_peaks", None):
            try:
                write_waveform_peak_cache(self.audio_file, self.timeline.waveform_peaks, project_file=destination)
            except Exception:
                pass

        data = self.project_data()
        errors = self.validate_project_data(data)
        if errors:
            raise ValueError("Validation failed: " + "; ".join(errors))

        write_rtvs_project_file(destination, data)
        self.project_dirty = False
        self._remember_saved_project(str(destination))
        self.update_window_title()

    # In project_export.py -> ProjectExportMixin class

    def prepare_export_directories(self, target_base_dir=None, default_name=None, prompt_user=True):
        """Resolves:
          ├── [project_dir]/
          │   ├── [project_file].json
          │   ├── Transcripts/
          │   └── Media/
        If the current project is already saved in a dedicated project directory
        (like Bellevue/) that contains Transcripts/ or Media/, it reuses it directly
        without asking for another folder name or parent directory.
        """
        create_bundle = str(self.settings_store.value("create_project_subfolders", "true")).lower() in {"1", "true", "yes"}

        # 1. Check if an active project is already open in an existing bundle folder
        if target_base_dir is None and self.project_file:
            active_parent = self.project_file.parent
            has_transcripts = (active_parent / "Transcripts").is_dir()
            has_media = (active_parent / "Media").is_dir()

            # If inside a folder like 'Bellevue' with Transcripts/ or Media/ present, reuse it immediately
            if has_transcripts or has_media or active_parent.name == self.project_file.stem:
                transcripts_dir = active_parent / "Transcripts"
                media_dir = active_parent / "Media"
                transcripts_dir.mkdir(parents=True, exist_ok=True)
                media_dir.mkdir(parents=True, exist_ok=True)
                return active_parent, transcripts_dir, media_dir, self.project_file.stem

        # 2. Fallback to passed directory, default project directory, or media folder
        if target_base_dir is None:
            target_base_dir = self.get_default_save_directory()

        fallback_name = safe_filename(
            default_name 
            or (self.project_file.stem if self.project_file else None)
            or (self.audio_file.stem if self.audio_file else "export")
        )

        folder_name = fallback_name
        base_path = Path(target_base_dir)

        # 3. If target_base_dir is already the project folder (e.g. user selected 'Bellevue' or it contains subfolders)
        if (base_path / "Transcripts").is_dir() or (base_path / "Media").is_dir() or base_path.name == fallback_name:
            project_dir = base_path
            transcripts_dir = project_dir / "Transcripts"
            media_dir = project_dir / "Media"
            transcripts_dir.mkdir(parents=True, exist_ok=True)
            media_dir.mkdir(parents=True, exist_ok=True)
            return project_dir, transcripts_dir, media_dir, base_path.name

        # 4. Prompt user only if creating a new subfolder and prompt_user is True
        if prompt_user and create_bundle:
            dialog_name, ok = QInputDialog.getText(
                self,
                "Project Folder Name",
                "Enter folder name for project and export subfolders:",
                QLineEdit.EchoMode.Normal,
                fallback_name
            )
            if not ok:
                return None, None, None, None
            folder_name = safe_filename(dialog_name.strip()) or fallback_name

        if create_bundle:
            project_dir = base_path / folder_name
            transcripts_dir = project_dir / "Transcripts"
            media_dir = project_dir / "Media"
        else:
            project_dir = base_path
            transcripts_dir = base_path
            media_dir = base_path

        project_dir.mkdir(parents=True, exist_ok=True)
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        media_dir.mkdir(parents=True, exist_ok=True)

        return project_dir, transcripts_dir, media_dir, folder_name
        
    def get_default_save_directory(self) -> str:
        """Returns target base directory based on preferences and loaded media."""
        save_with_media = (
            str(self.settings_store.value("save_project_with_media", "false")).lower() in {"1", "true", "yes"}
        )
        if save_with_media and self.audio_file:
            media_path = Path(self.audio_file)
            if media_path.exists():
                return str(media_path.parent)

        if getattr(self, "default_project_directory", ""):
            return str(self.default_project_directory)

        return str(Path.home())

    def save_project_as(self) -> bool:
        if not self.audio_file and not self.transcript:
            return False

        base_name = safe_filename(
            Path(self.audio_file).stem if self.audio_file else "project"
        )
        target_base_dir = Path(self.get_default_save_directory())
        create_bundle = str(self.settings_store.value("create_project_subfolders", "true")).lower() in {"1", "true", "yes"}

        if getattr(self, "batch_active", False) and hasattr(self, "batch_settings"):
            out_setting = self.batch_settings.get("output")
            out_dir = Path(out_setting) if out_setting and os.path.exists(out_setting) else target_base_dir

            if create_bundle:
                project_bundle_dir = out_dir / base_name
                project_bundle_dir.mkdir(parents=True, exist_ok=True)
                file_path = str(project_bundle_dir / f"{base_name}.rtvs")
            else:
                out_dir.mkdir(parents=True, exist_ok=True)
                file_path = str(out_dir / f"{base_name}.rtvs")

            self._write_project_file(file_path)
            self.log_activity(f"[BATCH] Auto-saved project to {file_path}")
            return True

        # Interactive Save As dialog
        if create_bundle:
            initial_path = str(target_base_dir / base_name / f"{base_name}.rtvs")
        else:
            initial_path = str(target_base_dir / f"{base_name}.rtvs")

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project As",
            initial_path,
            "RadioTV Story Segmenter Projects (*.rtvs);;Legacy Projects (*.json);;All Files (*.*)"
        )
        if file_path:
            target_path = Path(file_path)
            if create_bundle:
                (target_path.parent / "Transcripts").mkdir(parents=True, exist_ok=True)
                (target_path.parent / "Media").mkdir(parents=True, exist_ok=True)

            self._write_project_file(str(target_path))
            return True
        return False

    def export_project_archive(self, destination_zip=None) -> bool:
        """Export current project state, transcripts, and media into a self-contained portable .zip archive."""
        if not self.audio_file and not self.transcript and not getattr(self, "stories", None):
            QMessageBox.information(
                self,
                "Export Project Archive",
                "No project data or media is currently loaded to export."
            )
            return False

        base_name = safe_filename(
            Path(self.audio_file).stem if self.audio_file else "project"
        )
        target_base_dir = Path(self.get_default_save_directory())

        if not destination_zip:
            default_path = str(target_base_dir / f"{base_name}_archive.zip")
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Project Archive (.zip)",
                default_path,
                "Zip Archives (*.zip);;All Files (*.*)"
            )
            if not file_path:
                return False
            destination_zip = Path(file_path)
        else:
            destination_zip = Path(destination_zip)

        destination_zip.parent.mkdir(parents=True, exist_ok=True)

        try:
            data = self.project_data()
            if self.audio_file and Path(self.audio_file).exists():
                media_path = Path(self.audio_file).resolve()
                data["audio_reference"] = f"Media/{media_path.name}"
                data["audio_file_name"] = media_path.name
                data["audio_duration"] = float(getattr(self, "audio_duration", 0.0) or 0.0)

            with zipfile.ZipFile(destination_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                # 1. Project file inside zip
                proj_json_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
                zf.writestr(f"{base_name}.rtvs", proj_json_bytes)

                # 2. Source Media file
                if self.audio_file and Path(self.audio_file).exists():
                    media_path = Path(self.audio_file).resolve()
                    zf.write(media_path, arcname=f"Media/{media_path.name}")

                # 3. Waveform Peak Cache if available
                if self.audio_file and getattr(self.timeline, "waveform_peaks", None):
                    peaks = self.timeline.waveform_peaks
                    peak_bytes = json.dumps({"peaks": [float(p) for p in peaks]}).encode("utf-8")
                    zf.writestr(".cache/peaks.json", peak_bytes)

            self.log_activity(f"[PROJECT] Exported self-contained project archive to {destination_zip}")
            show_export_completion_dialog(
                self,
                title="Project Archive Exported",
                message=f"Successfully exported self-contained project archive:\n\n{destination_zip.name}",
                export_path=str(destination_zip)
            )
            return True
        except Exception as exc:
            self.log_activity(f"[ERROR] Failed to export project archive: {exc}")
            QMessageBox.critical(
                self,
                "Archive Export Failed",
                f"Could not export project archive:\n{exc}"
            )
            return False

    def ensure_project_for_processing_pipeline(self) -> bool:
        """
        Ensures a project file is established on disk before running multi-stage
        automated pipelines so progress can be safely saved between stages.
        """
        if getattr(self, "project_file", None):
            return True

        if getattr(self, "batch_active", False):
            return bool(self.save_project_as())

        if self.audio_file or self.transcript:
            reply = QMessageBox.question(
                self,
                "Save Project",
                "Multi-stage automated processing saves progress to your project file after each stage.\n\n"
                "Would you like to save this project now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                return bool(self.save_project_as())
            return False

        return False

    def validate_project_data(self, data):
        """Return a list of structural project-data problems before saving."""
        errors = []
        if data.get("format") != "Radio & TV Story Segmenter Project":
            errors.append("Invalid project format.")
        duration = data.get("duration", 0)
        try:
            if float(duration) < 0:
                errors.append("Media duration cannot be negative.")
        except (TypeError, ValueError):
            errors.append("Media duration is not numeric.")

        transcript = data.get("transcript")
        if transcript is not None:
            segments = transcript.get("segments") if isinstance(transcript, dict) else None
            if not isinstance(segments, list):
                errors.append("Transcript segments are missing or invalid.")
            else:
                for i, seg in enumerate(segments):
                    if not isinstance(seg, dict):
                        errors.append(f"Transcript segment {i + 1} is invalid.")
                        continue
                    try:
                        if float(seg.get("start", 0)) > float(seg.get("end", 0)):
                            errors.append(f"Transcript segment {i + 1} has an invalid time range.")
                    except (TypeError, ValueError):
                        errors.append(f"Transcript segment {i + 1} has invalid timestamps.")

        stories = data.get("stories", [])
        if not isinstance(stories, list):
            errors.append("Stories data is not a list.")
        else:
            for i, story in enumerate(stories):
                try:
                    start = float(story.get("start", 0))
                    end = float(story.get("end", 0))
                    if start < 0 or end < start:
                        errors.append(f"Story {i + 1} has an invalid time range.")
                except (AttributeError, TypeError, ValueError):
                    errors.append(f"Story {i + 1} is invalid.")
        return errors

    def save_project(self, force=True):
        if not self.audio_file:
            return False
        if not self.project_file:
            return self.save_project_as()
        if not force and not self.project_dirty:
            return True
        if self.save_in_progress:
            return False

        self.save_in_progress = True
        temp_file = self.project_file.with_name(self.project_file.name + ".tmp")
        backup_file = self.project_file.with_name(self.project_file.name + ".backup")
        try:
            self.project_file.parent.mkdir(parents=True, exist_ok=True)

            # Optional: Copy source media file into project folder
            copy_media = str(self.settings_store.value("copy_media_to_project_folder", "false")).lower() in {"1", "true", "yes"}
            if copy_media and self.audio_file and Path(self.audio_file).exists():
                src_media = Path(self.audio_file).resolve()
                media_subfolder = self.project_file.parent / "Media"
                if media_subfolder.is_dir() or str(self.settings_store.value("create_project_subfolders", "true")).lower() in {"1", "true", "yes"}:
                    media_subfolder.mkdir(parents=True, exist_ok=True)
                    target_media = media_subfolder / src_media.name
                else:
                    target_media = self.project_file.parent / src_media.name

                if target_media.resolve() != src_media:
                    try:
                        shutil.copy2(src_media, target_media)
                        self.audio_file = target_media
                        self.log_activity(f"[PROJECT] Copied media file to project folder: {target_media.name}", mark_dirty=False)
                    except Exception as exc:
                        self.log_activity(f"[WARNING] Could not copy media to project folder: {exc}", mark_dirty=False)

            # Ensure dedicated waveform peak cache is saved alongside project
            if self.audio_file and getattr(self.timeline, "waveform_peaks", None):
                try:
                    write_waveform_peak_cache(self.audio_file, self.timeline.waveform_peaks)
                except Exception:
                    pass

            data = self.project_data()
            errors = self.validate_project_data(data)
            if errors:
                message = "Project validation failed:\n\n" + "\n".join(f"• {item}" for item in errors)
                self.log_activity(f"[ERROR] Project validation failed: {'; '.join(errors)}", mark_dirty=False)
                QMessageBox.critical(self, "Project Validation Error", message)
                return False

            if self.project_file.exists():
                shutil.copy2(self.project_file, backup_file)
                self.log_activity(f"[PROJECT] Previous project saved as recovery backup: {backup_file.name}", mark_dirty=False)

            write_rtvs_project_file(self.project_file, data)
            # A successful explicit save supersedes its recovery snapshot.
            try:
                self.project_file.with_suffix(self.project_file.suffix + ".autosave").unlink(missing_ok=True)
            except Exception:
                pass
            self.project_dirty = False
            self._remember_saved_project(str(self.project_file))
            self.update_window_title()
            saved_time = QTime.currentTime().toString("hh:mm:ss A")
            if hasattr(self, "save_state_label"):
                self.save_state_label.setText(f"✓ Saved {saved_time}")
            self.statusBar().showMessage(f"Project saved: {self.project_file.name}")
            return True
        except Exception as exc:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception:
                pass
            self.log_activity(f"[ERROR] Project save failed: {exc}", mark_dirty=False)
            QMessageBox.critical(self, "Save Error", str(exc))
            return False
        finally:
            self.save_in_progress = False

    def find_adjacent_project(self, media_path):
        # A project is now named after its source media file:
        # episode.mp4 -> episode.rtvs (or legacy episode.json)
        candidates = [
            media_path.parent / f"{media_path.stem}.rtvs",
            media_path.parent / f"{media_path.stem}.json",
            media_path.parent / media_path.stem / f"{media_path.stem}.rtvs",
            media_path.parent / media_path.stem / f"{media_path.stem}.json",
        ]
        for candidate in candidates:
            if not candidate.exists() or not candidate.is_file():
                continue
            try:
                data = read_rtvs_project_file(candidate)
                ref = data.get("audio_file")
                if not ref:
                    continue
                ref_path = Path(ref)
                if not ref_path.is_absolute():
                    ref_path = candidate.parent / ref_path
                if ref_path.resolve() == media_path.resolve():
                    return candidate.resolve()
            except Exception:
                continue
        return None

    # Extensions resolve_project_media() will accept as a project's media file.
    # A project file (.rtvs) can reference an arbitrary path; without this
    # whitelist, opening a malicious project could resolve to -- and, with
    # "Copy media file to project folder" enabled, copy -- an arbitrary
    # non-media file the victim happens to have on disk. Deliberately broad
    # (covers less-common containers too) since the media-open dialog itself
    # imposes no extension restriction ("Media Files (*.*)") -- the goal here
    # is excluding non-media files, not second-guessing which media formats
    # a user may have legitimately opened.
    _VALID_MEDIA_EXTENSIONS = {
        ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wma",
        ".aiff", ".aif", ".caf", ".amr", ".ac3", ".dts", ".ra", ".rm",
        ".mp4", ".m4v", ".mov", ".mkv", ".avi", ".webm", ".wmv", ".mpg", ".mpeg",
        ".3gp", ".3g2", ".ts", ".mts", ".m2ts", ".asf", ".flv",
    }

    def resolve_project_media(self, project_file, audio_reference, audio_file_abs=None):
        def _is_valid_media_candidate(candidate: Path) -> bool:
            return candidate.exists() and candidate.is_file() and candidate.suffix.lower() in self._VALID_MEDIA_EXTENSIONS

        # 1. Check remembered absolute path if available and exists on disk
        if audio_file_abs:
            abs_candidate = Path(audio_file_abs).expanduser().resolve()
            if _is_valid_media_candidate(abs_candidate):
                return abs_candidate

        if not audio_reference:
            return None

        ref_path = Path(audio_reference)

        # 2. Check audio_reference if already absolute and exists
        if ref_path.is_absolute():
            cand = ref_path.resolve()
            if _is_valid_media_candidate(cand):
                return cand

        proj_dir = project_file.parent

        # 3. Check relative to project_file.parent
        rel_candidate = (proj_dir / ref_path).resolve()
        if _is_valid_media_candidate(rel_candidate):
            return rel_candidate

        # 4. Check inside Media/ subfolder in project dir
        media_candidate = (proj_dir / "Media" / ref_path.name).resolve()
        if _is_valid_media_candidate(media_candidate):
            return media_candidate

        # 5. Check direct basename in project directory
        basename_candidate = (proj_dir / ref_path.name).resolve()
        if _is_valid_media_candidate(basename_candidate):
            return basename_candidate

        # 6. Check in default projects directory
        default_dir = getattr(self, "default_project_directory", "")
        if default_dir:
            cand = (Path(default_dir) / ref_path.name).resolve()
            if _is_valid_media_candidate(cand):
                return cand

        # 7. Check in last media directory
        last_media = getattr(self, "last_media_directory", "")
        if last_media:
            cand = (Path(last_media) / ref_path.name).resolve()
            if _is_valid_media_candidate(cand):
                return cand

        return None

    def load_project_file(self, filename, prompt=True, preserve_media=False):
        project_path = Path(filename).resolve()
        # Handle self-contained .zip project archives
        if project_path.suffix.lower() == ".zip":
            try:
                extract_dir = project_path.parent / project_path.stem
                extract_dir.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(project_path, "r") as zf:
                    safe_extract_zip(zf, extract_dir)
                candidate_rtvs = list(extract_dir.glob("*.rtvs")) or list(extract_dir.glob("*.json"))
                if candidate_rtvs:
                    self.log_activity(f"[PROJECT] Extracted archive {project_path.name} to {extract_dir.name}", mark_dirty=False)
                    return self.load_project_file(str(candidate_rtvs[0]), prompt=prompt, preserve_media=preserve_media)
            except Exception as z_exc:
                self.log_activity(f"[ERROR] Could not extract zip archive {project_path.name}: {z_exc}", mark_dirty=False)
                if not preserve_media:
                    QMessageBox.critical(self, "Archive Error", f"Failed to extract project archive:\n{z_exc}")
                return False

        try:
            data = read_rtvs_project_file(project_path)
        except Exception as exc:
            backup_path = project_path.with_name(project_path.name + ".backup")
            if backup_path.exists():
                answer = QMessageBox.question(
                    self, "Project Recovery",
                    f"The project file could not be read:\n\n{project_path.name}\n\n"
                    f"A recovery backup was found ({backup_path.name}). Would you like to open the backup instead?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if answer == QMessageBox.StandardButton.Yes:
                    try:
                        data = read_rtvs_project_file(backup_path)
                        self.log_activity(f"[PROJECT] Recovered project from backup: {backup_path.name}", mark_dirty=False)
                    except Exception as backup_exc:
                        self.log_activity(f"[ERROR] Project recovery backup could not be read: {backup_exc}", mark_dirty=False)
                        if not preserve_media:
                            QMessageBox.critical(self, "Load Error", str(backup_exc))
                        return False
                else:
                    if not preserve_media:
                        QMessageBox.critical(self, "Load Error", str(exc))
                    return False
            else:
                self.log_activity(f"[ERROR] Could not read project file '{project_path.name}': {exc}", mark_dirty=False)
                if not preserve_media:
                    QMessageBox.critical(self, "Load Error", str(exc))
                return False

        if data.get("format") not in (None, "Radio & TV Story Segmenter Project"):
            QMessageBox.warning(self, "Load Project", "This file is not a Radio & TV Story Segmenter project.")
            return False

        if not preserve_media and not self.confirm_stop_processing_for_media_change():
            return False
        if not preserve_media and not self.close_project(prompt=prompt):
            return False

        self.project_file = project_path
        audio_path = self.resolve_project_media(project_path, data.get("audio_file"), data.get("audio_file_abs"))

        if audio_path is None and data.get("audio_file"):
            answer = QMessageBox.question(
                self, "Media File Missing",
                "The media file saved with this project could not be found.\n\nWould you like to locate it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                located, _ = QFileDialog.getOpenFileName(
                    self, "Locate Project Media", str(project_path.parent),
                    "Media Files (*.*);;All Files (*)",
                )
                if located:
                    audio_path = Path(located).resolve()

        if audio_path is not None:
            self.stop_waveform_worker()
            self.stop_video_thumbnail_worker()
            self.audio_file = audio_path
            self.player.setSource(QUrl.fromLocalFile(str(audio_path)))
            self.current_media_is_video = self.is_video_file(audio_path)
            self.update_video_preview_state()
            if hasattr(self, "timeline") and hasattr(self.timeline, "set_is_video"):
                self.timeline.set_is_video(self.current_media_is_video)
            self.timeline.set_audio_filename(audio_path.name)
            self.timeline.set_waveform_peaks([])

            # Restore pre-calculated waveform peaks from disk cache or legacy project file
            cached_peaks = read_waveform_peak_cache(audio_path, project_file=project_path)
            if not cached_peaks:
                cached_peaks = data.get("waveform_peaks")
            if cached_peaks:
                self.timeline.set_waveform_peaks(cached_peaks)
                self.log_activity(f"[WAVEFORM] Loaded cached waveform ({len(cached_peaks):,} peaks).", mark_dirty=False)
            else:
                self.load_waveform_async()
        else:
            self.audio_file = None
            self.current_media_is_video = False
            self.update_video_preview_state()
            if hasattr(self, "timeline") and hasattr(self.timeline, "set_is_video"):
                self.timeline.set_is_video(False)

        self.duration = float(data.get("duration") or 0)
        if self.duration > 0:
            self.timeline.set_duration(self.duration)
            if self.current_media_is_video:
                QTimer.singleShot(0, self.start_video_thumbnail_generation)
        self.transcript = data.get("transcript")
        self.transcript_notes = str(data.get("transcript_notes", ""))
        self.diarization = data.get("diarization")
        self.speaker_names = {str(k): str(v) for k, v in data.get("speaker_names", {}).items() if str(v).strip()}
        self.segment_speaker_overrides = {int(k): str(v) for k, v in data.get("segment_speaker_overrides", {}).items()}
        self.stories = [Story.from_dict(item) for item in data.get("stories", [])]
        self.plugins_project_data = dict(data.get("plugins_data", {})) if isinstance(data.get("plugins_data"), dict) else {}
        self.translations = data.get("translations", {}) if isinstance(data.get("translations", {}), dict) else {}
        self.translation_display_mode = str(data.get("translation_display_mode", "en"))
        if self.translation_display_mode == "bilingual":
            self.translation_display_mode = "split"
        elif self.translation_display_mode not in {"en", "es", "split"}:
            self.translation_display_mode = "en"
        self.update_translation_language_selector()
        if hasattr(self, "transcript_language_selector"):
            idx = self.transcript_language_selector.findData(self.translation_display_mode)
            if idx >= 0:
                self.transcript_language_selector.blockSignals(True)
                self.transcript_language_selector.setCurrentIndex(idx)
                self.transcript_language_selector.blockSignals(False)

        settings = data.get("settings", {})
        self.auto_save_minutes = float(settings.get("auto_save_minutes", data.get("auto_save_minutes", 5)))
        self.skip_seconds = float(settings.get("skip_seconds", data.get("skip_seconds", 5)))
        # Transcription Model is a global user preference, not a project setting.
        saved_global_whisper = str(self.settings_store.value("whisper_model", getattr(self, "whisper_model", "parakeet-onnx")) or "parakeet-onnx")
        allowed_whisper = {"parakeet-onnx", "tiny", "base", "small", "distil-medium.en", "medium", "distil-large-v3", "large-v3"}
        self.whisper_model = saved_global_whisper if saved_global_whisper in allowed_whisper else "parakeet-onnx"
        self.settings_store.setValue("whisper_model", self.whisper_model)
        self.settings_store.sync()
        self.translation_model_variant = str(settings.get("translation_model_variant", data.get("translation_model_variant", "tiny")))
        if self.translation_model_variant not in {"tiny", "standard"}: self.translation_model_variant = "tiny"
        self.silence_threshold = float(settings.get("silence_threshold", data.get("silence_threshold", 3.0)))
        self.lead_in_padding = float(settings.get("lead_in_padding", data.get("lead_in_padding", 0.5)))
        # "expected_speakers" replaces the old "speaker_sensitivity" (1-10) setting;
        # projects saved by older builds only have the latter, which no longer maps
        # to anything meaningful, so such projects just fall back to "auto".
        self.expected_speakers = str(settings.get("expected_speakers", data.get("expected_speakers", "auto")) or "auto")
        self.show_speaker_labels = bool(settings.get("show_speaker_labels", self.show_speaker_labels))
        self.show_timestamps = bool(settings.get("show_timestamps", self.show_timestamps))
        self.language = str(settings.get("language", self.language)) if str(settings.get("language", self.language)) in {"en","es"} else self.language
        self._apply_localization()
        if hasattr(self, "show_speaker_labels_action"):
            self.show_speaker_labels_action.setChecked(self.show_speaker_labels)
            self.show_timestamps_action.setChecked(self.show_timestamps)
        self.timeline.set_skip_seconds(self.skip_seconds)
        if hasattr(self, "skip_display"):
            self.skip_display.setValue(int(self.skip_seconds))
        self.refresh_whisper_model_chooser()
        saved_status = data.get("processing_status", {})
        self.processing_status = {
            "transcription": bool(saved_status.get("transcription", bool(self.transcript))),
            "diarization": bool(saved_status.get("diarization", bool(self.diarization))),
            "stories": bool(saved_status.get("stories", bool(self.stories))),
        }
        self.update_processing_stage_summary()
        self.update_auto_save_timer()

        session = data.get("session", {})
        position = max(0.0, min(float(session.get("position", 0) or 0), self.duration or float("inf")))
        self.current_position = position
        self.timeline.set_position(position)
        self.timeline.set_zoom(float(session.get("timeline_zoom", 1.0) or 1.0))
        self.timeline.scroll_offset = float(session.get("timeline_scroll_offset", 0.0) or 0.0)
        self.current_selected_story_indices = [int(i) for i in session.get("selected_story_indices", []) if 0 <= int(i) < len(self.stories)]

        if self.audio_file:
            self.transcribe_action.setEnabled(True)
            self.diarize_action.setEnabled(True)
            self.auto_detect_action.setEnabled(True)
            self.transcribe_diarize_action.setEnabled(True)
            self.transcribe_diarize_detect_action.setEnabled(True)
            self.save_action.setEnabled(True)
            self.save_as_action.setEnabled(True)
            if hasattr(self, "quick_save_button"):
                self.quick_save_button.setEnabled(True)

        if self.diarization:
            number = self.diarization.get("num_speakers", 0)
            self.speaker_status.setText(f"Speaker detection loaded: {number} speaker(s).")
        else:
            self.speaker_status.setText("Speaker detection has not been run.")

        self.set_tools_actions_enabled(True)
        self.render_transcript()
        self.refresh_story_list()
        self.project_dirty = False
        self.update_window_title()
        self.log_activity(f"[FILE] Loaded project: {project_path.name}", mark_dirty=False)
        self.log_activity(
            f"[PROJECT] Restored transcript={bool(self.transcript)}, diarization={bool(self.diarization)}, "
            f"speaker names={len(self.speaker_names)}, stories={len(self.stories)}.",
            mark_dirty=False,
        )
        self.project_dirty = False
        self.update_window_title()

        if session.get("video_preview_visible") and self.current_media_is_video and self.video_preview_action:
            self.video_preview_action.setChecked(False)
            self.toggle_video_preview(True)

        # Remember this project so launch startup and recent projects track it reliably
        self._remember_saved_project(str(project_path))

        self.statusBar().showMessage("Project loaded.")
        return True

    def load_project(self, filename=None):
        if not filename:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Load Project", self._dialog_directory(),
                "RadioTV Story Segmenter Projects (*.rtvs);;Legacy Projects (*.json);;All Files (*.*)",
            )
        if filename:
            try:
                directory = str(Path(filename).resolve().parent)
                self.settings_store.setValue("last_open_directory", directory)
                self.settings_store.sync()
            except Exception:
                pass
            return self.load_project_file(filename, prompt=True, preserve_media=False)
        return False

    def trigger_export(self):
        """Standard trigger for Export (File menu Ctrl+E / toolbar)."""
        self.open_unified_export_dialog()

    def export_full_transcript(self):
        """Triggered from the Export Transcript button above the transcript view."""
        self.open_unified_export_dialog(initial_scope="full")

    def open_export_scope_dialog(self):
        """Standard trigger for the main toolbar Export button."""
        self.open_unified_export_dialog()

    def open_unified_export_dialog(self, initial_scope=None, initial_dest=None):
        """Unified Export Dialog entry point for local file exports, WordPress publishing, and YouTube Studio assisted exports."""
        if not self.transcript and not self.audio_file:
            QMessageBox.warning(self, "Nothing to Export", "There is no transcript or media available to export.")
            return

        if initial_scope is None:
            sel = getattr(self, "current_selected_story_indices", [])
            if sel:
                initial_scope = "selected_stories"
            elif getattr(self, "stories", []):
                initial_scope = "all_stories"
            else:
                initial_scope = "full"

        dialog = UnifiedExportDialog(self, initial_scope=initial_scope, initial_dest=initial_dest)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        result = dialog.get_result()
        dest = result.get("destination", "local")
        scope = result.get("scope", "full")

        if dest == "local":
            formats = result.get("formats", {})
            base = result.get("base", "")
            options = result.get("options", {})
            export_dir = result.get("export_dir")
            is_custom = bool(export_dir and os.path.isdir(export_dir))

            # Check if user explicitly chose a custom export directory
            if is_custom:
                project_dir = Path(export_dir)
                chosen_name = base
            # Otherwise check if project already lives in an existing folder containing Transcripts/Media (e.g. Bellevue/)
            elif self.project_file and ((self.project_file.parent / "Transcripts").is_dir() or (self.project_file.parent / "Media").is_dir()):
                project_dir, trans_dir, media_dir, chosen_name = self.prepare_export_directories()
            else:
                parent_dir = QFileDialog.getExistingDirectory(self, "Choose Export Location", self._dialog_directory())
                if not parent_dir:
                    return
                project_dir, trans_dir, media_dir, chosen_name = self.prepare_export_directories(
                    parent_dir, default_name=base, prompt_user=True
                )

            if not project_dir:
                return

            # Keep project session file saved in project folder, NOT in custom export directory
            if not is_custom:
                if self.audio_file or self.transcript:
                    self._write_project_file(str(project_dir / f"{chosen_name}.rtvs"))
            else:
                if self.project_file and (self.audio_file or self.transcript):
                    self._write_project_file(str(self.project_file))

            # Route exports directly to project_dir
            if scope == "full":
                self.export_full_episode(custom_formats=formats, custom_base=chosen_name, custom_options=options, directory=str(project_dir), is_custom_location=is_custom)
            elif scope == "selected_stories":
                self.export_selected_stories(custom_formats=formats, custom_base=chosen_name, custom_options=options, directory=str(project_dir), is_custom_location=is_custom)
            elif scope == "all_stories":
                self.export_all_stories(custom_formats=formats, custom_base=chosen_name, custom_options=options, directory=str(project_dir), is_custom_location=is_custom)
            elif scope == "full_and_all_stories":
                self.export_full_and_all_stories(custom_formats=formats, custom_base=chosen_name, custom_options=options, directory=str(project_dir), is_custom_location=is_custom)
        elif dest == "youtube":
            self._handle_youtube_export_result(result)
        else:
            self._handle_wordpress_export_result(result)

    def cancel_export(self):
        """Flag the running export operation to halt at the next iteration."""
        self.export_cancelled = True
        self.log_activity("[EXPORT] Cancel requested by user.")

    def _export_story_files(self, stories_with_indices, formats, base, options, directory, start_idx=0, total_batch=None, is_custom_location=False):
        out = Path(directory)
        create_bundle = str(self.settings_store.value("create_project_subfolders", "true")).lower() in {"1", "true", "yes"}
        if create_bundle and not is_custom_location:
            transcripts_out = out / "Transcripts"
            media_out = out / "Media"
            transcripts_out.mkdir(parents=True, exist_ok=True)
            if formats.get("media"):
                media_out.mkdir(parents=True, exist_ok=True)
        else:
            transcripts_out = out
            media_out = out

        languages_to_export = []
        batch_direction = options.get("translation_direction")
        if batch_direction and options.get("include_spanish", False):
            source_code, target_code, target_suffix = self.translation_export_spec(options)
            languages_to_export.append((source_code, ""))
            if self.get_translation_item(source_code, target_code):
                languages_to_export.append((target_code, target_suffix))
        else:
            if options.get("include_english", True):
                languages_to_export.append(("en", ""))
            if options.get("include_spanish", False):
                has_es = self.has_spanish_translation() if hasattr(self, "has_spanish_translation") else (
                    self.translation_is_current(self.translation_key("en", "es")) if hasattr(self, "translation_is_current") else False
                )
                if has_es:
                    languages_to_export.append(("es", "_es"))

        doc_base = base if base else (safe_filename(self.audio_file.stem) if self.audio_file else "Story")
        total_stories = total_batch if total_batch is not None else len(stories_with_indices)

        for i, (idx, story) in enumerate(stories_with_indices):
            if getattr(self, "export_cancelled", False):
                self.log_activity("[EXPORT] Export operation stopped by user.")
                return False

            story_title = story.title.strip() if story.title else f"Story {idx + 1}"
            current_count = start_idx + i + 1
            pct = int(((start_idx + i) / max(1, total_stories)) * 100)
            
            # Update inline top-of-window header indicators
            self.set_processing_stage("Exporting Stories", f"{current_count} of {total_stories}: '{story_title}'")
            self.update_processing_progress(pct, f"Exporting {story_title}...")
            QApplication.processEvents()

            story_slug = safe_filename(story.title) if story.title else f"Story_{idx + 1:02d}"
            story_base = f"{doc_base}_{idx + 1:02d}_{story_slug}" if story.title else f"{doc_base}_{idx + 1:02d}"
            segments = self.transcript_for_range(story.start, story.end)

            for lang_code, suffix in languages_to_export:
                file_base = f"{story_base}{suffix}"
                batch_direction = options.get("translation_direction")
                source_code = self.translation_export_spec(options)[0] if batch_direction else "en"
                if lang_code == source_code:
                    blocks = self.build_story_blocks(segments) if segments else []
                else:
                    batch_direction = options.get("translation_direction")
                    if batch_direction:
                        source_code, target_code, _target_suffix = self.translation_export_spec(options)
                        item = self.get_translation_item(source_code, target_code)
                    else:
                        item = self.get_spanish_translation_item() if hasattr(self, "get_spanish_translation_item") else (
                            self.translations.get("en-es") or self.translations.get("en_es") or {}
                        )
                    trans_segs = item.get("segments", []) if item else []
                    source_segs = self.transcript.get("segments", []) if self.transcript else []
                    curr_spk_blocks = []
                    for s_idx, t_seg in enumerate(trans_segs):
                        source_seg = source_segs[s_idx] if s_idx < len(source_segs) else {}
                        s_start = float(t_seg.get("start", source_seg.get("start", 0.0)))
                        s_end = float(t_seg.get("end", source_seg.get("end", s_start + 1.0)))
                        if s_end <= story.start or s_start >= story.end:
                            continue
                        spk = self.get_effective_speaker_name(s_idx, source_seg) if source_seg else ""
                        curr_spk_blocks.append({
                            "speaker": spk,
                            "text": t_seg.get("text", "").strip(),
                            "start": s_start,
                            "end": s_end,
                            "_source_index": s_idx,
                        })
                    blocks = self.build_story_blocks(curr_spk_blocks) if curr_spk_blocks else []

                # Export TXT
                if formats.get("txt"):
                    txt_file = transcripts_out / f"{file_base}.txt"
                    with open(txt_file, "w", encoding="utf-8") as f:
                        source_name = self.audio_file.name if self.audio_file else "Text-only project"
                        lang_label = " (Spanish)" if lang_code == "es" else (" (English)" if lang_code == "en" else "")
                        f.write(f"{story_title}{lang_label}\n{source_name} ({format_time(story.start, False)} - {format_time(story.end, False)})\n" + "=" * 70 + "\n\n")
                        last_speaker = None
                        for block in blocks:
                            speaker = (block.get("speaker") or "").strip() if options.get("include_speakers", True) else ""
                            p_text = block.get("text", "").strip()
                            if not p_text:
                                continue
                            prefix = ""
                            if options.get("include_timestamps") and block.get("start") is not None:
                                prefix = f"[{format_time(block['start'], False)}] "
                            is_speaker_change = block.get("is_speaker_change", (speaker != last_speaker))
                            if speaker and is_speaker_change and speaker != last_speaker:
                                prefix += f"{speaker}: "
                                last_speaker = speaker
                            f.write(f"{prefix}{p_text}\n")

                            if options.get("include_comments", options.get("include_notes", True)):
                                src_idx = block.get("_source_index")
                                source_segs = self.transcript.get("segments", []) if self.transcript else []
                                seg_comment = ""
                                if src_idx is not None and 0 <= src_idx < len(source_segs):
                                    seg_comment = (source_segs[src_idx].get("comments") or source_segs[src_idx].get("notes", "")).strip()
                                elif "comments" in block or "notes" in block:
                                    seg_comment = str(block.get("comments") or block.get("notes", "")).strip()
                                if seg_comment:
                                    f.write(f"   [Comment: {seg_comment}]\n")
                            f.write("\n")

                # Export DOCX
                if formats.get("docx"):
                    docx_file = transcripts_out / f"{file_base}.docx"
                    create_story_docx(
                        title=story_title,
                        blocks=blocks,
                        output_path=docx_file,
                        media_name=self.audio_file.name if self.audio_file else "",
                        start_time=story.start,
                        end_time=story.end,
                        include_speakers=options.get("include_speakers", True),
                        include_timestamps=options.get("include_timestamps", True),
                        include_comments=options.get("include_comments", options.get("include_notes", True)),
                        lang_code=lang_code,
                        source_segments=self.transcript.get("segments", []) if self.transcript else None,
                    )

                # Export PDF
                if formats.get("pdf"):
                    pdf_file = transcripts_out / f"{file_base}.pdf"
                    lang_label = " (Spanish)" if lang_code == "es" else (" (English)" if lang_code == "en" else "")
                    header_title = f"{story_title}{lang_label}"
                    rec_info = f"Recording: {self.audio_file.name} ({format_time(story.start, False)} - {format_time(story.end, False)})" if self.audio_file else None
                    pdf_writer = TranscriptPdfWriter(doc_title=header_title)
                    pdf_writer.add_header(header_title, rec_info)

                    last_speaker = None
                    for block in blocks:
                        speaker = (block.get("speaker") or "").strip() if options.get("include_speakers", True) else ""
                        p_text = block.get("text", "").strip()
                        if not p_text:
                            continue
                        t_stamp = ""
                        if options.get("include_timestamps") and "start" in block and block["start"] is not None:
                            t_stamp = f"[{format_time(block['start'], False)}]"
                        is_speaker_change = block.get("is_speaker_change", (speaker != last_speaker))
                        effective_speaker = speaker if (speaker and is_speaker_change and speaker != last_speaker) else ""
                        if effective_speaker:
                            last_speaker = speaker

                        seg_comment = ""
                        if options.get("include_comments", options.get("include_notes", True)):
                            src_idx = block.get("_source_index")
                            source_segs = self.transcript.get("segments", []) if self.transcript else []
                            if src_idx is not None and 0 <= src_idx < len(source_segs):
                                seg_comment = (source_segs[src_idx].get("comments") or source_segs[src_idx].get("notes", "")).strip()
                            elif "comments" in block or "notes" in block:
                                seg_comment = str(block.get("comments") or block.get("notes", "")).strip()

                        pdf_writer.add_paragraph(
                            text=p_text,
                            speaker=effective_speaker,
                            timestamp=t_stamp,
                            comment=seg_comment,
                        )
                    with open(pdf_file, "wb") as pf:
                        pf.write(pdf_writer.get_pdf_bytes())

                # Export Subtitles
                if formats.get("srt"):
                    self.write_subtitles(blocks, transcripts_out / f"{file_base}.srt", "srt", options.get("include_speakers", True))
                if formats.get("vtt"):
                    self.write_subtitles(blocks, transcripts_out / f"{file_base}.vtt", "vtt", options.get("include_speakers", True))

            # Export Media Clip
            if formats.get("media") and self.audio_file:
                media_file = media_out / f"{story_base}{self.audio_file.suffix.lower()}"
                self.extract_media(story.start, story.end, media_file)

        # Export CUE sheet and tracklist if requested
        if formats.get("cue") and stories_with_indices:
            stories_subset = [s for _, s in stories_with_indices]
            cue_file = transcripts_out / f"{base}.cue"
            album_title = base
            media_name = self.audio_file.name if self.audio_file else ""
            cue_text = generate_cue_sheet(stories_subset, media_name, album_title)
            with open(cue_file, "w", encoding="utf-8") as f:
                f.write(cue_text)

        if formats.get("tracklist") and stories_with_indices:
            stories_subset = [s for _, s in stories_with_indices]
            chapters_file = transcripts_out / f"{base}_chapters.txt"
            chapters_text = generate_youtube_chapters(stories_subset)
            with open(chapters_file, "w", encoding="utf-8") as f:
                f.write(chapters_text)

        return True

    def export_selected_stories(self, custom_formats=None, custom_base=None, custom_options=None, directory=None, is_custom_location=False):
        indices = getattr(self, "current_selected_story_indices", [])
        is_music = getattr(self, "story_detection_mode", "voice") == "music"
        term = "Song" if is_music else "Story"
        term_plural = "Songs" if is_music else "Stories"
        if not indices:
            QMessageBox.warning(self, f"No {term} Selected", f"Please select one or more {term_plural.lower()} to export.")
            return
        stories_to_export = [(i, self.stories[i]) for i in indices if 0 <= i < len(self.stories)]
        if not stories_to_export:
            QMessageBox.warning(self, f"No {term} Selected", f"No valid {term_plural.lower()} are currently selected.")
            return

        base = custom_base or (safe_filename(self.project_file.stem if self.project_file else (self.audio_file.stem if self.audio_file else "export")))
        if directory is None:
            if self.project_file and ((self.project_file.parent / "Transcripts").is_dir() or (self.project_file.parent / "Media").is_dir()):
                project_dir, _, _, chosen_base = self.prepare_export_directories()
            else:
                parent_dir = QFileDialog.getExistingDirectory(self, "Choose Export Location", self._dialog_directory())
                if not parent_dir:
                    return
                project_dir, _, _, chosen_base = self.prepare_export_directories(parent_dir, default_name=base, prompt_user=True)
            if not project_dir:
                return
            directory = str(project_dir)
            base = chosen_base

        formats = custom_formats or {"txt": True, "docx": True, "pdf": True, "srt": False, "vtt": False, "media": False}
        options = custom_options or {"include_speakers": True, "include_timestamps": False, "include_english": True, "include_spanish": False}

        self.export_cancelled = False
        if hasattr(self, "cancel_button"):
            self.cancel_button.show()

        try:
            success = self._export_story_files(stories_to_export, formats, base, options, directory, is_custom_location=is_custom_location)
            if success and not self.export_cancelled:
                self.update_processing_progress(100, "Export complete.")
                self.log_activity(f"[EXPORT] Exported {len(stories_to_export)} selected {term.lower()}(s) to {directory}")
                show_export_completion_dialog(self, "Export Complete", f"Exported {len(stories_to_export)} {term.lower()}(s) to:\n{directory}", directory)
        except Exception as exc:
            self.log_activity(f"[ERROR] Selected stories export failed: {exc}")
            QMessageBox.critical(self, "Export Error", str(exc))
        finally:
            self.set_processing_stage(None)
            if hasattr(self, "cancel_button"):
                self.cancel_button.hide()

    def export_all_stories(self, custom_formats=None, custom_base=None, custom_options=None, directory=None, is_custom_location=False):
        is_music = getattr(self, "story_detection_mode", "voice") == "music"
        term = "Song" if is_music else "Story"
        term_plural = "Songs" if is_music else "Stories"
        if not getattr(self, "stories", []):
            QMessageBox.warning(self, f"No {term_plural}", f"There are no {term_plural.lower()} in this project to export.")
            return

        base = custom_base or (safe_filename(self.project_file.stem if self.project_file else (self.audio_file.stem if self.audio_file else "export")))
        if directory is None:
            if self.project_file and ((self.project_file.parent / "Transcripts").is_dir() or (self.project_file.parent / "Media").is_dir()):
                project_dir, _, _, chosen_base = self.prepare_export_directories()
            else:
                parent_dir = QFileDialog.getExistingDirectory(self, "Choose Export Location", self._dialog_directory())
                if not parent_dir:
                    return
                project_dir, _, _, chosen_base = self.prepare_export_directories(parent_dir, default_name=base, prompt_user=True)
            if not project_dir:
                return
            directory = str(project_dir)
            base = chosen_base

        formats = custom_formats or {"txt": True, "docx": True, "pdf": True, "srt": False, "vtt": False, "media": False}
        options = custom_options or {"include_speakers": True, "include_timestamps": False, "include_english": True, "include_spanish": False}

        stories_to_export = list(enumerate(self.stories))
        self.export_cancelled = False
        if hasattr(self, "cancel_button"):
            self.cancel_button.show()

        try:
            success = self._export_story_files(stories_to_export, formats, base, options, directory, is_custom_location=is_custom_location)
            if success and not self.export_cancelled:
                self.update_processing_progress(100, "Export complete.")
                self.log_activity(f"[EXPORT] Exported all {len(stories_to_export)} {term_plural.lower()} to {directory}")
                show_export_completion_dialog(self, "Export Complete", f"Exported all {len(stories_to_export)} {term_plural.lower()} to:\n{directory}", directory)
        except Exception as exc:
            self.log_activity(f"[ERROR] All stories export failed: {exc}")
            QMessageBox.critical(self, "Export Error", str(exc))
        finally:
            self.set_processing_stage(None)
            if hasattr(self, "cancel_button"):
                self.cancel_button.hide()

    def export_full_and_all_stories(self, custom_formats=None, custom_base=None, custom_options=None, directory=None, is_custom_location=False):
        base = custom_base or (safe_filename(self.project_file.stem if self.project_file else (self.audio_file.stem if self.audio_file else "export")))
        if directory is None:
            if self.project_file and ((self.project_file.parent / "Transcripts").is_dir() or (self.project_file.parent / "Media").is_dir()):
                project_dir, _, _, chosen_base = self.prepare_export_directories()
            else:
                parent_dir = QFileDialog.getExistingDirectory(self, "Choose Export Location", self._dialog_directory())
                if not parent_dir:
                    return
                project_dir, _, _, chosen_base = self.prepare_export_directories(parent_dir, default_name=base, prompt_user=True)
            if not project_dir:
                return
            directory = str(project_dir)
            base = chosen_base

        formats = custom_formats or {"txt": True, "docx": True, "pdf": True, "srt": False, "vtt": False, "media": False}
        options = custom_options or {"include_speakers": True, "include_timestamps": False, "include_english": True, "include_spanish": False}
        stories_to_export = list(enumerate(self.stories)) if getattr(self, "stories", []) else []
        total_items = 1 + len(stories_to_export)

        self.export_cancelled = False
        if hasattr(self, "cancel_button"):
            self.cancel_button.show()

        is_music = getattr(self, "story_detection_mode", "voice") == "music"
        term_plural = "Songs" if is_music else "Stories"

        try:
            self.set_processing_stage(f"Exporting Full & {term_plural}", f"1 of {total_items}: Full Episode")
            self.update_processing_progress(0, "Exporting full episode...")
            QApplication.processEvents()

            ok = self.export_full_episode(
                custom_formats=formats,
                custom_base=base,
                custom_options=options,
                directory=directory,
                show_completion=False,
                is_custom_location=is_custom_location,
            )

            if ok and not self.export_cancelled and stories_to_export:
                self._export_story_files(
                    stories_to_export,
                    formats,
                    base,
                    options,
                    directory,
                    start_idx=1,
                    total_batch=total_items,
                    is_custom_location=is_custom_location,
                )

            if not self.export_cancelled:
                self.update_processing_progress(100, "Export complete.")
                self.log_activity(f"[EXPORT] Exported full episode and all {term_plural.lower()} to {directory}")
                show_export_completion_dialog(self, "Export Complete", f"Exported full episode and {term_plural.lower()} to:\n{directory}", directory)
        except Exception as exc:
            self.log_activity(f"[ERROR] Full & story export failed: {exc}")
            QMessageBox.critical(self, "Export Error", str(exc))
        finally:
            self.set_processing_stage(None)
            if hasattr(self, "cancel_button"):
                self.cancel_button.hide()

    def _handle_wordpress_export_result(self, result):
        client = getattr(self, "_get_wp_client", lambda: None)()
        if not client:
            return
        wp_posts = result.get("wp_posts", [])
        if not wp_posts:
            QMessageBox.warning(self, "No Posts", "No posts were configured for export.")
            return

        inc_en = result.get("include_english", True)
        inc_es = result.get("include_spanish", False)
        pres = result.get("spanish_presentation", "accordion")
        primary = result.get("primary_language", "en")
        total_posts = len(wp_posts)

        self.export_cancelled = False
        if hasattr(self, "cancel_button"):
            self.cancel_button.show()

        created_posts = []
        failed_posts = []

        try:
            for idx, post in enumerate(wp_posts):
                if getattr(self, "export_cancelled", False):
                    self.log_activity("[WORDPRESS] Export canceled by user.")
                    break

                post_title = post.get("title") or "Untitled Post"
                task_label = post.get("task_label") or post_title
                media_name = safe_filename(post_title) if post_title else "audio"
                media_filename = f"{media_name}.mp3"

                pct = int((idx / max(1, total_posts)) * 100)
                self.set_processing_stage("WordPress Publishing", f"Post {idx + 1} of {total_posts}: '{post_title}'")
                self.update_processing_progress(pct, f"Starting WordPress export for '{post_title}'…")
                QApplication.processEvents()

                def wp_progress(step, step_total, description, _idx=idx, _title=post_title):
                    # Four user-visible steps per post: prepare/convert, upload,
                    # prepare post, and create draft. Keep the overall progress
                    # bar moving across all posts rather than resetting per post.
                    fraction = max(0.0, min(1.0, ((step - 1) / step_total)))
                    overall = ((_idx + fraction) / max(1, total_posts)) * 100
                    self.current_processing_stage_detail = f"Post {_idx + 1} of {total_posts}: Step {step} of {step_total} — {description}"
                    self.update_processing_progress(int(overall), description)
                    QApplication.processEvents()

                try:
                    post_data = self._execute_wordpress_upload(
                        client=client,
                        post_title=post_title,
                        post_excerpt=post.get("excerpt", ""),
                        start=post.get("start"),
                        end=post.get("end"),
                        task_label=task_label,
                        include_english=inc_en,
                        include_spanish=inc_es,
                        spanish_presentation=pres,
                        primary_language=primary,
                        author_ids=post.get("author_ids", []),
                        author_term_ids=post.get("author_term_ids", []),
                        category_ids=post.get("category_ids", []),
                        show_completion_dialog=False,
                        media_filename=media_filename,
                        featured_image_path=post.get("featured_image"),
                        progress_callback=wp_progress,
                    )
                    if post_data and isinstance(post_data, dict):
                        self.current_processing_stage_detail = f"Post {idx + 1} of {total_posts}: Step 4 of 4 — Export complete"
                        self.update_processing_progress(int(((idx + 1) / max(1, total_posts)) * 100), f"Finished '{post_title}'.")
                        QApplication.processEvents()
                        post_id = post_data.get("id", "Draft")
                        post_link = post_data.get("link") or f"{client.site_url}/?p={post_id}"
                        created_posts.append({
                            "title": post_title,
                            "id": post_id,
                            "link": post_link,
                        })
                except Exception as exc:
                    self.log_activity(f"[WORDPRESS ERROR] Failed to export '{post_title}': {exc}")
                    failed_posts.append({
                        "title": post_title,
                        "error": str(exc),
                    })
        finally:
            self.set_processing_stage(None)
            if hasattr(self, "cancel_button"):
                self.cancel_button.hide()

        # Final summaries
        if created_posts and not failed_posts:
            if len(created_posts) == 1:
                p = created_posts[0]
                QMessageBox.information(
                    self,
                    "WordPress Export Complete",
                    f"Draft post created successfully on {client.site_url}!\n\n"
                    f"Post Title: {p['title']}\n"
                    f"Post ID: {p['id']}\n"
                    f"Status: Draft\n"
                    f"Preview Link: {p['link']}",
                )
            else:
                posts_summary = "\n".join([f"  #{p['id']}: {p['title']}" for p in created_posts])
                QMessageBox.information(
                    self,
                    "WordPress Export Complete",
                    f"All {len(created_posts)} stories have been posted successfully as drafts to {client.site_url}!\n\n"
                    f"Created Posts:\n{posts_summary}",
                )
        elif created_posts and failed_posts:
            success_summary = "\n".join([f"  #{p['id']}: {p['title']}" for p in created_posts])
            fail_summary = "\n".join([f"  {f['title']}: {f['error']}" for f in failed_posts])
            QMessageBox.warning(
                self,
                "WordPress Export Finished with Errors",
                f"Completed {len(created_posts)} of {total_posts} draft posts.\n\n"
                f"Created Posts:\n{success_summary}\n\n"
                f"Failed Posts:\n{fail_summary}",
            )
        elif failed_posts:
            fail_summary = "\n".join([f"  {f['title']}: {f['error']}" for f in failed_posts])
            QMessageBox.critical(
                self,
                "WordPress Export Failed",
                f"None of the {len(failed_posts)} posts could be exported to WordPress.\n\n"
                f"Errors:\n{fail_summary}",
            )

    def _handle_youtube_export_result(self, result: dict):
        scope = result.get("scope", "full")
        title = result.get("title", "Broadcast Video").strip()
        description = result.get("description", "").strip()
        tags = result.get("tags", "").strip()
        category = result.get("category", "25")
        privacy = result.get("privacy", "unlisted")
        thumb_mode = result.get("thumb_mode", "auto")
        thumb_file = result.get("thumb_file")
        copy_clipboard = result.get("copy_clipboard", True)
        open_browser = result.get("open_browser", True)
        open_folder = result.get("open_folder", True)
        include_subtitles = result.get("include_subtitles", True)

        # 1. Determine export directory (creating a dedicated YouTube subfolder in project directory)
        export_dir = result.get("export_dir")
        create_bundle = str(self.settings_store.value("create_project_subfolders", "true")).lower() in {"1", "true", "yes"}

        if export_dir and os.path.isdir(export_dir):
            base_dir = Path(export_dir)
            if create_bundle and base_dir.name.lower() != "youtube":
                out_dir = base_dir / "YouTube"
            else:
                out_dir = base_dir
        else:
            project_dir, _, _, _ = self.prepare_export_directories(prompt_user=False)
            if create_bundle and project_dir.name.lower() != "youtube":
                out_dir = project_dir / "YouTube"
            else:
                out_dir = project_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        base_name = safe_filename(title) or "youtube_export"

        # 2. Export Media Clip
        media_src = getattr(self, "audio_file", None)
        exported_media_path = None
        if media_src and Path(media_src).exists():
            src_path = Path(media_src)
            ext = src_path.suffix.lower() or ".mp4"
            dst_media = out_dir / f"{base_name}{ext}"

            # If exporting selected stories, cut media clip with ffmpeg
            if scope == "selected_stories":
                sel_indices = getattr(self, "current_selected_story_indices", [])
                stories = getattr(self, "stories", [])
                target_stories = [stories[i] for i in sel_indices if 0 <= i < len(stories)]
                if target_stories:
                    start_sec = min(getattr(st, "start", 0.0) for st in target_stories)
                    end_sec = max(getattr(st, "end", getattr(st, "start", 0.0) + 1.0) for st in target_stories)
                    dur = max(0.1, end_sec - start_sec)
                    ff = ffmpeg_path() or "ffmpeg"
                    cmd = [
                        ff, "-hide_banner", "-loglevel", "error", "-y",
                        "-ss", f"{start_sec:.3f}",
                        "-i", str(src_path),
                        "-t", f"{dur:.3f}",
                        "-c", "copy",
                        str(dst_media)
                    ]
                    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                    try:
                        subprocess.run(cmd, capture_output=True, timeout=120, creationflags=flags)
                    except Exception:
                        shutil.copy2(str(src_path), str(dst_media))
                else:
                    shutil.copy2(str(src_path), str(dst_media))
            else:
                try:
                    if not dst_media.exists() or dst_media.resolve() != src_path.resolve():
                        shutil.copy2(str(src_path), str(dst_media))
                except Exception:
                    pass
            exported_media_path = str(dst_media)

        # 3. Export Thumbnail
        exported_thumb_path = None
        if thumb_mode in ("frame", "file") and thumb_file and Path(thumb_file).exists():
            thumb_ext = Path(thumb_file).suffix.lower() or ".jpg"
            dst_thumb = out_dir / f"{base_name}_thumbnail{thumb_ext}"
            try:
                shutil.copy2(thumb_file, str(dst_thumb))
                exported_thumb_path = str(dst_thumb)
            except Exception as e:
                print(f"[YOUTUBE EXPORT] Thumbnail copy error: {e}")

        # 4. Export Subtitles / Captions (.srt)
        exported_srt_path = None
        if include_subtitles and getattr(self, "transcript", None):
            dst_srt = out_dir / f"{base_name}.srt"
            try:
                segs = self.transcript.get("segments", [])
                if scope == "selected_stories":
                    sel_indices = getattr(self, "current_selected_story_indices", [])
                    stories = getattr(self, "stories", [])
                    target_stories = [stories[i] for i in sel_indices if 0 <= i < len(stories)]
                    if target_stories:
                        start_sec = min(getattr(st, "start", 0.0) for st in target_stories)
                        end_sec = max(getattr(st, "end", getattr(st, "start", 0.0) + 1.0) for st in target_stories)
                        segs = [s for s in segs if s.get("start", 0.0) >= start_sec and s.get("end", 0.0) <= end_sec]

                srt_lines = []
                def srt_ts(sec):
                    h = int(sec // 3600)
                    m = int((sec % 3600) // 60)
                    s = int(sec % 60)
                    ms = int(round((sec - int(sec)) * 1000))
                    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

                for i, seg in enumerate(segs, 1):
                    s_t = max(0.0, float(seg.get("start", 0.0)))
                    e_t = max(s_t, float(seg.get("end", 0.0)))
                    text = seg.get("text", "").strip()
                    if not text:
                        continue
                    srt_lines.append(f"{i}\n{srt_ts(s_t)} --> {srt_ts(e_t)}\n{text}\n")
                if srt_lines:
                    dst_srt.write_text("\n".join(srt_lines), encoding="utf-8")
                    exported_srt_path = str(dst_srt)
            except Exception as e:
                print(f"[YOUTUBE EXPORT] SRT export error: {e}")

        # 5. Export YouTube Upload Info Text File
        info_file = out_dir / f"{base_name}_youtube_info.txt"
        info_content = [
            "=" * 78,
            "YOUTUBE STUDIO UPLOAD GUIDE & METADATA",
            "=" * 78,
            "",
            f"VIDEO TITLE:\n{title}",
            "",
            f"DESCRIPTION & CHAPTER TIMESTAMPS:\n{description}",
            "",
            f"TAGS:\n{tags}",
            "",
            f"PRIVACY STATUS: {privacy.capitalize()}",
            f"CATEGORY ID: {category}",
            "",
            "EXPORTED ASSETS:",
            f"- Video File: {Path(exported_media_path).name if exported_media_path else 'None'}",
            f"- Thumbnail: {Path(exported_thumb_path).name if exported_thumb_path else 'Auto / None'}",
            f"- Closed Captions: {Path(exported_srt_path).name if exported_srt_path else 'None'}",
            "",
            "-" * 78,
            "HOW TO UPLOAD TO YOUTUBE STUDIO:",
            "-" * 78,
            "1. Open https://studio.youtube.com in your web browser.",
            "2. In YouTube Studio, click CREATE (top right) -> Upload videos.",
            "3. Drag and drop your video file into the upload window.",
            "4. Paste (Ctrl+V / Cmd+V) the Description above into the Description box.",
            "   (The chapter timestamps will automatically turn into interactive video chapters!)",
            "5. Under 'Thumbnail', click 'Upload thumbnail' and select your thumbnail file.",
            "6. Under 'Show More' -> 'Tags', paste the tags above.",
            "7. In the 'Video elements' tab, upload your .srt subtitle file if desired.",
            "8. Set your visibility (Unlisted or Public) and click Publish.",
            "=" * 78,
        ]
        info_file.write_text("\n".join(info_content), encoding="utf-8")

        # 6. Copy to clipboard
        clipboard_text = f"{title}\n\n{description}"
        if copy_clipboard:
            QApplication.clipboard().setText(clipboard_text)

        # 7. Open browser
        if open_browser:
            try:
                webbrowser.open("https://studio.youtube.com/channel/UC/videos/upload?d=ud")
            except Exception:
                pass

        # 8. Open folder
        if open_folder and out_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out_dir)))

        # 9. Show Guide Dialog
        files_dict = {
            "Video Media File": exported_media_path,
            "Custom Thumbnail": exported_thumb_path,
            "Subtitles (.srt)": exported_srt_path,
            "YouTube Info Notes": str(info_file),
        }
        guide = YouTubeAssistedUploadGuideDialog(
            self,
            title=title,
            description=description,
            tags=tags,
            files_dict=files_dict,
            privacy=privacy,
        )
        guide.exec()

    def export_full_episode(self, custom_formats=None, custom_base=None, custom_options=None, directory=None, show_completion=True, progress_dialog=None, progress_value=0, is_custom_location=False):
        if not self.transcript and not self.audio_file:
            QMessageBox.warning(self, "Nothing to Export", "There is no transcript or media available to export.")
            return False
        if custom_formats is None or custom_base is None or custom_options is None:
            choice = self._choose_export_formats("Export Full Episode")
            if not choice:
                return False
            formats, base, options = choice
        else:
            formats, base, options = custom_formats, custom_base, custom_options

        if directory is None:
            parent_dir = QFileDialog.getExistingDirectory(self, "Choose Export Location", self._dialog_directory())
            if not parent_dir:
                return False
            project_dir, _, _, chosen_base = self.prepare_export_directories(parent_dir, default_name=base, prompt_user=True)
            if not project_dir:
                return False
            directory = str(project_dir)
            base = chosen_base

        out = Path(directory)
        create_bundle = str(self.settings_store.value("create_project_subfolders", "true")).lower() in {"1", "true", "yes"}
        if create_bundle and not is_custom_location:
            transcripts_out = out / "Transcripts"
            media_out = out / "Media"
            transcripts_out.mkdir(parents=True, exist_ok=True)
            if formats.get("media"):
                media_out.mkdir(parents=True, exist_ok=True)
        else:
            transcripts_out = out
            media_out = out

        created_local_dialog = False
        if progress_dialog is None:
            progress_dialog = QProgressDialog("Preparing export...", "Cancel", 0, 1, self)
            progress_dialog.setWindowTitle("Exporting Files")
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            progress_dialog.setMinimumDuration(0)
            progress_dialog.setValue(0)
            progress_dialog.show()
            QApplication.processEvents()
            created_local_dialog = True

        try:
            languages_to_export = []
            batch_direction = options.get("translation_direction")
            if batch_direction and options.get("include_spanish", False):
                source_code, target_code, target_suffix = self.translation_export_spec(options)
                languages_to_export.append((source_code, ""))
                if self.get_translation_item(source_code, target_code):
                    languages_to_export.append((target_code, target_suffix))
            else:
                if options.get("include_english", True):
                    languages_to_export.append(("en", ""))
                if options.get("include_spanish", False):
                    has_es = self.has_spanish_translation() if hasattr(self, "has_spanish_translation") else (
                        self.translation_is_current(self.translation_key("en", "es")) if hasattr(self, "translation_is_current") else False
                    )
                    if has_es:
                        languages_to_export.append(("es", "_es"))

            doc_title = base if base else (safe_filename(self.audio_file.stem) if self.audio_file else "Transcript")

            if progress_dialog is not None:
                if progress_dialog.wasCanceled():
                    self.log_activity("[EXPORT] Export canceled by user.")
                    return False
                progress_dialog.setLabelText(f"Exporting Full Episode: '{doc_title}'...")
                progress_dialog.setValue(progress_value)
                QApplication.processEvents()

            for lang_code, suffix in languages_to_export:
                file_base = f"{base}{suffix}"

                batch_direction = options.get("translation_direction")
                source_code = self.translation_export_spec(options)[0] if batch_direction else "en"
                if lang_code == source_code:
                    segments = self.transcript.get("segments", []) if self.transcript else []
                    blocks = self.build_story_blocks(segments) if segments else []
                else:
                    batch_direction = options.get("translation_direction")
                    if batch_direction:
                        source_code, target_code, _target_suffix = self.translation_export_spec(options)
                        item = self.get_translation_item(source_code, target_code)
                    else:
                        item = self.get_spanish_translation_item() if hasattr(self, "get_spanish_translation_item") else (
                            self.translations.get("en-es") or self.translations.get("en_es") or {}
                        )
                    trans_segs = item.get("segments", []) if item else []
                    source_segs = self.transcript.get("segments", []) if self.transcript else []
                    curr_spk_blocks = []
                    for idx, t_seg in enumerate(trans_segs):
                        source_seg = source_segs[idx] if idx < len(source_segs) else {}
                        t_start = float(t_seg.get("start", source_seg.get("start", 0.0)))
                        t_end = float(t_seg.get("end", source_seg.get("end", t_start + 1.0)))
                        spk = self.get_effective_speaker_name(idx, source_seg) if source_seg else ""
                        curr_spk_blocks.append({
                            "speaker": spk,
                            "text": t_seg.get("text", "").strip(),
                            "start": t_start,
                            "end": t_end,
                            "_source_index": idx,
                        })
                    blocks = self.build_story_blocks(curr_spk_blocks) if curr_spk_blocks else []

                # Export TXT to Transcripts subfolder
                if formats.get("txt"):
                    txt_file = transcripts_out / f"{file_base}.txt"
                    with open(txt_file, "w", encoding="utf-8") as f:
                        source_name = self.audio_file.name if self.audio_file else "Text-only project"
                        lang_label = " (Spanish)" if lang_code == "es" else (" (English)" if lang_code == "en" else "")
                        f.write(f"{doc_title}{lang_label}\n{source_name}\n" + "=" * 70 + "\n\n")

                        if self.diarization and lang_code == "en":
                            number = self.diarization.get("num_speakers", 0)
                            f.write(f"Speaker detection: {number} speaker(s) detected.\n\n")

                        last_speaker = None
                        for block in blocks:
                            speaker = (block.get("speaker") or "").strip() if options.get("include_speakers", True) else ""
                            paragraph_text = block.get("text", "").strip()
                            if not paragraph_text:
                                continue

                            prefix = ""
                            if options.get("include_timestamps") and block.get("start") is not None:
                                prefix = f"[{format_time(block['start'], False)}] "
                            is_speaker_change = block.get("is_speaker_change", (speaker != last_speaker))
                            if speaker and is_speaker_change and speaker != last_speaker:
                                prefix += f"{speaker}: "
                                last_speaker = speaker

                            f.write(f"{prefix}{paragraph_text}\n")

                            if options.get("include_comments", options.get("include_notes", True)):
                                src_idx = block.get("_source_index")
                                source_segs = self.transcript.get("segments", []) if self.transcript else []
                                seg_comment = ""
                                if src_idx is not None and 0 <= src_idx < len(source_segs):
                                    seg_comment = (source_segs[src_idx].get("comments") or source_segs[src_idx].get("notes", "")).strip()
                                elif "comments" in block or "notes" in block:
                                    seg_comment = str(block.get("comments") or block.get("notes", "")).strip()
                                if seg_comment:
                                    f.write(f"   [Comment: {seg_comment}]\n")
                            f.write("\n")

                # Export DOCX to Transcripts subfolder
                if formats.get("docx"):
                    docx_file = transcripts_out / f"{file_base}.docx"
                    create_story_docx(
                        title=doc_title,
                        blocks=blocks,
                        output_path=docx_file,
                        media_name=self.audio_file.name if self.audio_file else "",
                        start_time=0.0,
                        end_time=0.0,
                        include_speakers=options.get("include_speakers", True),
                        include_timestamps=options.get("include_timestamps", True),
                        include_comments=options.get("include_comments", options.get("include_notes", True)),
                        lang_code=lang_code,
                        source_segments=self.transcript.get("segments", []) if self.transcript else None,
                    )

                # Export PDF to Transcripts subfolder
                if formats.get("pdf"):
                    pdf_file = transcripts_out / f"{file_base}.pdf"
                    lang_label = " (Spanish)" if lang_code == "es" else (" (English)" if lang_code == "en" else "")
                    header_title = f"{doc_title}{lang_label}"
                    rec_info = f"Recording: {self.audio_file.name}" if self.audio_file else None
                    pdf_writer = TranscriptPdfWriter(doc_title=header_title)
                    pdf_writer.add_header(header_title, rec_info)

                    if blocks:
                        last_speaker = None
                        for block in blocks:
                            speaker = (block.get("speaker") or "").strip() if options.get("include_speakers", True) else ""
                            paragraph_text = block.get("text", "").strip()
                            if not paragraph_text:
                                continue

                            t_stamp = ""
                            if options.get("include_timestamps") and "start" in block and block["start"] is not None:
                                t_stamp = f"[{format_time(block['start'], False)}]"

                            is_speaker_change = block.get("is_speaker_change", (speaker != last_speaker))
                            effective_speaker = speaker if (speaker and is_speaker_change and speaker != last_speaker) else ""
                            if effective_speaker:
                                last_speaker = speaker

                            seg_comment = ""
                            if options.get("include_comments", options.get("include_notes", True)):
                                src_idx = block.get("_source_index")
                                source_segs = self.transcript.get("segments", []) if self.transcript else []
                                if src_idx is not None and 0 <= src_idx < len(source_segs):
                                    seg_comment = (source_segs[src_idx].get("comments") or source_segs[src_idx].get("notes", "")).strip()
                                elif "comments" in block or "notes" in block:
                                    seg_comment = str(block.get("comments") or block.get("notes", "")).strip()

                            pdf_writer.add_paragraph(
                                text=paragraph_text,
                                speaker=effective_speaker,
                                timestamp=t_stamp,
                                comment=seg_comment,
                            )
                    with open(pdf_file, "wb") as pf:
                        pf.write(pdf_writer.get_pdf_bytes())

                # Export Subtitles to Transcripts subfolder
                if formats.get("srt"):
                    self.write_subtitles(blocks, transcripts_out / f"{file_base}.srt", "srt", options.get("include_speakers", True))
                if formats.get("vtt"):
                    self.write_subtitles(blocks, transcripts_out / f"{file_base}.vtt", "vtt", options.get("include_speakers", True))

            # Export Media to Media subfolder
            if formats.get("media"):
                if not self.audio_file:
                    raise RuntimeError("Media export is unavailable because this project has no imported media file.")
                media_file = media_out / f"{base}{self.audio_file.suffix.lower()}"
                self.extract_media(0, self.duration, media_file)

            # Export CUE sheet and Tracklist/Chapters if requested
            if formats.get("cue") and getattr(self, "stories", None):
                cue_file = transcripts_out / f"{base}.cue"
                album_title = base
                media_name = self.audio_file.name if self.audio_file else ""
                cue_text = generate_cue_sheet(self.stories, media_name, album_title)
                with open(cue_file, "w", encoding="utf-8") as f:
                    f.write(cue_text)

            if formats.get("tracklist") and getattr(self, "stories", None):
                chapters_file = transcripts_out / f"{base}_chapters.txt"
                chapters_text = generate_youtube_chapters(self.stories)
                with open(chapters_file, "w", encoding="utf-8") as f:
                    f.write(chapters_text)

            if progress_dialog is not None and created_local_dialog:
                progress_dialog.setValue(1)
                QApplication.processEvents()

            self.log_activity(f"[EXPORT] Exported full episode to {out}")
            if show_completion and not (progress_dialog and progress_dialog.wasCanceled()):
                show_export_completion_dialog(self, "Export Complete", f"Exported to:\n{out}", out)
            return True
        except Exception as exc:
            self.log_activity(f"[ERROR] Full episode export failed: {exc}")
            QMessageBox.critical(self, "Export Error", str(exc))
            return False
        finally:
            if created_local_dialog and progress_dialog is not None:
                progress_dialog.close()

    def _choose_export_formats(self, title="Export", allow_media=True):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumWidth(380)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Choose the formats to export."))

        txt = QCheckBox("Text (.txt)")
        docx = QCheckBox("DOCX (.docx)")
        pdf = QCheckBox("PDF document (.pdf)")
        srt = QCheckBox("SubRip subtitles (.srt)")
        vtt = QCheckBox("WebVTT subtitles (.vtt)")
        media = QCheckBox(f"Media ({self.audio_file.suffix.lower() if self.audio_file else 'source format'})")
        media_available = allow_media and self.audio_file is not None

        txt.setChecked(True)
        docx.setChecked(True)
        pdf.setChecked(True)
        media.setChecked(media_available)
        media.setVisible(media_available)

        layout.addWidget(txt)
        layout.addWidget(docx)
        layout.addWidget(pdf)
        layout.addWidget(srt)
        layout.addWidget(vtt)
        if allow_media:
            layout.addWidget(media)

        default = safe_filename(self.project_file.stem if self.project_file else (self.audio_file.stem if self.audio_file else "export"))
        name = QLineEdit(default)
        form = QFormLayout()
        form.addRow("File Name:", name)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        ok = QPushButton("Next")
        cancel = QPushButton("Cancel")
        buttons.addStretch()
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

        cancel.clicked.connect(dialog.reject)
        ok.clicked.connect(dialog.accept)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        formats = {
            "txt": txt.isChecked(),
            "docx": docx.isChecked(),
            "pdf": pdf.isChecked(),
            "srt": srt.isChecked(),
            "vtt": vtt.isChecked(),
            "media": media.isChecked() if allow_media else False,
        }
        if not any(formats.values()):
            QMessageBox.warning(self, "Export", "Select at least one export format.")
            return None

        base = safe_filename(name.text().strip() or default)

        opt_dialog = QDialog(self)
        opt_dialog.setWindowTitle("Transcript Content Options")
        opt_dialog.setMinimumWidth(360)
        opt_layout = QVBoxLayout(opt_dialog)
        opt_layout.addWidget(QLabel("Configure content elements for text exports:"))

        include_speakers_cb = QCheckBox("Include Speaker Labels")
        include_speakers_cb.setChecked(True)

        include_timestamps_cb = QCheckBox("Include Timestamps")
        include_timestamps_cb.setChecked(False)

        opt_layout.addWidget(include_speakers_cb)
        opt_layout.addWidget(include_timestamps_cb)

        opt_layout.addSpacing(6)
        opt_layout.addWidget(QLabel("<b>Language Tracks:</b>"))

        include_english_cb = QCheckBox("Include English Transcript")
        include_english_cb.setChecked(True)

        include_spanish_cb = QCheckBox("Include Spanish Transcript")

        es_key = self.translation_key("en", "es")
        has_spanish = self.translation_is_current(es_key)

        if has_spanish:
            include_spanish_cb.setChecked(True)
            include_spanish_cb.setEnabled(True)
        else:
            include_spanish_cb.setChecked(False)
            include_spanish_cb.setEnabled(False)
            include_spanish_cb.setToolTip("Spanish translation is not available or up to date for this project.")

        opt_layout.addWidget(include_english_cb)
        opt_layout.addWidget(include_spanish_cb)

        opt_buttons = QHBoxLayout()
        opt_ok = QPushButton("Export")
        opt_cancel = QPushButton("Cancel")
        opt_buttons.addStretch()
        opt_buttons.addWidget(opt_ok)
        opt_buttons.addWidget(opt_cancel)
        opt_layout.addLayout(opt_buttons)

        opt_cancel.clicked.connect(opt_dialog.reject)
        opt_ok.clicked.connect(opt_dialog.accept)

        if opt_dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        if (formats["txt"] or formats["docx"]) and not include_english_cb.isChecked() and not include_spanish_cb.isChecked():
            QMessageBox.warning(self, "Export Options", "Please select at least one language track (English or Spanish) to export text content.")
            return None

        options = {
            "include_speakers": include_speakers_cb.isChecked(),
            "include_timestamps": include_timestamps_cb.isChecked(),
            "include_english": include_english_cb.isChecked(),
            "include_spanish": include_spanish_cb.isChecked(),
        }

        return formats, base, options

    def _subtitle_timestamp(self, seconds, vtt=False):
        seconds=max(0.0,float(seconds)); h=int(seconds//3600); m=int((seconds%3600)//60); s=seconds%60
        ms=int(round((s-int(s))*1000)); sec=int(s)
        if ms>=1000: sec+=1; ms=0
        return f"{h:02d}:{m:02d}:{sec:02d}{'.' if vtt else ','}{ms:03d}"

    def write_subtitles(self, blocks, path, fmt="srt", include_speakers=True):
        lines=[]
        if fmt == "vtt": lines.append("WEBVTT\n")
        for i, block in enumerate(blocks,1):
            start=block.get("start",0); end=block.get("end", start+1.0)
            text=self.clean_export_text(block.get("text",""), block.get("speaker",""))
            if include_speakers and block.get("speaker"):
                text=f"{block['speaker']}: {text}"
            if not text: continue
            if fmt == "srt":
                lines.extend([str(i), f"{self._subtitle_timestamp(start)} --> {self._subtitle_timestamp(end)}", text, ""])
            else:
                lines.extend([f"{self._subtitle_timestamp(start, True)} --> {self._subtitle_timestamp(end, True)}", text, ""])
        Path(path).write_text("\n".join(lines), encoding="utf-8")

    def extract_media(self, start, end, output_file):
        """Export a media range using the same container/format as the imported file."""
        if not self.audio_file:
            raise RuntimeError("No source media is loaded.")
        output_file = Path(output_file)
        duration = max(0.0, float(end) - float(start))
        if duration <= 0:
            raise RuntimeError("The selected media range is empty.")

        ext = output_file.suffix.lower()
        copy_cmd = [ffmpeg_path() or "ffmpeg", "-y", "-ss", str(start), "-i", str(self.audio_file), "-t", str(duration), "-map", "0", "-c", "copy", str(output_file)]
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        result = subprocess.run(copy_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600, creationflags=creationflags)
        if result.returncode == 0:
            return

        codec_args = {
            ".wav": ["-c:a", "pcm_s16le"],
            ".mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
            ".flac": ["-c:a", "flac"],
            ".m4a": ["-c:a", "aac", "-b:a", "192k"],
            ".mp4": ["-c:v", "libx264", "-c:a", "aac", "-b:a", "192k"],
            ".mov": ["-c:v", "libx264", "-c:a", "aac", "-b:a", "192k"],
            ".webm": ["-c:v", "libvpx-vp9", "-c:a", "libopus"],
            ".ogg": ["-c:a", "libvorbis"],
            ".aac": ["-c:a", "aac", "-b:a", "192k"],
        }.get(ext)
        if codec_args is None:
            raise RuntimeError(f"Could not export media in the original format ({ext or 'unknown'}).\n\n{result.stderr}")
        transcode_cmd = [ffmpeg_path() or "ffmpeg", "-y", "-ss", str(start), "-i", str(self.audio_file), "-t", str(duration), "-map", "0"] + codec_args + [str(output_file)]
        result2 = subprocess.run(transcode_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1800, creationflags=creationflags)
        if result2.returncode != 0:
            raise RuntimeError(result2.stderr or result.stderr)

    def extract_audio(self, start, end, output_file):
        # Backward-compatible helper for older project/export code.
        duration=end-start
        command=[ffmpeg_path() or "ffmpeg","-y","-ss",str(start),"-i",str(self.audio_file),"-t",str(duration),"-vn","-codec:a","libmp3lame","-q:a","2",str(output_file)]

        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600,
            creationflags=creationflags,
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr)

    def transcript_for_range(self, start, end):
        if not self.transcript:
            return []

        start_time = float(start) if start is not None else 0.0
        end_time = float(end) if end is not None else float("inf")

        result = []
        for source_index, segment in enumerate(self.transcript.get("segments", [])):
            s_start = float(segment.get("start", 0.0))
            s_end = float(segment.get("end", s_start))
            if s_end <= start_time or s_start >= end_time:
                continue
            copied = dict(segment)
            copied["_source_index"] = source_index
            result.append(copied)

        return result

    def speaker_for_segment(self, segment):
        if not segment:
            return ""
        start = segment.get("start", 0.0) if isinstance(segment, dict) else getattr(segment, "start", 0.0)
        end = segment.get("end", start) if isinstance(segment, dict) else getattr(segment, "end", start)
        return self.speaker_at_time(start, end)

    def clean_export_text(self, text, current_speaker=""):
        text = str(text or "").strip()
        if not text:
            return ""

        candidates = set()
        if current_speaker:
            candidates.add(str(current_speaker).strip())
        for value in self.speaker_names.values():
            if value:
                candidates.add(str(value).strip())
        if self.diarization:
            self._ensure_diar_speaker_index()
            candidates.update(self._diar_speaker_labels)

        candidates = sorted((c for c in candidates if c), key=len, reverse=True)
        if not candidates:
            return text

        # Strip speaker labels matched with any standard punctuation (: - —) or brackets
        changed = True
        while changed:
            changed = False
            for name in candidates:
                pattern = rf"^\s*(?:\[{re.escape(name)}\]|\({re.escape(name)}\)|{re.escape(name)})\s*[:\-\—]?\s*"
                new_text = re.sub(pattern, "", text, count=1, flags=re.IGNORECASE)
                if new_text != text:
                    text = new_text.strip()
                    changed = True
                    break
        return text

    def build_story_blocks(self, segments):
        if not segments:
            return []

        word_tokens = []
        for seg_idx, segment in enumerate(segments):
            start = segment.get("start", 0.0) if isinstance(segment, dict) else getattr(segment, "start", 0.0)
            end = segment.get("end", start) if isinstance(segment, dict) else getattr(segment, "end", start)
            source_idx = segment.get("_source_index", seg_idx)
            spk_name = segment.get("speaker")
            if spk_name is None:
                spk_name = self.get_effective_speaker_name(source_idx, segment)
            spk_name = (spk_name or "").strip()

            words = segment.get("words", [])
            if words:
                for w in words:
                    w_text = w.get("word", "").strip()
                    if not w_text or bool(w.get("deleted", False)):
                        continue
                    word_tokens.append({
                        "word": w_text,
                        "start": w.get("start", start),
                        "end": w.get("end", end),
                        "seg_idx": source_idx,
                        "speaker_name": spk_name,
                    })
            else:
                seg_text = segment.get("text", "").strip()
                cleaned_seg_text = self.clean_export_text(seg_text, spk_name)
                for word in cleaned_seg_text.split():
                    word_tokens.append({
                        "word": word,
                        "start": start,
                        "end": end,
                        "seg_idx": source_idx,
                        "speaker_name": spk_name,
                    })

        if not word_tokens:
            return []

        blocks = []
        curr_para_words = []
        curr_speaker_name = None
        last_rendered_speaker_name = None

        def flush_para():
            nonlocal curr_para_words, curr_speaker_name, last_rendered_speaker_name
            if not curr_para_words:
                return
            p_text = " ".join(t["word"] for t in curr_para_words).strip()
            p_text = self.clean_export_text(p_text, curr_speaker_name)
            if p_text:
                is_change = (curr_speaker_name != last_rendered_speaker_name)
                para_source_indices = []
                for t in curr_para_words:
                    s_idx = t.get("seg_idx")
                    if s_idx is not None and s_idx not in para_source_indices:
                        para_source_indices.append(s_idx)

                # Extract any comments anchored to the source segments
                source_segs = self.transcript.get("segments", []) if (hasattr(self, "transcript") and self.transcript) else []
                para_comments = []
                for s_idx in para_source_indices:
                    if 0 <= s_idx < len(source_segs):
                        c = (source_segs[s_idx].get("comments") or source_segs[s_idx].get("notes", "")).strip()
                        if c and c not in para_comments:
                            para_comments.append(c)

                # Also inspect segments list passed directly to build_story_blocks
                if not para_comments and segments:
                    for s in segments:
                        if isinstance(s, dict):
                            s_idx = s.get("_source_index")
                            if s_idx in para_source_indices or s.get("seg_idx") in para_source_indices:
                                c = (s.get("comments") or s.get("notes", "")).strip()
                                if c and c not in para_comments:
                                    para_comments.append(c)

                block_dict = {
                    "speaker": curr_speaker_name or "",
                    "text": p_text,
                    "start": curr_para_words[0]["start"],
                    "end": curr_para_words[-1]["end"],
                    "is_speaker_change": is_change,
                    "_source_index": para_source_indices[0] if para_source_indices else None,
                    "source_indices": para_source_indices,
                }
                if para_comments:
                    block_dict["comments"] = "\n".join(para_comments)
                    block_dict["notes"] = block_dict["comments"]

                blocks.append(block_dict)
                last_rendered_speaker_name = curr_speaker_name
            curr_para_words = []

        for token in word_tokens:
            spk_name = token["speaker_name"]

            if curr_speaker_name is None:
                curr_speaker_name = spk_name

            # Inherit current speaker over short unassigned gaps
            if not spk_name and curr_speaker_name:
                spk_name = curr_speaker_name

            speaker_changed = (spk_name != curr_speaker_name)
            word_count_exceeded = (len(curr_para_words) >= MIN_WORDS_PER_PARAGRAPH)
            prev_word_ended_sentence = curr_para_words and is_sentence_end(curr_para_words[-1]["word"])

            if curr_para_words and (speaker_changed or (word_count_exceeded and prev_word_ended_sentence)):
                flush_para()
                curr_para_words = [token]
                curr_speaker_name = spk_name
            else:
                curr_para_words.append(token)

        if curr_para_words:
            flush_para()

        return blocks

    def story_text(self, segments):
        blocks = self.build_story_blocks(segments)
        output = []
        last_speaker = None
        for block in blocks:
            speaker = (block.get("speaker") or "").strip()
            paragraph = block.get("text", "").strip()
            if not paragraph:
                continue
            is_speaker_change = block.get("is_speaker_change", (speaker != last_speaker))
            if speaker and is_speaker_change and speaker != last_speaker:
                output.append(f"{speaker}: {paragraph}")
                last_speaker = speaker
            else:
                output.append(paragraph)

        return "\n\n".join(output)

    def add_story_to_docx(self, document, segments):
        blocks = self.build_story_blocks(segments)
        last_speaker = None
        for block in blocks:
            speaker = (block.get("speaker") or "").strip()
            paragraph = block.get("text", "").strip()
            if not paragraph:
                continue
            doc_paragraph = document.add_paragraph()
            is_speaker_change = block.get("is_speaker_change", (speaker != last_speaker))
            if speaker and is_speaker_change and speaker != last_speaker:
                speaker_run = doc_paragraph.add_run(f"{speaker}: ")
                speaker_run.bold = True
                last_speaker = speaker
            doc_paragraph.add_run(paragraph)

    def closeEvent(self, event):
        self.log_activity("[SYSTEM] Application shutdown requested.")
        self.statusBar().showMessage("Shutting down...")

        model_thread = getattr(self, "_model_install_thread", None)
        if model_thread is not None and model_thread.isRunning():
            self.log_activity("[WARNING] A model installation is still running; close was canceled to prevent an interrupted download.", mark_dirty=False)
            QMessageBox.warning(
                self,
                "Model Installation Still Running",
                "A model or AI component is still being installed. Please wait for the installation to finish before closing the application."
            )
            event.ignore()
            return

        try:
            self.cleanup_transcription_process()
        except Exception as exc:
            self.log_activity(f"[WARNING] Transcription cleanup failed: {exc}")

        try:
            if not self.stop_all_processing(timeout_ms=10000):
                self.log_activity("[WARNING] One or more processing workers are still shutting down. Close was canceled to avoid destroying a running QThread.", mark_dirty=False)
                QMessageBox.warning(
                    self,
                    "Processing Still Running",
                    "A local processing task is still shutting down. The application was not closed to prevent data loss or a thread crash.\n\nPlease wait a few seconds and try closing again."
                )
                event.ignore()
                return
        except Exception as exc:
            self.log_activity(f"[WARNING] Processing cleanup failed: {exc}", mark_dirty=False)
            event.ignore()
            return

        try:
            if getattr(self, "player", None):
                self.player.stop()
                self.player.setSource(QUrl())
        except Exception as exc:
            self.log_activity(f"[WARNING] Media player cleanup failed: {exc}")

        # Waveform extraction uses a QThread and an FFmpeg subprocess.
        # Cancel the worker and wait for the thread before allowing Qt to
        # destroy the window, preventing QThread lifetime crashes.
        try:
            if not self.stop_waveform_worker(timeout_ms=10000):
                self.log_activity("[WARNING] Waveform worker is still shutting down. Close was canceled to avoid destroying a running QThread.", mark_dirty=False)
                QMessageBox.warning(
                    self,
                    "Waveform Still Running",
                    "The waveform worker is still shutting down. The application was not closed to prevent a thread crash.\n\nPlease wait a few seconds and try closing again."
                )
                event.ignore()
                return
        except Exception as exc:
            self.log_activity(f"[WARNING] Waveform cleanup encountered an issue: {exc}", mark_dirty=False)

        try:
            for thread in list(getattr(self, "translation_status_threads", [])):
                if thread.isRunning():
                    thread.quit()
                    thread.wait(5000)
            self.translation_status_threads.clear()
        except Exception as exc:
            self.log_activity(f"[WARNING] Translation status cleanup failed: {exc}", mark_dirty=False)

        try:
            if not self.stop_video_thumbnail_worker():
                self.log_activity("[WARNING] Video thumbnail worker is still stopping. Close was canceled to avoid a QThread lifetime crash.", mark_dirty=False)
                event.ignore()
                return
        except Exception:
            pass
        try:
            self.auto_save_timer.stop()
            self.scrub_timer.stop()
        except Exception:
            pass

        checkpoint_thread = getattr(self, "translation_checkpoint_thread", None)
        if checkpoint_thread is not None and checkpoint_thread.is_alive():
            checkpoint_thread.join(timeout=5.0)

        for save_thread in list(getattr(self, "translation_save_threads", [])):
            if save_thread.is_alive():
                save_thread.join(timeout=5.0)

        try:
            warnings.showwarning = self._original_showwarning
            sys.excepthook = self._original_excepthook
        except Exception:
            pass

        try:
            terminate_all_registered_processes()
        except Exception:
            pass

        try:
            cleanup_old_thumbnail_cache(24)
        except Exception:
            pass

        # QSettings writes made during this session (a project just saved,
        # a Preferences change) are not guaranteed to reach disk on their
        # own during interpreter shutdown -- force a flush now, while the
        # app is still fully alive, so the next launch sees them.
        try:
            if getattr(self, "settings_store", None) is not None:
                self.settings_store.sync()
        except Exception as exc:
            self.log_activity(f"[WARNING] Settings sync failed: {exc}", mark_dirty=False)

        self.log_activity("[SYSTEM] Application shutdown cleanup complete.")
        event.accept()

    def export_cue_sheet(self, destination_path=None):
        """Export story/song segments to a standard .cue sheet."""
        is_music = getattr(self, "story_detection_mode", "voice") == "music"
        term_plural = "Songs" if is_music else "Stories"
        if not getattr(self, "stories", []):
            QMessageBox.warning(self, f"No {term_plural}", f"There are no {term_plural.lower()} to export.")
            return False
        base = safe_filename(self.project_file.stem if self.project_file else (self.audio_file.stem if self.audio_file else "project"))
        album_title = self.project_file.stem if self.project_file else (self.audio_file.stem if self.audio_file else "Album")
        if not destination_path:
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Export CUE Sheet",
                str(Path(self._dialog_directory()) / f"{base}.cue"),
                "CUE Sheet (*.cue)"
            )
            if not save_path:
                return False
        else:
            save_path = destination_path

        media_name = self.audio_file.name if getattr(self, "audio_file", None) else ""
        content = generate_cue_sheet(self.stories, media_name, album_title)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(content)
        self.log_activity(f"[EXPORT] Exported CUE sheet to {save_path}")
        if not destination_path:
            show_export_completion_dialog(self, "Export Complete", f"CUE sheet exported successfully to:\n{save_path}", save_path)
        return True

    def export_tracklist(self, destination_path=None):
        """Export story/song segments as YouTube chapters / tracklist formatted text."""
        is_music = getattr(self, "story_detection_mode", "voice") == "music"
        term_plural = "Songs" if is_music else "Stories"
        if not getattr(self, "stories", []):
            QMessageBox.warning(self, f"No {term_plural}", f"There are no {term_plural.lower()} to export.")
            return False
        base = safe_filename(self.project_file.stem if self.project_file else (self.audio_file.stem if self.audio_file else "project"))
        if not destination_path:
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Export Tracklist / Chapters",
                str(Path(self._dialog_directory()) / f"{base}_chapters.txt"),
                "Text File (*.txt)"
            )
            if not save_path:
                return False
        else:
            save_path = destination_path

        content = generate_youtube_chapters(self.stories)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(content)
        self.log_activity(f"[EXPORT] Exported tracklist / chapters to {save_path}")
        if not destination_path:
            show_export_completion_dialog(self, "Export Complete", f"Tracklist / Chapters exported successfully to:\n{save_path}", save_path)
        return True

    def perform_stories_export(
        self,
        target_stories=None,
        custom_formats=None,
        custom_base=None,
        custom_options=None,
        directory=None,
        show_completion=False,
    ):
        stories = target_stories if target_stories is not None else getattr(self, "stories", [])
        if not stories:
            return False
        base = custom_base or (safe_filename(self.project_file.stem if self.project_file else (self.audio_file.stem if self.audio_file else "export")))
        formats = custom_formats or {"txt": True, "docx": True, "pdf": True, "srt": False, "vtt": False, "media": False}
        options = custom_options or {"include_speakers": True, "include_timestamps": False, "include_english": True, "include_spanish": False}
        stories_to_export = list(enumerate(stories))
        success = self._export_story_files(stories_to_export, formats, base, options, directory)
        if show_completion and success:
            show_export_completion_dialog(self, "Export Complete", f"Exported {len(stories_to_export)} stories to {directory}", directory)
        return success

    def _get_transcript_text_slice(self, start: float, end: float | None = None) -> str:
        segments = self.transcript_for_range(start, end)
        parts = []
        for s in segments:
            t = s.get("text", "").strip()
            if t:
                parts.append(t)
        return " ".join(parts)
