from __future__ import annotations

import html
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPoint, QTimer, Qt
from PySide6.QtGui import QKeySequence, QColor, QCloseEvent, QMouseEvent, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizeGrip,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from live_captions.audio import AudioMode
from live_captions.capture_protection import exclude_window_from_capture
from live_captions.clipboard import set_clipboard_text
from live_captions.config import (
    LANGUAGES,
    Settings,
    resolve_language,
    resolve_whisper_language,
    save_deepgram_api_key,
)
from live_captions.deepgram import DeepgramTranscriptionThread
from live_captions.transcript import TranscriptBuffer
from live_captions.whisper_local import WhisperTranscriptionThread

if TYPE_CHECKING:
    from PySide6.QtGui import QKeySequence, QShowEvent


# Text colour + marker for each audio source (final text / interim text).
SOURCE_STYLES = {
    "computer": {"tag": "\U0001f50a COMPUTER", "final": "#9CC4FF", "interim": "#6C86AD"},
    "microphone": {"tag": "\U0001f3a4 MIC", "final": "#FFC857", "interim": "#A58A4B"},
}


class ApiKeyDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, current_key: str | None = None) -> None:
        super().__init__(parent)
        self._current_key = current_key or ""
        self._drag_origin: QPoint | None = None

        self.setWindowTitle("Configurar Chave Deepgram")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(520, 250)
        self._build_ui()
        self._apply_styles()

        self.winId()
        exclude_window_from_capture(self)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)

        card = QWidget(objectName="dialogCard")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 160))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("🔑  DEEPGRAM API KEY", objectName="dialogTitle")
        header.addWidget(title)
        header.addStretch(1)

        close_btn = QPushButton("×", objectName="closeButton")
        close_btn.setToolTip("Fechar")
        close_btn.clicked.connect(self.reject)
        header.addWidget(close_btn)
        card_layout.addLayout(header)

        # Subtitle
        subtitle = QLabel(
            "Cadastre ou altere sua chave da Deepgram. Ela fica salva no sistema e será carregada automaticamente ao abrir o aplicativo.",
            objectName="dialogSubtitle",
        )
        subtitle.setWordWrap(True)
        card_layout.addWidget(subtitle)

        # Input row
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self.key_input = QLineEdit(objectName="keyInput")
        self.key_input.setPlaceholderText("Cole sua chave aqui...")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setText(self._current_key)
        self.key_input.returnPressed.connect(self._on_save)
        input_layout.addWidget(self.key_input, 1)

        self.eye_btn = QPushButton("👁", objectName="secondaryButton")
        self.eye_btn.setToolTip("Mostrar / Ocultar chave")
        self.eye_btn.setFixedWidth(38)
        self.eye_btn.clicked.connect(self._toggle_visibility)
        input_layout.addWidget(self.eye_btn)
        card_layout.addLayout(input_layout)

        # Bottom buttons
        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addStretch(1)

        cancel_btn = QPushButton("Cancelar", objectName="secondaryButton")
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        save_btn = QPushButton("Salvar", objectName="primaryButton")
        save_btn.clicked.connect(self._on_save)
        footer.addWidget(save_btn)

        card_layout.addLayout(footer)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QWidget#dialogCard {
                background: rgba(13, 18, 31, 250);
                border: 1px solid rgba(126, 150, 255, 90);
                border-radius: 18px;
            }
            QLabel#dialogTitle {
                color: #8EA2FF;
                font-size: 12px;
                font-weight: 800;
                letter-spacing: 1px;
            }
            QLabel#dialogSubtitle {
                color: #9AA7C2;
                font-size: 12px;
                line-height: 1.4;
            }
            QLineEdit#keyInput {
                min-height: 32px;
                color: #F7F9FF;
                background: #172038;
                border: 1px solid #354364;
                border-radius: 10px;
                padding: 0 12px;
                font-size: 12px;
                selection-background-color: #6578E8;
            }
            QLineEdit#keyInput:focus {
                border: 1px solid #7D8EF3;
                background: #1B2642;
            }
            QPushButton {
                min-height: 30px;
                border-radius: 10px;
                padding: 0 14px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton#primaryButton {
                color: white;
                background: #6578E8;
                border: 1px solid #7D8EF3;
            }
            QPushButton#primaryButton:hover { background: #788AEE; }
            QPushButton#secondaryButton {
                color: #DCE3F8;
                background: rgba(255, 255, 255, 12);
                border: 1px solid rgba(255, 255, 255, 28);
            }
            QPushButton#secondaryButton:hover {
                background: rgba(255, 255, 255, 24);
            }
            QPushButton#closeButton {
                color: #94A0B8;
                background: transparent;
                border: 0;
                min-width: 26px;
                max-width: 26px;
                padding: 0;
                font-size: 16px;
            }
            QPushButton#closeButton:hover {
                color: white; background: #D94A62;
                border-radius: 6px;
            }
        """)

    def _toggle_visibility(self) -> None:
        if self.key_input.echoMode() == QLineEdit.EchoMode.Password:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.eye_btn.setText("🔒")
            self.eye_btn.setToolTip("Ocultar chave")
        else:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.eye_btn.setText("👁")
            self.eye_btn.setToolTip("Mostrar chave")

    def _on_save(self) -> None:
        key = self.key_input.text().strip()
        save_deepgram_api_key(key)
        self.accept()

    def saved_key(self) -> str:
        return self.key_input.text().strip()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        dragging = event.buttons() & Qt.MouseButton.LeftButton
        if self._drag_origin is not None and dragging:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_origin = None
        super().mouseReleaseEvent(event)


class CaptionsWindow(QWidget):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._transcript = TranscriptBuffer()
        self._worker: DeepgramTranscriptionThread | WhisperTranscriptionThread | None = None
        self._pending_restart = False
        self._closing = False
        self._drag_origin: QPoint | None = None
        self._protection_scheduled = False

        self.setWindowTitle("Live Captions")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(780, 260)
        self.resize(960, 340)
        self._build_ui()
        self._apply_styles()

        # Create the HWND early to minimize unprotected frames.
        self.winId()
        self._apply_capture_protection()
        QTimer.singleShot(350, self.start_transcription)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)

        self.card = QWidget(objectName="card")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(42)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 145))
        self.card.setGraphicsEffect(shadow)
        outer.addWidget(self.card)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(24, 18, 24, 14)
        card_layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(10)

        brand = QLabel("●  LIVE CAPTIONS", objectName="brand")
        header.addWidget(brand)

        self.status_label = QLabel("Getting ready…", objectName="status")
        header.addWidget(self.status_label)
        header.addStretch(1)

        self.protection_label = QLabel("◈ Checking privacy", objectName="protection")
        header.addWidget(self.protection_label)

        self.engine_combo = QComboBox(objectName="engine")
        self.engine_combo.addItem("Deepgram", userData="deepgram")
        self.engine_combo.addItem("Local Whisper", userData="whisper")
        self.engine_combo.setToolTip("Transcription engine")
        if not self._settings.api_key:
            self.engine_combo.setCurrentIndex(1)
        self.engine_combo.currentIndexChanged.connect(self._engine_changed)
        header.addWidget(self.engine_combo)

        self.language_combo = QComboBox(objectName="language")
        for key in LANGUAGES:
            self.language_combo.addItem(
                "PT" if key == "pt" else "EN",
                userData=key,
            )
        self.language_combo.setToolTip("Transcription language")
        self.language_combo.currentIndexChanged.connect(self._language_changed)
        header.addWidget(self.language_combo)

        self.audio_source_combo = QComboBox(objectName="audioSource")
        self.audio_source_combo.addItem("\U0001f50a Computer", userData=AudioMode.COMPUTER)
        self.audio_source_combo.addItem("\U0001f3a4 Mic", userData=AudioMode.MICROPHONE)
        self.audio_source_combo.addItem("\U0001f50a+\U0001f3a4 Both", userData=AudioMode.BOTH)
        self.audio_source_combo.setToolTip("Audio source to capture")
        self.audio_source_combo.currentIndexChanged.connect(self._audio_source_changed)
        header.addWidget(self.audio_source_combo)

        self.toggle_button = QPushButton("Pause", objectName="primaryButton")
        self.toggle_button.setToolTip("Start or pause audio capture")
        self.toggle_button.clicked.connect(self.toggle_transcription)
        header.addWidget(self.toggle_button)

        self.copy_button = QPushButton("Copy", objectName="secondaryButton")
        self.copy_button.clicked.connect(self.copy_text)
        header.addWidget(self.copy_button)

        self.clear_button = QPushButton("Clear", objectName="secondaryButton")
        self.clear_button.clicked.connect(self.clear_text)
        header.addWidget(self.clear_button)

        self.key_button = QPushButton("⚙ Key", objectName="secondaryButton")
        self.key_button.setToolTip("Configurar chave DEEPGRAM_API_KEY (salva no sistema)")
        self.key_button.clicked.connect(self.open_api_key_dialog)
        header.addWidget(self.key_button)

        minimize = QPushButton("—", objectName="windowButton")
        minimize.setToolTip("Minimize")
        minimize.clicked.connect(self.showMinimized)
        header.addWidget(minimize)

        close = QPushButton("×", objectName="closeButton")
        close.setToolTip("Close")
        close.clicked.connect(self.close)
        header.addWidget(close)
        card_layout.addLayout(header)

        self.caption_view = QTextEdit(objectName="captions")
        self.caption_view.setReadOnly(True)
        self.caption_view.setAcceptRichText(True)
        self.caption_view.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.caption_view.setPlaceholderText("Audio played on this computer will appear here…")
        self.caption_view.installEventFilter(self)
        card_layout.addWidget(self.caption_view, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(2, 0, 0, 0)
        hint = QLabel(
            "Always on top • drag the border to move the window",
            objectName="hint",
        )
        footer.addWidget(hint)
        footer.addStretch(1)
        legend = QLabel(
            f'<span style="color:{SOURCE_STYLES["computer"]["final"]};">\U0001f50a Computer</span>'
            "&nbsp;&nbsp;&nbsp;"
            f'<span style="color:{SOURCE_STYLES["microphone"]["final"]};">\U0001f3a4 Mic</span>',
            objectName="hint",
        )
        footer.addWidget(legend)
        footer.addWidget(QSizeGrip(self.card))
        card_layout.addLayout(footer)

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QWidget#card {
                background: rgba(13, 18, 31, 242);
                border: 1px solid rgba(126, 150, 255, 80);
                border-radius: 22px;
            }
            QLabel#brand {
                color: #8EA2FF;
                font-size: 12px;
                font-weight: 800;
                letter-spacing: 1px;
            }
            QLabel#status { color: #9AA7C2; font-size: 12px; }
            QLabel#protection {
                color: #6EE7B7;
                background: rgba(16, 185, 129, 28);
                border: 1px solid rgba(110, 231, 183, 55);
                border-radius: 9px;
                padding: 5px 9px;
                font-size: 11px;
            }
            QLabel#hint { color: #59667E; font-size: 11px; }
            QTextEdit#captions {
                color: #F7F9FF;
                background: rgba(255, 255, 255, 7);
                border: 1px solid rgba(255, 255, 255, 16);
                border-radius: 16px;
                padding: 18px;
                font-family: "Segoe UI Variable Display", "Segoe UI";
                font-size: 18px;
                font-weight: 600;
                selection-background-color: #6578E8;
            }
            QComboBox#language, QComboBox#engine, QComboBox#audioSource, QPushButton {
                min-height: 30px;
                border-radius: 10px;
                padding: 0 12px;
                font-size: 12px;
                font-weight: 700;
            }
            QComboBox#language, QComboBox#engine, QComboBox#audioSource {
                min-width: 48px;
                color: #DFE5FF;
                background: #202A44;
                border: 1px solid #354364;
            }
            QComboBox#language { min-width: 48px; }
            QComboBox#engine { min-width: 110px; }
            QComboBox#audioSource { min-width: 115px; }
            QComboBox#language::drop-down, QComboBox#engine::drop-down, QComboBox#audioSource::drop-down {
                border: 0; width: 15px;
            }
            QComboBox#language QAbstractItemView,
            QComboBox#engine QAbstractItemView,
            QComboBox#audioSource QAbstractItemView {
                color: #F7F9FF;
                background: #172038;
                selection-background-color: #6578E8;
            }
            QPushButton#primaryButton {
                color: white;
                background: #6578E8;
                border: 1px solid #7D8EF3;
            }
            QPushButton#primaryButton:hover { background: #788AEE; }
            QPushButton#secondaryButton {
                color: #DCE3F8;
                background: rgba(255, 255, 255, 12);
                border: 1px solid rgba(255, 255, 255, 28);
            }
            QPushButton#secondaryButton:hover {
                background: rgba(255, 255, 255, 24);
            }
            QPushButton#windowButton, QPushButton#closeButton {
                color: #94A0B8;
                background: transparent;
                border: 0;
                min-width: 28px;
                max-width: 28px;
                padding: 0;
                font-size: 16px;
            }
            QPushButton#windowButton:hover {
                color: white; background: #26314A;
            }
            QPushButton#closeButton:hover {
                color: white; background: #D94A62;
            }
            QPushButton:disabled {
                color: #667085;
                background: #252B3A;
                border-color: #303849;
            }
            QScrollBar:vertical {
                width: 7px; background: transparent; margin: 5px;
            }
            QScrollBar::handle:vertical {
                background: #3C4864; border-radius: 3px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height: 0; }
            """)

    def _apply_capture_protection(self) -> None:
        result = exclude_window_from_capture(self)
        self.protection_label.setText(f"◈ {result.message}")
        if result.fully_excluded:
            color = "#6EE7B7"
        elif result.protected:
            color = "#F9D675"
        else:
            color = "#FF7A90"
        self.protection_label.setStyleSheet(f"color: {color};")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._protection_scheduled:
            self._protection_scheduled = True
            QTimer.singleShot(0, self._apply_capture_protection)

    def start_transcription(self) -> None:
        if self._closing or (self._worker and self._worker.isRunning()):
            return
        language_key = str(self.language_combo.currentData())
        engine = str(self.engine_combo.currentData())
        audio_mode: AudioMode = self.audio_source_combo.currentData()  # type: ignore[assignment]
        if engine == "deepgram":
            if not self._settings.api_key:
                self._show_issue("DEEPGRAM_API_KEY não configurada.")
                self.toggle_button.setText("Start")
                saved = self.open_api_key_dialog()
                if not saved or not self._settings.api_key:
                    return
            language = resolve_language(language_key)
            self._worker = DeepgramTranscriptionThread(self._settings, language, audio_mode)
        else:
            language = resolve_whisper_language(language_key)
            self._worker = WhisperTranscriptionThread(self._settings, language, audio_mode)
        self._worker.transcript_received.connect(self._receive_transcript)
        self._worker.status_changed.connect(self.status_label.setText)
        self._worker.issue_detected.connect(self._show_issue)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()
        self.toggle_button.setText("Pause")
        self.toggle_button.setEnabled(True)

    def stop_transcription(self) -> None:
        if self._worker and self._worker.isRunning():
            self.status_label.setText("Stopping…")
            self.toggle_button.setEnabled(False)
            self.engine_combo.setEnabled(False)
            self.language_combo.setEnabled(False)
            self.audio_source_combo.setEnabled(False)
            self._worker.stop()

    def toggle_transcription(self) -> None:
        if self._worker and self._worker.isRunning():
            self._pending_restart = False
            self.stop_transcription()
        else:
            self.start_transcription()

    def _worker_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker:
            worker.deleteLater()
        self.toggle_button.setText("Start")
        self.toggle_button.setEnabled(True)
        self.engine_combo.setEnabled(True)
        self.language_combo.setEnabled(True)
        self.audio_source_combo.setEnabled(True)
        if self._closing:
            QTimer.singleShot(0, self.close)
            return
        if self._pending_restart:
            self._pending_restart = False
            QTimer.singleShot(100, self.start_transcription)

    def _language_changed(self) -> None:
        self._restart_running_worker()

    def _audio_source_changed(self) -> None:
        self._restart_running_worker()

    def _engine_changed(self) -> None:
        engine = str(self.engine_combo.currentData())
        if engine == "deepgram":
            self.engine_combo.setToolTip("Deepgram • sends audio to the cloud")
            if not self._settings.api_key:
                self._show_issue("DEEPGRAM_API_KEY não configurada. Cadastre a chave.")
                self.open_api_key_dialog()
        else:
            self.engine_combo.setToolTip("Whisper • 100% local processing")
        self._restart_running_worker()

    def open_api_key_dialog(self) -> bool:
        dialog = ApiKeyDialog(self, current_key=self._settings.api_key)
        dialog.move(
            self.x() + max(0, (self.width() - dialog.width()) // 2),
            self.y() + max(0, (self.height() - dialog.height()) // 2),
        )
        if dialog.exec():
            new_key = dialog.saved_key()
            self._settings = self._settings.with_api_key(new_key if new_key else None)
            if new_key:
                self.status_label.setText("Chave Deepgram atualizada")
                engine = str(self.engine_combo.currentData())
                if engine == "deepgram":
                    if self._worker and self._worker.isRunning():
                        self._restart_running_worker()
                    else:
                        self.status_label.setText("Pronto para iniciar com Deepgram")
            else:
                self.status_label.setText("Chave Deepgram removida")
                if str(self.engine_combo.currentData()) == "deepgram":
                    self.engine_combo.setCurrentIndex(1)
            return True
        return False

    def _restart_running_worker(self) -> None:
        if self._worker and self._worker.isRunning():
            self._pending_restart = True
            self.stop_transcription()

    def _render_transcript(self) -> str:
        paragraphs = []
        for turn in self._transcript.turns():
            style = SOURCE_STYLES.get(turn.source, SOURCE_STYLES["computer"])
            parts = [
                f'<span style="color:{style["final"]}; font-size:11px; font-weight:800;">{style["tag"]}</span>'
                "&nbsp;&nbsp;"
            ]
            if turn.final:
                parts.append(f'<span style="color:{style["final"]};">{html.escape(turn.final)}</span>')
            if turn.interim:
                parts.append(f' <span style="color:{style["interim"]};">{html.escape(turn.interim)}</span>')
            paragraphs.append(f'<p style="margin-top:0px; margin-bottom:10px;">{"".join(parts)}</p>')
        return "".join(paragraphs)

    def _receive_transcript(self, text: str, is_final: bool, source: str) -> None:
        self._transcript.apply(text, is_final, source)
        rendered = self._render_transcript()

        cursor = self.caption_view.textCursor()
        has_selection = cursor.hasSelection()
        selection_start = cursor.selectionStart()
        selection_end = cursor.selectionEnd()

        self.caption_view.setHtml(rendered)

        new_cursor = self.caption_view.textCursor()
        if has_selection:
            new_cursor.setPosition(selection_start)
            new_cursor.setPosition(selection_end, QTextCursor.KeepAnchor)
        else:
            new_cursor.movePosition(QTextCursor.MoveOperation.End)
        self.caption_view.setTextCursor(new_cursor)
        if not has_selection:
            self.caption_view.ensureCursorVisible()

    def _show_issue(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.setToolTip(message)

    def copy_text(self) -> None:
        original = self.copy_button.text()
        try:
            set_clipboard_text(self._transcript.text, owner_hwnd=int(self.winId()))
        except RuntimeError as exc:
            self._show_issue(str(exc))
            self.copy_button.setText("Failed")
            QTimer.singleShot(1600, lambda: self.copy_button.setText(original))
            return
        self.copy_button.setText("Copied ✓")
        QTimer.singleShot(1100, lambda: self.copy_button.setText(original))

    def clear_text(self) -> None:
        self._transcript.clear()
        self.caption_view.clear()


    def eventFilter(self, obj: QWidget, event: QEvent) -> bool:
        if obj is self.caption_view and event.type() == QEvent.Type.KeyPress:
            if event.matches(QKeySequence.StandardKey.Copy):
                cursor = self.caption_view.textCursor()
                if cursor.hasSelection():
                    text = cursor.selectedText().replace('\u2029', '\n')
                    try:
                        set_clipboard_text(text, owner_hwnd=int(self.winId()))
                    except RuntimeError as exc:
                        self._show_issue(str(exc))
                return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        dragging = event.buttons() & Qt.MouseButton.LeftButton
        if self._drag_origin is not None and dragging:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_origin = None
        super().mouseReleaseEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker and self._worker.isRunning():
            event.ignore()
            self._closing = True
            self._pending_restart = False
            self.stop_transcription()
            self.status_label.setText("Closing transcription…")
            return
        event.accept()
