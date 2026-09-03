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
        segments = self.transcript.get("segments", [])

        if not segments:
            self.transcript_view.setHtml("")
            self.transcript_view.set_char_timestamp_map([])
            self._block_segment_groups = []
            if hasattr(self, "_capture_project_state") and not getattr(self, "is_restoring_undo", False):
                self._transcript_edit_baseline = self._capture_project_state()
            self.is_updating_transcript_view = False
            return

        word_tokens = []
        for seg_idx, segment in enumerate(segments):
            start = segment.get("start", 0.0) if isinstance(segment, dict) else getattr(segment, "start", 0.0)
            end = segment.get("end", start) if isinstance(segment, dict) else getattr(segment, "end", start)
            raw_spk = self.segment_speaker_overrides.get(seg_idx) or self.speaker_at_time(start, end)
            spk_name = self.get_effective_speaker_name(seg_idx, segment)

            words = segment.get("words", [])
            if words:
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
        elif curr_theme == "high_contrast":
            word_color = "#ffffff"
            speaker_color = "#00ffff"
            time_color = "#ffff00"
        else:
            word_color = "#ffffff"
            speaker_color = "#58a6ff"
            time_color = "#8b949e"

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
            self.timeline.set_transcript_selection_range(None, None)

    def on_transcript_text_changed(self):
        if self.is_updating_transcript_view or getattr(self, "is_restoring_undo", False) or not self.transcript:
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

    def prompt_rename_speaker(self, seg_idx, speaker):
        self.flush_pending_transcript_undo() if hasattr(self, "flush_pending_transcript_undo") else None
        before_state = self._capture_project_state() if hasattr(self, "_capture_project_state") else None
        current_name = self.get_effective_speaker_name(seg_idx, self.transcript["segments"][seg_idx]) if (self.transcript and seg_idx < len(self.transcript.get("segments", []))) else self.display_speaker(speaker)

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Speaker Options")
        msg_box.setText(f"Speaker: '{current_name}' (Segment #{seg_idx})")

        all_btn = msg_box.addButton("Rename All Instances", QMessageBox.ButtonRole.AcceptRole)
        single_btn = msg_box.addButton("Rename This Instance Only", QMessageBox.ButtonRole.ActionRole)
        cancel_btn = msg_box.addButton(QMessageBox.StandardButton.Cancel)

        msg_box.exec()
        clicked = msg_box.clickedButton()

        if clicked in (all_btn, single_btn):
            new_name, accepted = QInputDialog.getText(
                self,
                "New Speaker Name",
                f"Enter new name for {current_name}:",
                QLineEdit.EchoMode.Normal,
                current_name,
            )

            if not accepted or not new_name.strip():
                return

            new_name = new_name.strip()

            if clicked == all_btn:
                if speaker:
                    self.speaker_names[str(speaker)] = new_name
                    self.add_custom_speaker_to_glossary(new_name)
                for idx, seg in enumerate(self.transcript.get("segments", [])):
                    if self.get_effective_speaker_name(idx, seg) == current_name:
                        override_key = f"SEG_{idx}_SPEAKER"
                        self.speaker_names[override_key] = new_name
                        self.segment_speaker_overrides[idx] = override_key
                self.log_activity(f"[SPEAKER] Renamed all instances of '{current_name}' to '{new_name}'")
            elif clicked == single_btn:
                override_key = f"SEG_{seg_idx}_SPEAKER"
                self.speaker_names[override_key] = new_name
                self.segment_speaker_overrides[seg_idx] = override_key
                self.log_activity(f"[SPEAKER] Renamed single instance of '{current_name}' to '{new_name}' (Segment #{seg_idx})")

            if before_state is not None and hasattr(self, "_commit_project_state_change"):
                self._commit_project_state_change(before_state, f"Rename Speaker: {current_name} → {new_name}")
            self.render_transcript()
            self.save_project()
            self.statusBar().showMessage(f"Updated speaker to: {new_name}")

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

        # Generate a unique segment-specific override key so it never collides globally
        unique_key = f"SEG_{seg_idx}_SPEAKER_{int(split_time * 1000)}"
        self.speaker_names[unique_key] = name

        # If click is at start of segment, reassign this segment directly without splitting
        if is_at_segment_start:
            self.flush_pending_transcript_undo() if hasattr(self, "flush_pending_transcript_undo") else None
            before_state = self._capture_project_state() if hasattr(self, "_capture_project_state") else None

            self.segment_speaker_overrides[seg_idx] = unique_key
            self._diar_index_key = None

            if before_state is not None and hasattr(self, "_commit_project_state_change"):
                self._commit_project_state_change(before_state, f"Add Speaker Label ({name})")

            self.add_custom_speaker_to_glossary(name)
            self.log_activity(f"[SPEAKER] Set speaker label '{name}' at segment #{seg_idx + 1}")
            self.save_project()
            self.render_transcript()
            return True

        # Otherwise, split segment at word boundary
        if not self.split_segment_at_time(seg_idx, split_time, new_speaker_key=unique_key):
            # Fallback: assign directly if split boundary is tightly constrained
            self.flush_pending_transcript_undo() if hasattr(self, "flush_pending_transcript_undo") else None
            before_state = self._capture_project_state() if hasattr(self, "_capture_project_state") else None

            self.segment_speaker_overrides[seg_idx] = unique_key
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

    def split_segment_at_time(self, seg_idx, split_time, new_speaker_key=None):
        """Split a segment at an exact word timestamp."""
        if not self.transcript or "segments" not in self.transcript:
            return False

        segments = self.transcript.get("segments", [])
        if seg_idx < 0 or seg_idx >= len(segments):
            return False

        target_seg = segments[seg_idx]
        words = target_seg.get("words", [])

        if words:
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

        if new_speaker_key:
            self.segment_speaker_overrides[seg_idx + 1] = new_speaker_key

        self._diar_index_key = None

        if before_state is not None and hasattr(self, "_commit_project_state_change"):
            self._commit_project_state_change(
                before_state,
                "Add Speaker Label Break"
            )

        self.log_activity(f"[SPEAKER] Added speaker label break at {format_time(split_time)} (Split Segment #{seg_idx + 1})")
        self.save_project()
        self.render_transcript()
        return True

    def remove_speaker_label_at_segment(self, seg_idx):
        """Remove a speaker label strictly for this specific turn by clearing its override,
        merging it back into the preceding speaker without touching other sections."""
        if not self.transcript or "segments" not in self.transcript:
            return False

        segments = self.transcript.get("segments", [])
        if seg_idx <= 0 or seg_idx >= len(segments):
            return False  # Must have a previous segment to merge into

        self.flush_pending_transcript_undo() if hasattr(self, "flush_pending_transcript_undo") else None
        before_state = self._capture_project_state() if hasattr(self, "_capture_project_state") else None

        removed_name = self.get_effective_speaker_name(seg_idx, segments[seg_idx])
        prev_seg_idx = seg_idx - 1
        target_name = self.get_effective_speaker_name(prev_seg_idx, segments[prev_seg_idx])

        # Find only the CONTIGUOUS run of segments starting at seg_idx with removed_name
        section_indices = []
        for i in range(seg_idx, len(segments)):
            if self.get_effective_speaker_name(i, segments[i]) == removed_name:
                section_indices.append(i)
            else:
                break

        if not section_indices:
            return False

        # To remove this label, we simply delete its segment override so it falls back 
        # to the preceding speaker or underlying track, without touching any other part of the file.
        for idx in section_indices:
            if idx in self.segment_speaker_overrides:
                del self.segment_speaker_overrides[idx]

        self._diar_index_key = None

        if before_state is not None and hasattr(self, "_commit_project_state_change"):
            self._commit_project_state_change(
                before_state,
                f"Remove Speaker Label: {removed_name} → {target_name}"
            )

        self.log_activity(
            f"[SPEAKER] Removed speaker label '{removed_name}' at segment #{seg_idx + 1}; "
            f"merged {len(section_indices)} segment(s) into '{target_name}'"
        )
        self.save_project()
        self.render_transcript()
        self.statusBar().showMessage(f"Merged into '{target_name}'.")
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

    def add_story(self):
        start = self.current_position
        end = min(self.duration, start + 300)

        old_stories = [Story.from_dict(s.to_dict()) for s in self.stories]
        story = Story(start=start, end=end, title="Untitled Story")
        new_stories = old_stories + [story]

        self.commit_story_change(old_stories, new_stories, "Add Story")
        self.apply_story_selection_indices([len(self.stories) - 1])

    def set_story_start(self):
        selected_rows = list(self.current_selected_story_indices)

        if not selected_rows:
            self.add_story()
            return

        index = selected_rows[0]
        old_stories = [Story.from_dict(s.to_dict()) for s in self.stories]
        new_stories = [Story.from_dict(s.to_dict()) for s in self.stories]

        story = new_stories[index]
        story.start = self.current_position

        if story.end <= story.start:
            story.end = min(self.duration, story.start + 300)

        self.commit_story_change(old_stories, new_stories, "Set Story Start")

    def set_story_end(self):
        selected_rows = list(self.current_selected_story_indices)

        if not selected_rows:
            self.add_story()
            return

        index = selected_rows[0]
        story = self.stories[index]

        if self.current_position <= story.start:
            QMessageBox.warning(self, "Invalid Boundary", "The story end must be after the story start.")
            return

        old_stories = [Story.from_dict(s.to_dict()) for s in self.stories]
        new_stories = [Story.from_dict(s.to_dict()) for s in self.stories]

        new_stories[index].end = self.current_position
        self.commit_story_change(old_stories, new_stories, "Set Story End")

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