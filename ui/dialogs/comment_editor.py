"""Comment and note editor dialog."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class CommentEditorDialog(QDialog):
    """Multi-line document-style comment editor supporting spaces, line breaks, and paragraph breaks."""

    def __init__(self, parent=None, comment_text="", title="Add Comment", prompt="Enter comment details:"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        label = QLabel(prompt, self)
        label.setWordWrap(True)
        label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(label)

        self.text_edit = QTextEdit(self)
        self.text_edit.setPlainText(comment_text)
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setPlaceholderText("Type your comment here... (Spaces, tabs, Enter line breaks, and Ctrl+Enter to save supported)")
        self.text_edit.setStyleSheet("font-size: 13px; line-height: 1.5; padding: 6px;")
        layout.addWidget(self.text_edit)

        btn_layout = QHBoxLayout()
        self.delete_btn = QPushButton("🗑️ Delete Comment", self)
        self.delete_btn.setStyleSheet("color: #dc2626; font-weight: bold;")
        self.delete_btn.setVisible(bool(comment_text and comment_text.strip()))

        self.save_btn = QPushButton("Save Comment", self)
        self.save_btn.setDefault(True)
        self.cancel_btn = QPushButton("Cancel", self)

        btn_layout.addWidget(self.delete_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.save_btn)
        layout.addLayout(btn_layout)

        self.save_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        self.delete_btn.clicked.connect(self._on_delete)
        self._is_deleted = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.accept()
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_delete(self):
        self._is_deleted = True
        self.accept()

    def get_comment_text(self):
        if self._is_deleted:
            return ""
        return self.text_edit.toPlainText()

    def get_note_text(self):
        return self.get_comment_text()

    def is_deleted(self):
        return self._is_deleted


# Alias for backward compatibility
NoteEditorDialog = CommentEditorDialog
