# Next Steps & Feedback (v3.0.0-beta.5 / v3.0.1-beta-1)

## ✅ Completed in v3.0.1-beta-1

### 1. Transcript Rich Text Formatting Toolbar & Styling Engine
- [x] **Formatting Toolbar (`transcript_format_toolbar`)**: Added toolbar directly above the transcript view that automatically appears when Editing Mode is enabled (`Edit Transcript` or `Ctrl+E`).
- [x] **Quick Action Buttons**: Bold, Italic, Underline, Strikethrough, Highlight (yellow text background), Clear Formatting (`Ctrl+\`), and Split Speaker Segment (`Shift+Enter`).
- [x] **Standard Keyboard Shortcuts**: Full support in `InteractiveTranscriptEdit` for `Ctrl+B` (Bold), `Ctrl+I` (Italic), `Ctrl+U` (Underline), `Ctrl+K` (Strikethrough), and `Ctrl+\` / `Ctrl+Space` (Clear).
- [x] **Bidirectional State Sync**: Buttons dynamically update their pressed/checked state matching the styling at the current cursor position or selection (`formatChanged` signal & cursor tracking).
- [x] **Context Menu Access**: Added "Format Text" submenu in right-click context menu when editing mode is active.
- [x] **Non-Destructive Word Token Persistence**: Preserved style formatting attributes across word splicing (`sync_segment_words`) and rendering (`render_paragraph_block`).

### 2. Multi-Location Comments Sidebar Toggles
- [x] **View > Transcript Submenu**: Added checkable "Show Comments Sidebar" option (`Ctrl+Alt+M`).
- [x] **View Menu**: Synchronized with existing top-level "Show Comments Sidebar & Highlights" action.
- [x] **Transcript Search Bar**: Synchronized with the "💬 Comments" header toggle button.
- [x] **Sidebar Close Button**: Connected the Comments panel's `✕` close button to synchronously update all menu items and buttons.
- [x] **Preference Persistence**: Saved visibility state to `QSettings` (`show_comments`).

---

## Feature Re-Architecture: From "Notes" to "Comments" (Completed in v3.0.0-beta.5)
*(Inspired by Microsoft Word, Google Docs, and LibreOffice Writer)*

### 💡 Visual & Interaction Model: Comments in Radio & TV Story Segmenter

In modern document processors (Microsoft Word, Google Docs, LibreOffice Writer), comments are never injected as raw inline body text. Instead, they operate as a non-destructive annotation layer:

1. **Text Anchor & Subtle Highlight**:
   - When a user highlights any word, phrase, sentence, or segment and selects **"💬 Add Comment"** (or hits `Ctrl+Alt+M` / selection bubble), the selected text receives an amber/yellow tint highlight (e.g. `#fef08a` in light mode, `#854d0e` in dark mode).
   - The transcript body text remains 100% clean and readable—no notes, headers, or brackets are inserted into the body text.

2. **Dedicated Comments Margin / Side Panel (Docked Panel)**:
   - A dedicated, collapsible **Comments Panel** sits alongside (to the right of) the Transcript View, just like Google Docs' comment gutter or Word's modern Comments Pane.
   - Each comment is rendered as a clean card containing:
     * **Timestamp & Quote Anchor**: e.g., `[02:14 - 02:22]` quoting the anchored text excerpt. Clicking the timestamp or quote jumps playback and scrolls the transcript directly to that passage.
     * **Comment Content**: Multi-line comment text with complete support for spaces, tabs, and paragraph breaks.
     * **Card Actions**: ✏️ Edit, 🗑️ Delete / Resolve, and jump to timeline position.
   - **Two-Way Synchronization**:
     * Clicking or hovering highlighted text in the transcript highlights and scrolls to its corresponding comment card in the sidebar.
     * Clicking a comment card in the sidebar highlights the anchored text and seeks media playback to that timestamp.

3. **Spacebar & Focus Isolation (Critical Fix)**:
   - When any comment editor (or dialog/input box) is in focus, global shortcuts (specifically the **Spacebar** play/pause toggle and arrow key navigation) are strictly suppressed.
   - Pressing the Spacebar inputs a literal space character; `Enter` creates a line/paragraph break; `Ctrl+Enter` or a "Save Comment" button saves the comment.

4. **Removal of Project & Episode Notes (Comments Only Focus)**:
   - **Remove All Project/Episode Notes**: Completely decommission and remove the "Project & Episode Notes" concept, dialog (`open_transcript_notes_dialog`), and right-click menu item (`Transcript & Project Notes...`).
   - **Comments Exclusively**: The feature is strictly and solely **Comments**—anchored to highlighted text spans in the transcript, just like in Microsoft Word, Google Docs, and LibreOffice Writer.

5. **Native Word Document (DOCX) Export**:
   - In Microsoft Word, comments are structured as native OpenXML comments (`w:comment` anchored to `w:commentRangeStart` / `w:commentRangeEnd`).
   - When exporting to Word (.docx), user comments should export either as native Word comments (so they show in Word/Docs comment margins) or as cleanly styled, right-indented margin callouts, controllable by an **"Include Comments"** checkbox. No project notes sections will be added.

---

## ✅ Priority Task Checklist (Completed in v3.0.0-beta.5)

### 1. Remove Project & Episode Notes (Scope Reduction)
- [x] **Remove "Project & Episode Notes"**: Deleted `open_transcript_notes_dialog`, the `📋 Transcript & Project Notes...` menu item, and project notes export headers. The app now features segment comments only.

### 2. Comments UI & Architecture (Word / Docs / Writer Style)
- [x] **Rename all UI references**: Replaced "Note / Notes" with **"Comment / Comments"** across context menus, bubble toolbar, shortcuts, and dialogs.
- [x] **Remove Inline Text Ingestion**: Transcript view never inserts raw comment text into the document body, keeping transcript text clean.
- [x] **Comments Side Panel / Drawer**: Added collapsible docked Comments sidebar (`CommentsPanel`) to the right of the transcript view to house comment cards.
- [x] **Text Highlighting & Anchoring**: Associated comments with text ranges/anchors with amber highlighting; supported hover tooltips and two-way card-to-transcript focus.
- [x] **View Menu Toggle**: Provided checkable **"View > Show Comments Sidebar & Highlights"** (`Ctrl+Alt+M`) and search bar button to show/hide sidebar and text highlights.

### 3. Spacebar & Dialog Focus Isolation
- [x] **Suppress Global Play/Pause on Text Focus**: Suppressed Spacebar from triggering media playback when typing inside any comment input, dialog, or focused text control (`eventFilter`).
- [x] **Multi-Line & Spacing Support**: Enabled full support for spaces, tabs, line breaks (`Enter`), and quick save (`Ctrl+Enter`) in `CommentEditorDialog`.

### 4. Transcript Keyboard Navigation Fixes
- [x] **Home Key**: Move text cursor strictly to the start of the current paragraph block (not whole document) and seek to block start timestamp.
- [x] **End Key**: Move text cursor strictly to the end of the current paragraph block (not end of document) and seek to block end timestamp.
- [x] **Arrow Keys (Left / Right)**: In viewing mode, skip media playback by user-configured interval (e.g. 5s) and update both the timeline cursor and transcript word highlighting.

### 5. Word Document (DOCX) Export with Comments
- [x] **Export Dialog Toggle**: Added an **"Include Comments"** checkbox in the Export dialog with persistent preferences.
- [x] **Native DOCX Comment / Callout Formatting**: Formatted anchored comments as cleanly styled indented margin callouts with timing and speaker context in exported Word documents.

---

## Roadmap Note
Proceed with resolving all items in this checklist before moving on to any subsequent roadmap features.


