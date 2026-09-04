"""Radio & TV Segmenter v1.1.1 — transcript story responsibilities.

Methods intentionally retain the MainWindow-facing API so behavior remains
maintaining the established MainWindow-facing API while responsibilities are isolated.
"""

from prs_shared import *


class TranscriptStoryMixin:
    def render_transcript(self):
        if not self.transcript:
            return

        self.is_updating_transcript_view = True
        display_mode = getattr(self, "translation_display_mode", "en")
        if display_mode == "bilingual":
            display_mode = "split"
        segments = self.transcript.get("segments", [])
        es_item = self.get_spanish_translation_item() if hasattr(self, "get_spanish_translation_item") else None
        es_segments = es_item.get("segments", []) if isinstance(es_item, dict) else []

        active_segments = segments
        if display_mode == "es" and es_segments:
            active_segments = es_segments

        if not active_segments:
            self.transcript_view.setHtml("")
            self.transcript_view.set_char_timestamp_map([])
            self._block_segment_groups = []
            if hasattr(self, "_capture_project_state") and not getattr(self, "is_restoring_undo", False):
                self._transcript_edit_baseline = self._capture_project_state()
            self.is_updating_transcript_view = False
            return

        word_tokens = []
        for seg_idx, segment in enumerate(active_segments):
            start = segment.get("start", 0.0) if isinstance(segment, dict) else getattr(segment, "start", 0.0)
            end = segment.get("end", start) if isinstance(segment, dict) else getattr(segment, "end", start)
            raw_spk = self.segment_speaker_overrides.get(seg_idx) or self.speaker_at_time(start, end)
            orig_segment = segments[seg_idx] if 0 <= seg_idx < len(segments) else segment
            spk_name = self.get_effective_speaker_name(seg_idx, orig_segment)

            words = segment.get("words", [])
            if words and display_mode != "es":
                for w in words:
                    word_tokens.append({
                        "word": w.get("word", ""),
                        "start": w.get("start", start),
                        "end": w.get("end", end),
                        "seg_idx": seg_idx,
                        "speaker_name": spk_name,
                        "raw_speaker": raw_spk,
                    })
            else:
                seg_text = segment.get("text", "")
                for word in seg_text.split():
                    word_tokens.append({
                        "word": word,
                        "start": start,
                        "end": end,
                        "seg_idx": seg_idx,
                        "speaker_name": spk_name,
                        "raw_speaker": raw_spk,
                    })

        if not word_tokens:
            self.transcript_view.setHtml("")
            self.transcript_view.set_char_timestamp_map([])
            self._block_segment_groups = []
            if hasattr(self, "_capture_project_state") and not getattr(self, "is_restoring_undo", False):
                self._transcript_edit_baseline = self._capture_project_state()
            self.is_updating_transcript_view = False
            return

        # Batch document changes using QTextCursor EditBlock to prevent UI freezes
        doc = self.transcript_view.document()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()

        html_parts = []
        char_timestamp_map = []
        current_char_pos = 0
        block_segment_groups = []

        curr_theme = getattr(self.transcript_view, "current_theme", "dark")
        if curr_theme == "light":
            word_color = "#111111"
            speaker_color = "#0056b3"
            time_color = "#555c68"
            spanish_color = "#1a7f37"
            spanish_tag_color = "#57606a"
        elif curr_theme == "high_contrast":
            word_color = "#ffffff"
            speaker_color = "#00ffff"
            time_color = "#ffff00"
            spanish_color = "#00ff00"
            spanish_tag_color = "#ffff00"
        else:
            word_color = "#ffffff"
            speaker_color = "#58a6ff"
            time_color = "#8b949e"
            spanish_color = "#7ee787"
            spanish_tag_color = "#8b949e"

        curr_para_words = []
        curr_speaker_name = None
        curr_raw_speaker = None
        last_rendered_speaker_name = None

        def render_paragraph_block(p_words, p_speaker_name, p_raw_speaker, is_speaker_change):
            nonlocal current_char_pos
            if not p_words:
                return ""

            start_time = p_words[0]["start"]
            first_seg_idx = p_words[0]["seg_idx"]

            time_str = format_time(start_time)

            if p_speaker_name and is_speaker_change and self.show_speaker_labels:
                esc_spk = html.escape(p_speaker_name)
                esc_raw = html.escape(str(p_raw_speaker or ""))
                speaker_html = (
                    f'<a href="speaker:{first_seg_idx}:{esc_raw}" style="color:{speaker_color}; font-weight:bold; text-decoration:none;">'
                    f'{esc_spk}:</a> '
                )
            else:
                speaker_html = ""
            plain_prefix = (f"{time_str} " if self.show_timestamps else "")
            if self.show_speaker_labels and p_speaker_name and is_speaker_change:
                plain_prefix += f"{p_speaker_name}: "

            current_char_pos += len(plain_prefix)

            word_html_list = []
            for item in p_words:
                w_text = item["word"]
                w_start = item["start"]
                w_seg = item["seg_idx"]

                w_len = len(w_text) + 1
                char_timestamp_map.append((current_char_pos, current_char_pos + w_len, w_start, item.get("end", w_start), w_seg))
                current_char_pos += w_len

                esc_w = html.escape(w_text)
                word_html_list.append(
                    f'<a href="word:{w_start}:{w_seg}" style="color:{word_color}; text-decoration:none;">{esc_w}</a>'
                )

            current_char_pos += 2

            body_content = " ".join(word_html_list)

            timestamp_html = (
                f'<a href="time:{start_time}" style="color:{time_color}; text-decoration:none;"><b>{time_str}</b></a> '
                if self.show_timestamps else ""
            )

            if display_mode in ("split", "bilingual") and es_segments:
                seg_indices = list(dict.fromkeys(item["seg_idx"] for item in p_words if "seg_idx" in item))
                es_text_parts = [es_segments[idx].get("text", "") for idx in seg_indices if 0 <= idx < len(es_segments)]
                es_text = " ".join(t.strip() for t in es_text_parts if t.strip())
                if es_text:
                    esc_es_text = html.escape(es_text)
                    return (
                        f'<p style="margin-bottom: 14px;">'
                        f'{timestamp_html}{speaker_html}'
                        f'<span style="color:{word_color};">{body_content}</span><br/>'
                        f'<span style="color:{spanish_tag_color}; font-weight:bold; font-size:12px;">ES: </span>'
                        f'<span style="color:{spanish_color};"><i>{esc_es_text}</i></span>'
                        f'</p>'
                    )

            return (
                f'<p style="margin-bottom: 14px; color: {word_color};">'
                f'{timestamp_html}{speaker_html}'
                f'<span style="color:{word_color};">{body_content}</span>'
                f'</p>'
            )

        def _summarize_paragraph_segments(p_words):
            """Contiguous (seg_idx, word_count) run-length groups for one
            rendered paragraph, used to map edited text in that paragraph
            back to the original segment(s) it was built from."""
            groups = []
            for w in p_words:
                seg_idx = w["seg_idx"]
                if groups and groups[-1][0] == seg_idx:
                    groups[-1] = (seg_idx, groups[-1][1] + 1)
                else:
                    groups.append((seg_idx, 1))
            return groups

        for token in word_tokens:
            spk_name = token["speaker_name"]
            raw_spk = token["raw_speaker"]

            if curr_speaker_name is None:
                curr_speaker_name = spk_name
                curr_raw_speaker = raw_spk

            speaker_changed = (spk_name != curr_speaker_name)
            word_count_exceeded = (len(curr_para_words) >= MIN_WORDS_PER_PARAGRAPH)
            prev_word_ended_sentence = curr_para_words and is_sentence_end(curr_para_words[-1]["word"])

            if curr_para_words and (speaker_changed or (word_count_exceeded and prev_word_ended_sentence)):
                is_change = (curr_speaker_name != last_rendered_speaker_name)
                html_parts.append(render_paragraph_block(curr_para_words, curr_speaker_name, curr_raw_speaker, is_change))
                block_segment_groups.append(_summarize_paragraph_segments(curr_para_words))
                last_rendered_speaker_name = curr_speaker_name

                curr_para_words = [token]
                curr_speaker_name = spk_name
                curr_raw_speaker = raw_spk
            else:
                curr_para_words.append(token)

        if curr_para_words:
            is_change = (curr_speaker_name != last_rendered_speaker_name)
            html_parts.append(render_paragraph_block(curr_para_words, curr_speaker_name, curr_raw_speaker, is_change))
            block_segment_groups.append(_summarize_paragraph_segments(curr_para_words))

        self.transcript_view.setHtml("".join(html_parts))
        cursor.endEditBlock()
        self._block_segment_groups = block_segment_groups

        self.timeline.set_transcript_selection_range(None, None)
        self.transcript_view.rebuild_anchor_index()
        self.transcript_view.set_time_anchor_index(
            [
                (item["start"], item["end"], f"word:{item['start']}:{item['seg_idx']}")
                for item in word_tokens
            ]
        )
        self.transcript_view.set_char_timestamp_map(char_timestamp_map)
        # This is the exact project state represented by the rendered editor.
        # Text edits are grouped from this baseline into one undoable action.
        if hasattr(self, "_capture_project_state") and not getattr(self, "is_restoring_undo", False):
            self._transcript_edit_baseline = self._capture_project_state()
        self.is_updating_transcript_view = False

        if display_mode != "en":
            self.transcript_view.setReadOnly(True)
            if hasattr(self, "transcript_mode_toggle_btn"):
                self.transcript_mode_toggle_btn.setEnabled(False)
                self.transcript_mode_toggle_btn.setToolTip("Editing is disabled while viewing translations. Switch to English (Original) to edit.")
        else:
            if hasattr(self, "transcript_mode_toggle_btn"):
                self.transcript_mode_toggle_btn.setEnabled(True)
                self.transcript_mode_toggle_btn.setToolTip("Toggle between Viewing Mode (click to play/seek audio) and Editing Mode (type/edit transcript text).")
            self.transcript_view.setReadOnly(not getattr(self.transcript_view, "is_editing_mode", False))

    def on_transcript_selection_changed(self):
        if self.is_updating_transcript_view:
            return
        selected_range = self.transcript_view.get_selected_time_range()
        if selected_range:
            self.timeline.set_transcript_selection_range(*selected_range)
            self.statusBar().showMessage(
                f"Transcript selection: {format_time(selected_range[0])} – {format_time(selected_range[1])}"
            )
        else:
            if not getattr(self.transcript_view, "has_active_selection", lambda: False)():
                self.timeline.set_transcript_selection_range(None, None)

    def on_transcript_text_changed(self):
        if self.is_updating_transcript_view or getattr(self, "is_restoring_undo", False) or not self.transcript:
            return
        if getattr(self, "translation_display_mode", "en") != "en":
            return

        # Keep the data model synchronized with the editor. Each rendered
        # paragraph (Qt "block") isn't reliably one segment -- same-speaker
        # segments get merged into one paragraph, and long runs get split by
        # word count rather than segment boundary. self._block_segment_groups
        # (captured at the last render_transcript()) records, per block, the
        # ordered original (seg_idx, word_count) groups it was built from, so
        # an edit lands on the right segment(s) instead of on block index i.
        doc = self.transcript_view.document()
        blocks_count = doc.blockCount()
        segments = self.transcript.get("segments", [])
        block_groups = getattr(self, "_block_segment_groups", None) or []

        known_speaker_labels = None

        for i in range(min(blocks_count, len(block_groups))):
            groups = [g for g in block_groups[i] if 0 <= g[0] < len(segments)]
            if not groups:
                continue

            block_text = doc.findBlockByNumber(i).text()
            cleaned_text = re.sub(r'^\d{2}:\d{2}(?::\d{2})?\.\d{3}\s+', '', block_text)
            # Remove any displayed speaker prefix, including custom names.
            if ": " in cleaned_text:
                prefix, remainder = cleaned_text.split(": ", 1)
                if known_speaker_labels is None:
                    known_speaker_labels = set(self.speaker_names.values())
                    known_speaker_labels.update(
                        self.get_all_known_speakers() if hasattr(self, "get_all_known_speakers") else []
                    )
                if prefix.strip() in {str(x).strip() for x in known_speaker_labels if x}:
                    cleaned_text = remainder
            cleaned_text = re.sub(r'^Speaker \d+:\s+', '', cleaned_text)
            cleaned_text = cleaned_text.strip()

            if len(groups) == 1:
                segments[groups[0][0]]["text"] = cleaned_text
                continue

            # This paragraph was built from more than one original segment
            # (merged same-speaker turns). Redistribute the edited words
            # across those segments in proportion to how many words each
            # originally contributed -- an approximation, but it keeps
            # edits attached to roughly the right segment instead of all
            # landing on whichever segment happens to share the block index.
            words = cleaned_text.split()
            total_original_words = sum(g[1] for g in groups) or 1
            remaining_words = words
            for gi, (seg_idx, orig_count) in enumerate(groups):
                if gi == len(groups) - 1:
                    share, remaining_words = remaining_words, []
                else:
                    n = round(len(words) * (orig_count / total_original_words))
                    n = max(0, min(n, len(remaining_words)))
                    share, remaining_words = remaining_words[:n], remaining_words[n:]
                segments[seg_idx]["text"] = " ".join(share)

        if self.translations:
            for key in self.translations:
                self.translations[key]["status"] = "stale"
            self.log_activity("[TRANSLATION] Source transcript edited; existing translations marked for update.", mark_dirty=False)

        if getattr(self, "_pending_transcript_edit_before", None) is None:
            baseline = getattr(self, "_transcript_edit_baseline", None)
            if baseline is not None:
                self._pending_transcript_edit_before = baseline

        timer = getattr(self, "_transcript_undo_timer", None)
        if timer is not None:
            timer.start()


        self.mark_project_dirty()

    def transcript_clicked(self, url):
        text = url.toString()
        if text.startswith("time:"):
            seconds = float(text.split(":", 1)[1])
            self.seek_to(seconds)
        elif text.startswith("word:"):
            # Viewing-mode left-click is navigation only.  Speaker actions
            # are available from the right-click context menu.
            parts = text.split(":")
            seconds = float(parts[1])
            self.seek_to(seconds)
        elif text.startswith("speaker:"):
            # Do not open speaker-editing UI from a normal left-click.
            # Right-clicking the speaker anchor exposes Change/Remove actions.
            return

    def handle_insert_speaker_request(self, seg_idx, split_time, speaker_name):
        """Dispatched from the right-click 'Add Speaker Label Here' context menu."""
        if speaker_name == "__NEW__":
            self.add_speaker_label_at(seg_idx, split_time, name=None)
        else:
            self.add_speaker_label_at(seg_idx, split_time, name=speaker_name)

    def add_speaker_label_at(self, seg_idx, split_time, name=None):
        """Adds a speaker label break: assigns or splits the segment at split_time."""
        if not self.transcript or "segments" not in self.transcript:
            self.statusBar().showMessage("No transcript available.")
            return False

        segments = self.transcript.get("segments", [])
        if not segments:
            return False

        # If seg_idx is invalid, locate the segment that contains split_time
        if seg_idx is None or seg_idx < 0 or seg_idx >= len(segments):
            for i, seg in enumerate(segments):
                s_start = float(seg.get("start", 0.0))
                s_end = float(seg.get("end", s_start))
                if s_start <= split_time <= s_end:
                    seg_idx = i
                    break
            if seg_idx is None:
                seg_idx = max(0, min(len(segments) - 1, int(seg_idx or 0)))

        if name is None:
            known = self.get_all_known_speakers() if hasattr(self, "get_all_known_speakers") else []
            if known:
                name, accepted = QInputDialog.getItem(
                    self, "Add Speaker Label", "Speaker name for this label:", known, 0, True
                )
            else:
                name, accepted = QInputDialog.getText(self, "Add Speaker Label", "Speaker name for this label:")
            if not accepted:
                return False

        name = (name or "").strip()
        if not name:
            self.statusBar().showMessage("Speaker label needs a name.")
            return False

        target_seg = segments[seg_idx]
        words = target_seg.get("words", [])

        # Check if click is at or before the very first word of the segment
        is_at_segment_start = False
        if words:
            if split_time <= words[0].get("start", target_seg["start"]) + 0.05:
                is_at_segment_start = True
        else:
            if split_time <= float(target_seg.get("start", 0.0)) + 0.1:
                is_at_segment_start = True

        # If click is at start of segment, reassign this segment directly without splitting
        if is_at_segment_start:
            self.flush_pending_transcript_undo() if hasattr(self, "flush_pending_transcript_undo") else None
            before_state = self._capture_project_state() if hasattr(self, "_capture_project_state") else None

            override_key = f"SEG_{seg_idx}_SPEAKER"
            self.speaker_names[override_key] = name
            self.segment_speaker_overrides[seg_idx] = override_key
            self._diar_index_key = None

            if before_state is not None and hasattr(self, "_commit_project_state_change"):
                self._commit_project_state_change(before_state, f"Add Speaker Label ({name})")

            self.add_custom_speaker_to_glossary(name)
            self.log_activity(f"[SPEAKER] Set speaker label '{name}' at segment #{seg_idx + 1}")
            self.save_project()
            self.render_transcript()
            return True

        # Otherwise, split segment at word boundary
        if not self.split_segment_at_time(seg_idx, split_time, new_speaker_name=name):
            # Fallback: if words-based split rejected because split_time was slightly off,
            # assign to the segment directly so the user action always succeeds
            self.flush_pending_transcript_undo() if hasattr(self, "flush_pending_transcript_undo") else None
            before_state = self._capture_project_state() if hasattr(self, "_capture_project_state") else None

            override_key = f"SEG_{seg_idx}_SPEAKER"
            self.speaker_names[override_key] = name
            self.segment_speaker_overrides[seg_idx] = override_key
            self._diar_index_key = None

            if before_state is not None and hasattr(self, "_commit_project_state_change"):
                self._commit_project_state_change(before_state, f"Add Speaker Label ({name})")

            self.add_custom_speaker_to_glossary(name)
            self.log_activity(f"[SPEAKER] Assigned speaker label '{name}' to segment #{seg_idx + 1}")
            self.save_project()
            self.render_transcript()
            return True

        self.add_custom_speaker_to_glossary(name)
        return True

    def split_segment_at_time(self, seg_idx, split_time, new_speaker_name=None):
        """Split a segment at an exact word timestamp."""
        if not self.transcript or "segments" not in self.transcript:
            return False

        segments = self.transcript.get("segments", [])
        if seg_idx < 0 or seg_idx >= len(segments):
            return False

        target_seg = segments[seg_idx]
        words = target_seg.get("words", [])

        if words:
            # Find the best split split index by proximity
            split_idx = -1
            for w_i, w in enumerate(words):
                if w.get("start", target_seg["start"]) >= split_time - 0.01:
                    split_idx = w_i
                    break

            if split_idx <= 0 or split_idx >= len(words):
                return False

            left_words = words[:split_idx]
            right_words = words[split_idx:]

            seg1 = dict(target_seg)
            seg1["end"] = left_words[-1].get("end", split_time)
            seg1["words"] = left_words
            seg1["text"] = " ".join(w.get("word", "") for w in left_words)

            seg2 = dict(target_seg)
            seg2["start"] = right_words[0].get("start", split_time)
            seg2["words"] = right_words
            seg2["text"] = " ".join(w.get("word", "") for w in right_words)
        else:
            seg_text = target_seg.get("text", "").split()
            if len(seg_text) < 2:
                return False

            seg_start = float(target_seg.get("start", split_time))
            seg_end = float(target_seg.get("end", split_time))
            duration = max(0.0, seg_end - seg_start)
            ratio = max(0.0, min(1.0, (float(split_time) - seg_start) / duration)) if duration > 0 else 0.5
            split_word = max(1, min(len(seg_text) - 1, round(len(seg_text) * ratio)))

            seg1 = dict(target_seg)
            seg1["end"] = float(split_time)
            seg1["text"] = " ".join(seg_text[:split_word])

            seg2 = dict(target_seg)
            seg2["start"] = float(split_time)
            seg2["text"] = " ".join(seg_text[split_word:])

        self.flush_pending_transcript_undo() if hasattr(self, "flush_pending_transcript_undo") else None
        before_state = self._capture_project_state() if hasattr(self, "_capture_project_state") else None

        segments[seg_idx] = seg1
        segments.insert(seg_idx + 1, seg2)

        # Shift overrides down
        new_overrides = {}
        for idx_k, spk in self.segment_speaker_overrides.items():
            k = int(idx_k)
            if k <= seg_idx:
                new_overrides[k] = spk
            else:
                new_overrides[k + 1] = spk
        self.segment_speaker_overrides = new_overrides

        if new_speaker_name:
            override_key = f"SEG_{seg_idx + 1}_SPEAKER"
            self.speaker_names[override_key] = str(new_speaker_name).strip()
            self.segment_speaker_overrides[seg_idx + 1] = override_key

        self._diar_index_key = None

        if before_state is not None and hasattr(self, "_commit_project_state_change"):
            self._commit_project_state_change(
                before_state,
                f"Add Speaker Label{' (' + str(new_speaker_name) + ')' if new_speaker_name else ''}"
            )

        self.log_activity(f"[SPEAKER] Added speaker label break at {format_time(split_time)} (Split Segment #{seg_idx + 1})")
        self.save_project()
        self.render_transcript()
        return True

    def prompt_rename_custom_speaker(self, old_name):
        self.flush_pending_transcript_undo() if hasattr(self, "flush_pending_transcript_undo") else None
        before_state = self._capture_project_state() if hasattr(self, "_capture_project_state") else None
        new_name, accepted = QInputDialog.getText(
            self,
            "Rename Speaker",
            f"Enter new name for {old_name}:",
            QLineEdit.EchoMode.Normal,
            old_name,
        )
        if accepted and new_name.strip():
            self.speaker_names[f"CUSTOM_{old_name}"] = new_name.strip()
            self.add_custom_speaker_to_glossary(new_name.strip())
            if before_state is not None and hasattr(self, "_commit_project_state_change"):
                self._commit_project_state_change(before_state, f"Rename Speaker: {old_name} → {new_name.strip()}")
            self.render_transcript()
            self.save_project()
            self.log_activity(f"[SPEAKER] Renamed custom speaker '{old_name}' to '{new_name.strip()}'")

    def display_speaker(self, speaker):
        if speaker is None:
            return ""

        speaker = str(speaker)
        custom_name = self.speaker_names.get(speaker)
        if custom_name:
            return custom_name

        match = re.search(r"(\d+)$", speaker)
        if match:
            number = int(match.group(1)) + 1
            return f"Speaker {number}"

        return speaker

    def get_all_known_speakers(self):
        """Return a sorted list of unique speaker names currently known or used in the project."""
        speakers = set()
        # Custom speaker name overrides
        if hasattr(self, "speaker_names") and self.speaker_names:
            for k, v in self.speaker_names.items():
                if v and isinstance(v, str) and v.strip() and not k.startswith("SEG_"):
                    speakers.add(v.strip())
        # Transcript segment effective speakers
        if getattr(self, "transcript", None) and isinstance(self.transcript, dict) and "segments" in self.transcript:
            for idx, seg in enumerate(self.transcript["segments"]):
                name = self.get_effective_speaker_name(idx, seg)
                if name and name.strip():
                    speakers.add(name.strip())
        # Diarization segments
        diar_data = getattr(self, "diarization_result", None) or getattr(self, "diarization", None)
        if isinstance(diar_data, dict) and "segments" in diar_data:
            for seg in diar_data["segments"]:
                spk = seg.get("speaker")
                if spk:
                    disp = self.display_speaker(spk)
                    if disp and disp.strip():
                        speakers.add(disp.strip())
        # Custom speakers in glossary
        if hasattr(self, "custom_speakers") and self.custom_speakers:
            for spk in self.custom_speakers:
                if spk and isinstance(spk, str) and spk.strip():
                    speakers.add(spk.strip())

        def natural_sort_key(s):
            is_speaker_num = s.startswith("Speaker ") and s[8:].isdigit()
            if is_speaker_num:
                return (0, int(s[8:]), s.lower())
            return (1, 0, [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)])

        return sorted(speakers, key=natural_sort_key)

    def execute_speaker_rename(self, seg_idx, raw_speaker, target_name):
        """Reassign or rename a speaker from the context menu or speaker options."""
        if not self.transcript or "segments" not in self.transcript:
            return
        segments = self.transcript.get("segments", [])
        if seg_idx < 0 or seg_idx >= len(segments):
            return

        current_name = (
            self.get_effective_speaker_name(seg_idx, segments[seg_idx])
            if seg_idx < len(segments)
            else self.display_speaker(raw_speaker)
        )

        if target_name == "__NEW__":
            new_name, accepted = QInputDialog.getText(
                self,
                "New Speaker Name",
                f"Enter new name for '{current_name}':",
                QLineEdit.EchoMode.Normal,
                "",
            )
            if not accepted or not new_name.strip():
                return
            target_name = new_name.strip()
        else:
            target_name = str(target_name).strip()

        if not target_name or target_name == current_name:
            return

        # Prompt whether to change all instances or this instance only
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Change Speaker")
        msg_box.setText(f"Change '{current_name}' to '{target_name}' for:")

        all_btn = msg_box.addButton(f"All Instances of '{current_name}'", QMessageBox.ButtonRole.AcceptRole)
        single_btn = msg_box.addButton("This Instance Only", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = msg_box.addButton(QMessageBox.StandardButton.Cancel)

        msg_box.exec()
        clicked = msg_box.clickedButton()
        if clicked not in (all_btn, single_btn):
            return

        self.flush_pending_transcript_undo() if hasattr(self, "flush_pending_transcript_undo") else None
        before_state = self._capture_project_state() if hasattr(self, "_capture_project_state") else None

        if clicked == all_btn:
            if raw_speaker:
                self.speaker_names[str(raw_speaker)] = target_name
            self.add_custom_speaker_to_glossary(target_name)
            for idx, seg in enumerate(segments):
                if self.get_effective_speaker_name(idx, seg) == current_name:
                    override_key = f"SEG_{idx}_SPEAKER"
                    self.speaker_names[override_key] = target_name
                    self.segment_speaker_overrides[idx] = override_key
            self.log_activity(f"[SPEAKER] Changed all instances of '{current_name}' to '{target_name}'")
        elif clicked == single_btn:
            override_key = f"SEG_{seg_idx}_SPEAKER"
            self.speaker_names[override_key] = target_name
            self.segment_speaker_overrides[seg_idx] = override_key
            self.add_custom_speaker_to_glossary(target_name)
            self.log_activity(
                f"[SPEAKER] Changed single instance of '{current_name}' to '{target_name}' (Segment #{seg_idx})"
            )

        if before_state is not None and hasattr(self, "_commit_project_state_change"):
            self._commit_project_state_change(before_state, f"Change Speaker: {current_name} → {target_name}")

        self.render_transcript()
        self.save_project()
        self.statusBar().showMessage(f"Updated speaker to: {target_name}")

    def prompt_rename_speaker(self, seg_idx, speaker):
        self.execute_speaker_rename(seg_idx, speaker, "__NEW__")

    def remove_speaker_label_at_segment(self, seg_idx):
        """Remove a speaker label strictly for this specific instance/turn, 
        reassigning only this contiguous section to the preceding speaker."""
        if not self.transcript or "segments" not in self.transcript:
            return False

        segments = self.transcript.get("segments", [])
        if seg_idx <= 0 or seg_idx >= len(segments):
            return False  # Must have a previous segment to merge into

        self.flush_pending_transcript_undo() if hasattr(self, "flush_pending_transcript_undo") else None
        before_state = self._capture_project_state() if hasattr(self, "_capture_project_state") else None

        # 1. Determine the target speaker immediately preceding this label
        prev_seg_idx = seg_idx - 1
        target_name = self.get_effective_speaker_name(prev_seg_idx, segments[prev_seg_idx])
        target_raw = (
            self.segment_speaker_overrides.get(prev_seg_idx) 
            or self.speaker_for_segment(segments[prev_seg_idx])
        )

        # 2. Identify the speaker being removed at this specific position
        removed_name = self.get_effective_speaker_name(seg_idx, segments[seg_idx])

        # 3. Find only the CONTIGUOUS run of segments in this specific turn
        section_indices = []
        for i in range(seg_idx, len(segments)):
            if self.get_effective_speaker_name(i, segments[i]) == removed_name:
                section_indices.append(i)
            else:
                break  # Stop as soon as another speaker turn begins

        if not section_indices:
            return False

        section_indices_set = set(section_indices)

        # 4. Create isolated segment overrides for this section only.
        # We do NOT touch or reuse global speaker names to avoid altering 
        # other instances of either speaker that occur before or after.
        for idx in section_indices:
            instance_key = f"SEG_{idx}_SPEAKER"
            self.speaker_names[instance_key] = target_name
            self.segment_speaker_overrides[idx] = instance_key

        # 5. Reassign underlying diarization segments ONLY within this specific time range
        if self.diarization and isinstance(self.diarization, dict):
            sec_start = float(segments[section_indices[0]].get("start", 0.0))
            sec_end = float(segments[section_indices[-1]].get("end", sec_start))
            diar_segs = self.diarization.get("segments", [])
            updated_diar = False

            # Use the previous segment's underlying raw identity if valid, else an isolated key
            new_diar_speaker = target_raw or f"SEG_{prev_seg_idx}_SPEAKER"

            for d_seg in diar_segs:
                d_start = float(d_seg.get("start", 0.0))
                d_end = float(d_seg.get("end", d_start))

                # Check strict time-boundary overlap with this specific turn
                overlap = min(sec_end, d_end) - max(sec_start, d_start)
                if overlap <= 0.001:
                    continue

                # Find which transcript segment in this turn the diarization segment best overlaps
                best_seg_idx = None
                best_seg_overlap = 0.0

                for s_idx in section_indices:
                    t_seg = segments[s_idx]
                    t_start = float(t_seg.get("start", 0.0))
                    t_end = float(t_seg.get("end", t_start))
                    cur_overlap = min(t_end, d_end) - max(t_start, d_start)
                    if cur_overlap > best_seg_overlap:
                        best_seg_overlap = cur_overlap
                        best_seg_idx = s_idx

                if best_seg_idx in section_indices_set:
                    d_seg["speaker"] = new_diar_speaker
                    updated_diar = True

            if updated_diar:
                self._diar_index_key = None

        if before_state is not None and hasattr(self, "_commit_project_state_change"):
            self._commit_project_state_change(
                before_state,
                f"Remove Speaker Label: {removed_name} → {target_name} (turn at #{seg_idx + 1})"
            )

        self.log_activity(
            f"[SPEAKER] Removed speaker label '{removed_name}' at segment #{seg_idx + 1}; "
            f"merged {len(section_indices)} segment(s) into '{target_name}'"
        )
        self.save_project()
        self.render_transcript()
        self.statusBar().showMessage(f"Removed '{removed_name}' label at {format_time(segments[seg_idx].get('start', 0))}.")
        return True

    def merge_contiguous_speaker_segments(self):
        if not self.transcript or "segments" not in self.transcript:
            return

        segments = self.transcript["segments"]
        if not segments:
            return

        merged_segments = []
        new_overrides = {}
        curr_block = None
        curr_effective_name = None

        for idx, seg in enumerate(segments):
            effective_name = self.get_effective_speaker_name(idx, seg)

            if curr_block is None:
                curr_block = dict(seg)
                curr_block["words"] = list(seg.get("words", []))
                curr_effective_name = effective_name
            else:
                if effective_name == curr_effective_name:
                    curr_block["end"] = seg["end"]
                    curr_block["text"] = (curr_block["text"].strip() + " " + seg.get("text", "").strip()).strip()
                    curr_block["words"].extend(seg.get("words", []))
                else:
                    merged_idx = len(merged_segments)
                    merged_segments.append(curr_block)
                    if idx - 1 in self.segment_speaker_overrides:
                        new_overrides[merged_idx] = self.segment_speaker_overrides[idx - 1]

                    curr_block = dict(seg)
                    curr_block["words"] = list(seg.get("words", []))
                    curr_effective_name = effective_name

        if curr_block:
            merged_idx = len(merged_segments)
            merged_segments.append(curr_block)
            if len(segments) - 1 in self.segment_speaker_overrides:
                new_overrides[merged_idx] = self.segment_speaker_overrides[len(segments) - 1]

        self.transcript["segments"] = merged_segments
        self.segment_speaker_overrides = new_overrides

    def refresh_story_list(self):
        selected_indices = list(self.current_selected_story_indices)

        self.story_list.blockSignals(True)
        self.story_list.clear()

        for index, story in enumerate(self.stories, start=1):
            text = f"{index}. {format_time(story.start)} – {format_time(story.end)}  {story.title}"
            self.story_list.addItem(text)

        for idx in selected_indices:
            if 0 <= idx < self.story_list.count():
                self.story_list.item(idx).setSelected(True)

        self.story_list.blockSignals(False)
        self.timeline.set_stories(self.stories, selected_indices)

    def handle_new_story_started(self, start_time, end_time):
        self.pre_drag_stories_snapshot = [Story.from_dict(s.to_dict()) for s in self.stories]
        story = Story(start=start_time, end=end_time, title="Untitled Story")
        self.stories.append(story)

        self.refresh_story_list()
        self.story_selection_changed()

        self.start_input.setText(format_time(story.start))
        self.end_input.setText(format_time(story.end))
        self.title_input.setText(story.title)

    def handle_new_story_updated(self, start_time, end_time):
        if self.stories:
            story = self.stories[-1]
            story.start = start_time
            story.end = end_time

            self.start_input.setText(format_time(story.start))
            self.end_input.setText(format_time(story.end))
            self.refresh_story_list()

    def handle_drag_story_region(self, index, start_time, end_time):
        if not self.pre_drag_stories_snapshot:
            self.pre_drag_stories_snapshot = [Story.from_dict(s.to_dict()) for s in self.stories]

        if 0 <= index < len(self.stories):
            story = self.stories[index]
            story.start = start_time
            story.end = end_time

            self.start_input.setText(format_time(story.start))
            self.end_input.setText(format_time(story.end))
            self.refresh_story_list()

    def handle_drag_finished(self):
        if self.pre_drag_stories_snapshot:
            old_stories = self.pre_drag_stories_snapshot
            new_stories = [Story.from_dict(s.to_dict()) for s in self.stories]
            self.pre_drag_stories_snapshot = []
            self.commit_story_change(old_stories, new_stories, "Adjust Story Selection")

    def update_selected_story(self):
        selected_rows = list(self.current_selected_story_indices)

        if not selected_rows:
            return

        try:
            start = parse_time(self.start_input.text())
            end = parse_time(self.end_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Time", str(exc))
            return

        if end <= start:
            QMessageBox.warning(self, "Invalid Story", "End time must be after start time.")
            return

        index = selected_rows[0]
        old_stories = [Story.from_dict(s.to_dict()) for s in self.stories]
        new_stories = [Story.from_dict(s.to_dict()) for s in self.stories]

        new_stories[index].start = start
        new_stories[index].end = end
        new_stories[index].title = self.title_input.text().strip() or "Untitled Story"

        self.commit_story_change(old_stories, new_stories, "Update Story Details")

    def delete_selected_story(self):
        selected_rows = sorted(list(self.current_selected_story_indices), reverse=True)

        if not selected_rows:
            return

        old_stories = [Story.from_dict(s.to_dict()) for s in self.stories]
        new_stories = [Story.from_dict(s.to_dict()) for s in self.stories]

        for idx in selected_rows:
            del new_stories[idx]

        self.commit_story_change(old_stories, new_stories, "Delete Story")
	
    def add_selection_to_story(self):
        """Create a new story segment spanning the selected transcript text."""
        if not hasattr(self, "transcript_view"):
            return

        ranges = []
        if hasattr(self.transcript_view, "get_all_selected_story_ranges"):
            ranges = self.transcript_view.get_all_selected_story_ranges()

        if not ranges:
            cursor = self.transcript_view.textCursor()
            if not cursor.hasSelection():
                QMessageBox.information(
                    self,
                    "No Selection",
                    "Highlight a portion of the transcript first to create a story from it."
                )
                return

        # Multiple selections workflow: create separate stories for each selected section
        if len(ranges) > 1:
            old_stories = [Story.from_dict(s.to_dict()) for s in getattr(self, "stories", [])]
            created_stories = []
            for r in ranges:
                s_time = r.get("start_time", 0.0)
                e_time = r.get("end_time", s_time + 1.0)
                if e_time <= s_time:
                    e_time = s_time + 1.0
                text = r.get("text", "").strip()
                words = text.split()
                t = " ".join(words[:6]) + ("..." if len(words) > 6 else "") if words else "New Story"
                created_stories.append(Story(start=s_time, end=e_time, title=t))

            new_stories = sorted(old_stories + created_stories, key=lambda s: s.start)
            if hasattr(self, "commit_story_change"):
                self.commit_story_change(old_stories, new_stories, f"Add {len(created_stories)} Stories from Multi-Selection")
            else:
                self.stories = new_stories
                self.refresh_story_list()

            new_indices = [new_stories.index(s) for s in created_stories]
            if hasattr(self, "apply_story_selection_indices"):
                self.apply_story_selection_indices(new_indices)

            self.transcript_view.clear_all_selections()
            self.log_activity(f"[STORY] Added {len(created_stories)} stories from multi-selection.")
            self.statusBar().showMessage(f"Created {len(created_stories)} stories from multiple selections.")
            return

        # Single selection workflow
        start_time = None
        end_time = None
        selected_text = ""
        if ranges:
            start_time = ranges[0].get("start_time")
            end_time = ranges[0].get("end_time")
            selected_text = ranges[0].get("text", "")
        else:
            cursor = self.transcript_view.textCursor()
            selected_text = cursor.selectedText().strip()
            if hasattr(self.transcript_view, "get_selected_time_range"):
                sel_range = self.transcript_view.get_selected_time_range()
                if sel_range and sel_range[0] is not None and sel_range[1] is not None:
                    start_time, end_time = sel_range

        # Fallback to mapping character offsets to timestamps
        if start_time is None or end_time is None:
            cursor = self.transcript_view.textCursor()
            start_char = cursor.selectionStart()
            end_char = cursor.selectionEnd()
            char_map = getattr(self.transcript_view, "char_timestamp_map", [])
            for c_start, c_end, w_start, w_end, _ in char_map:
                if c_start <= start_char <= c_end and start_time is None:
                    start_time = w_start
                if c_start <= end_char <= c_end:
                    end_time = w_end

        # Fallback to playhead if mapping could not find timestamps
        if start_time is None:
            start_time = getattr(self, "current_position", 0.0)
        if end_time is None:
            end_time = min(getattr(self, "duration", start_time + 5.0), start_time + 5.0)

        if end_time <= start_time:
            end_time = start_time + 1.0

        # Auto-generate a preliminary title from the first few words of the selection
        words = selected_text.split()
        default_title = " ".join(words[:6]) + ("..." if len(words) > 6 else "") if words else "New Story"

        # Update input boxes if present
        if hasattr(self, "start_input"):
            self.start_input.setText(format_time(start_time))
        if hasattr(self, "end_input"):
            self.end_input.setText(format_time(end_time))
        if hasattr(self, "title_input"):
            self.title_input.setText(default_title)

        # Create the new story and commit it through the undo history
        new_story = Story(start=start_time, end=end_time, title=default_title)
        old_stories = [Story.from_dict(s.to_dict()) for s in getattr(self, "stories", [])]
        new_stories = sorted(old_stories + [new_story], key=lambda s: s.start)

        if hasattr(self, "commit_story_change"):
            self.commit_story_change(old_stories, new_stories, f"Add Story from Selection: '{default_title}'")
        else:
            self.stories = new_stories
            self.refresh_story_list()

        # Select the newly added story
        new_idx = new_stories.index(new_story)
        if hasattr(self, "apply_story_selection_indices"):
            self.apply_story_selection_indices([new_idx])

        self.transcript_view.clear_all_selections()
        self.log_activity(f"[STORY] Added story from selection ({format_time(start_time)} – {format_time(end_time)}).")
        self.statusBar().showMessage(f"Created story: {default_title}")

    def play_transcript_selection(self):
        """Play audio corresponding to the current transcript selection."""
        if not hasattr(self, "transcript_view"):
            return
        ranges = []
        if hasattr(self.transcript_view, "get_all_selected_story_ranges"):
            ranges = self.transcript_view.get_all_selected_story_ranges()
        if not ranges and hasattr(self.transcript_view, "get_selected_time_range"):
            tr = self.transcript_view.get_selected_time_range()
            if tr and tr[0] is not None:
                ranges = [{"start_time": tr[0], "end_time": tr[1]}]

        if ranges:
            start_t = ranges[0].get("start_time", 0.0)
            self.seek_to(start_t)
            if hasattr(self, "player") and hasattr(self, "toggle_play"):
                if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                    self.toggle_play()

    def select_all_stories(self):
        """Select every story in the story list and timeline."""
        if not getattr(self, "stories", []):
            return

        all_indices = list(range(len(self.stories)))
        self.apply_story_selection_indices(all_indices)
        if hasattr(self, "timeline"):
            self.timeline.set_stories(self.stories, all_indices)
        self.statusBar().showMessage(f"Selected all {len(self.stories)} stories.")

    def handle_timeline_selection_range_changed(self, start_time, end_time):
        """Synchronize timeline right-drag selection by highlighting transcript text."""
        if not hasattr(self, "transcript_view"):
            return

        if start_time is None or end_time is None:
            cursor = self.transcript_view.textCursor()
            if cursor.hasSelection():
                cursor.clearSelection()
                self.transcript_view.setTextCursor(cursor)
            return

        s = min(float(start_time), float(end_time))
        e = max(float(start_time), float(end_time))
        char_map = getattr(self.transcript_view, "char_timestamp_map", [])
        if not char_map:
            return

        first_char = None
        last_char = None

        for item in char_map:
            c_start = item[0]
            c_end = item[1]
            w_start = item[2]
            w_end = item[3] if len(item) >= 4 else w_start

            if w_end >= s and first_char is None:
                first_char = c_start
            if w_start <= e:
                last_char = c_end

        if first_char is not None and last_char is not None and last_char > first_char:
            cursor = self.transcript_view.textCursor()
            cursor.setPosition(first_char)
            cursor.setPosition(last_char, QTextCursor.MoveMode.KeepAnchor)
            self.transcript_view.setTextCursor(cursor)
            self.transcript_view.ensureCursorVisible()

    def add_story_from_range(self, start_time, end_time):
        """Create and commit a story spanning start_time to end_time."""
        s = min(float(start_time), float(end_time))
        e = max(float(start_time), float(end_time))
        if e <= s:
            e = s + 1.0

        default_title = "New Story"
        if hasattr(self, "transcript_for_range"):
            segs = self.transcript_for_range(s, e)
            words = " ".join(seg.get("text", "").strip() for seg in segs).split()
            if words:
                default_title = " ".join(words[:6]) + ("..." if len(words) > 6 else "")

        if hasattr(self, "start_input"):
            self.start_input.setText(format_time(s))
        if hasattr(self, "end_input"):
            self.end_input.setText(format_time(e))
        if hasattr(self, "title_input"):
            self.title_input.setText(default_title)

        new_story = Story(start=s, end=e, title=default_title)
        old_stories = [Story.from_dict(item.to_dict()) for item in getattr(self, "stories", [])]
        new_stories = sorted(old_stories + [new_story], key=lambda item: item.start)

        if hasattr(self, "commit_story_change"):
            self.commit_story_change(old_stories, new_stories, f"Add Story: '{default_title}'")
        else:
            self.stories = new_stories
            self.refresh_story_list()

        new_idx = new_stories.index(new_story)
        if hasattr(self, "apply_story_selection_indices"):
            self.apply_story_selection_indices([new_idx])

        self.log_activity(f"[STORY] Added story from selection ({format_time(s)} – {format_time(e)}).")
        self.statusBar().showMessage(f"Created story: {default_title}")

    def add_story_from_active_selection(self):
        """Add story using current timeline drag selection or highlighted transcript text."""
        canvas = getattr(getattr(self, "timeline", None), "canvas", None)
        if canvas and canvas.selection_start is not None and canvas.selection_end is not None:
            s = min(canvas.selection_start, canvas.selection_end)
            e = max(canvas.selection_start, canvas.selection_end)
            canvas.selection_start = None
            canvas.selection_end = None
            canvas.update()
            self.add_story_from_range(s, e)
            return

        if hasattr(self, "transcript_view") and self.transcript_view.has_active_selection():
            self.add_selection_to_story()
            return

        QMessageBox.information(
            self,
            "No Selection",
            "Make a selection first by right-click dragging across the timeline or highlighting transcript text."
        )
