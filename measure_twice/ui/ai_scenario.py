# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""The AI scenario screen: six prompts to copy into an AI chat, then its answer to load.

Done steps fold into one line, the current one is open, the future ones are grey lines.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QT_TRANSLATE_NOOP, Qt
from PySide6.QtGui import QGuiApplication, QPainter, QTextCursor
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from measure_twice import i18n
from measure_twice.ai import Prompt, prompts, remarks_prompt, task_limit, task_prompt
from measure_twice.ui.tables import label, plural, translate

TITLE = QT_TRANSLATE_NOOP("AiScenarioDialog", "Add a process with AI")
COPIED = QT_TRANSLATE_NOOP("AiScenarioDialog", "✓ Copied. Paste it into your AI chat.")
PROMPT_COPIED = QT_TRANSLATE_NOOP("AiScenarioDialog", "Prompt copied")
SHOW_AGAIN = QT_TRANSLATE_NOOP("AiScenarioDialog", "Show prompt again")
HIDE_AGAIN = QT_TRANSLATE_NOOP("AiScenarioDialog", "Hide prompt")
ANSWER_CAPTION = QT_TRANSLATE_NOOP("AiScenarioDialog", "Paste the AI’s answer")
FILE_STEP = 5
# The header note of each step on screen; the notes in the prompts file are for its readers.
NOTES = {
    1: QT_TRANSLATE_NOOP(
        "AiScenarioDialog",
        "Describe the job in one or two sentences, then copy the prompt into your AI chat.",
    ),
    2: QT_TRANSLATE_NOOP("AiScenarioDialog", "Use it when you have agreed on the list of ways."),
    3: QT_TRANSLATE_NOOP(
        "AiScenarioDialog", "Use it when you have agreed on the steps of each way."
    ),
    4: QT_TRANSLATE_NOOP(
        "AiScenarioDialog", "Use it when you have agreed on the actions and the checks."
    ),
    5: QT_TRANSLATE_NOOP(
        "AiScenarioDialog", "Use it when you have agreed who does what and how long it takes."
    ),
    6: QT_TRANSLATE_NOOP(
        "AiScenarioDialog",
        "The program found problems in the file. Copy this prompt into the same chat.",
    ),
}
REMARKS_STEP = 6

# What loading an answer returns: whether it loaded, and a message or the remark lines.
Loader = Callable[[str], tuple[bool, str | list[str]]]


def _repolish(*widgets: QWidget) -> None:
    for w in widgets:
        w.style().unpolish(w)
        w.style().polish(w)


def _not_accepted(count: int) -> str:
    one = "Not accepted: %n remark"
    text = translate("AiScenarioDialog", "Not accepted: %n remark", "", count)
    return plural(text, one, "Not accepted: %n remarks", count)


class ElidedLabel(QLabel):
    """A one-line label that ends with “…” when it does not fit; ``text()`` stays whole."""

    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        metrics = self.fontMetrics()
        shown = metrics.elidedText(self.text(), Qt.TextElideMode.ElideRight, self.width())
        painter.drawText(self.rect(), int(self.alignment()), shown)


class StepCard(QFrame):
    """One step: a head line and a body with the prompt and the buttons.

    :param prompt: the step's prompt.
    """

    def __init__(self, prompt: Prompt) -> None:
        super().__init__()
        self.number = prompt.number
        self.state = "future"
        self.expanded = False
        self.was_copied = False
        self.setObjectName("aiStep")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.head = QFrame()
        self.head.setObjectName("aiStepHead")
        head = QHBoxLayout(self.head)
        head.setContentsMargins(14, 8, 14, 8)
        head.setSpacing(8)
        self.mark = label("✓", "aiMark")
        head.addWidget(self.mark)
        self.title = label(f"{prompt.number}. {prompt.name}", "aiStepTitle")
        head.addWidget(self.title)
        self.summary = ElidedLabel()
        self.summary.setObjectName("aiSummary")
        head.addWidget(self.summary, 1)
        note = NOTES.get(prompt.number)
        self.note = label(translate("AiScenarioDialog", note) if note else prompt.note, "note")
        self.note.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(self.note, 1)
        self.again_button = QPushButton(translate("AiScenarioDialog", SHOW_AGAIN))
        self.again_button.setObjectName("aiLink")
        self.again_button.setCursor(Qt.CursorShape.PointingHandCursor)
        head.addWidget(self.again_button)
        lay.addWidget(self.head)

        self.body = QWidget()
        self.body.setObjectName("aiStepBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(16, 12, 16, 14)
        self.body_layout.setSpacing(10)
        self.prompt_view = QPlainTextEdit()
        self.prompt_view.setObjectName("aiPrompt")
        self.prompt_view.setReadOnly(True)
        self.prompt_view.setFixedHeight(170)
        self.body_layout.addWidget(self.prompt_view)
        self.row = QHBoxLayout()
        self.row.setSpacing(8)
        self.copied = label(translate("AiScenarioDialog", COPIED), "note")
        self.row.addWidget(self.copied)
        self.row.addStretch(1)
        self.copy_button = QPushButton(self.tr("Copy prompt"))
        self.next_button = QPushButton(self.tr("Next step"))
        self.next_button.setProperty("primary", True)
        self.row.addWidget(self.copy_button)
        self.row.addWidget(self.next_button)
        self.body_layout.addLayout(self.row)
        lay.addWidget(self.body)

        # Widgets shown only while the step is the current one.
        self.extras: list[QWidget] = []
        # The button that moves on, shown on the current step once the prompt is copied.
        self.forward: QPushButton | None = self.next_button


class AiScenarioDialog(QDialog):
    """The six steps of the AI scenario.

    :param load: loads the pasted answer: ``(True, message)`` or ``(False, message or remarks)``.
    :param parent: the parent window.
    """

    def __init__(self, load: Loader, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._load = load
        self._lang = i18n.current()  # the prompts are in the language of the window
        self._prompts = prompts(self._lang)
        self._remarks: list[str] = []
        self.setObjectName("aiScenario")
        self.setWindowTitle(translate("AiScenarioDialog", TITLE))
        self.setModal(True)
        self.resize(1000, 820)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        top = QFrame()
        top.setObjectName("aiTop")
        top_row = QHBoxLayout(top)
        top_row.setContentsMargins(16, 10, 16, 10)
        top_row.addWidget(label(translate("AiScenarioDialog", TITLE), "aiTopTitle"))
        top_row.addStretch(1)
        self.close_button = QPushButton(self.tr("Close"))
        self.close_button.setObjectName("aiLink")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        top_row.addWidget(self.close_button)
        lay.addWidget(top)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget()
        centre = QHBoxLayout(page)
        centre.setContentsMargins(16, 18, 16, 18)
        column = QWidget()
        column.setMaximumWidth(900)
        self.column = QVBoxLayout(column)
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(8)
        centre.addWidget(column)
        self.scroll.setWidget(page)
        lay.addWidget(self.scroll, 1)

        self.cards = [StepCard(prompt) for prompt in self._prompts]
        for card in self.cards:
            self.column.addWidget(card)
        self.column.addStretch(1)
        self._build_task()
        self._build_file()
        self._build_remarks()
        for card in self.cards:
            card.copy_button.clicked.connect(lambda _=False, c=card: self.copy(c))
            card.next_button.clicked.connect(lambda _=False, c=card: self.next_step(c))
            card.again_button.clicked.connect(lambda _=False, c=card: self.toggle_again(c))
        self.close_button.clicked.connect(self.reject)
        self._go(1)

    def _build_task(self) -> None:
        card = self.cards[0]
        self._task_limit = task_limit(self._lang)
        self.task = QPlainTextEdit()
        self.task.setObjectName("aiTask")
        self.task.setFixedHeight(64)
        self.task_left = label("", "note")
        self.task_left.setAlignment(Qt.AlignmentFlag.AlignRight)
        card.body_layout.insertWidget(0, self.task)
        card.body_layout.insertWidget(1, self.task_left)
        card.extras.append(self.task)
        card.extras.append(self.task_left)
        self.task.textChanged.connect(lambda: self._task_changed(card))
        self._show_left()

    def _task_changed(self, card: StepCard) -> None:
        text = self.task.toPlainText()
        if len(text) > self._task_limit:
            self.task.setPlainText(text[:self._task_limit])
            self.task.moveCursor(QTextCursor.MoveOperation.End)
            return
        self._show_left()
        self._render(card)

    def _show_left(self) -> None:
        left = self._task_limit - len(self.task.toPlainText())
        one = "%n character left"
        text = translate("AiScenarioDialog", "%n character left", "", left)
        self.task_left.setText(plural(text, one, "%n characters left", left))

    def _build_file(self) -> None:
        card = self.cards[FILE_STEP - 1]
        card.forward = None
        caption = label(translate("AiScenarioDialog", ANSWER_CAPTION), "aiCaption")
        self.answer = QPlainTextEdit()
        self.answer.setObjectName("aiAnswer")
        self.answer.setMinimumHeight(150)
        self.error = label("", "err")
        load_row = QHBoxLayout()
        load_row.addStretch(1)
        self.load_button = QPushButton(self.tr("Load file"))
        self.load_button.setProperty("primary", True)
        load_row.addWidget(self.load_button)
        holder = QWidget()
        holder.setLayout(load_row)
        load_row.setContentsMargins(0, 0, 0, 0)
        for w in (caption, self.answer, self.error, holder):
            card.body_layout.addWidget(w)
            card.extras.append(w)
        self.load_button.clicked.connect(self.load)
        self.answer.textChanged.connect(lambda: self._render(card))

    def _build_remarks(self) -> None:
        card = self.cards[REMARKS_STEP - 1]
        self.back_button = QPushButton(self.tr("Back to step {n}").format(n=FILE_STEP))
        card.row.addWidget(self.back_button)
        card.forward = self.back_button
        self.back_button.clicked.connect(self.back_to_file)

    # --- texts

    def prompt_text(self, number: int) -> str:
        """The prompt of a step as it is copied: with the task or the remarks filled."""
        if number == 1:
            return task_prompt(self.task.toPlainText(), self._lang)
        if number == REMARKS_STEP:
            return remarks_prompt(self._remarks, self._lang)
        return self._prompts[number - 1].text

    def _summary(self, card: StepCard) -> str:
        if card.number == 1:
            return " ".join(self.task.toPlainText().split())
        if card.number == FILE_STEP:
            return _not_accepted(len(self._remarks))
        return translate("AiScenarioDialog", PROMPT_COPIED)

    def current(self) -> int:
        """The number of the open step."""
        return next(card.number for card in self.cards if card.state == "current")

    # --- showing

    def _render(self, card: StepCard) -> None:
        current = card.state == "current"
        done = card.state == "done"
        card.mark.setVisible(done)
        card.summary.setVisible(done)
        card.summary.setText(self._summary(card) if done else "")
        card.again_button.setVisible(done)
        card.again_button.setText(
            translate("AiScenarioDialog", HIDE_AGAIN if card.expanded else SHOW_AGAIN)
        )
        card.note.setVisible(current)
        card.body.setVisible(current or (done and card.expanded))
        for w in card.extras:
            w.setVisible(current)
        if card.number == FILE_STEP:
            self.error.setVisible(current and bool(self.error.text()))
        card.copied.setVisible(card.was_copied)
        card.next_button.setVisible(current and card.forward is card.next_button
                                    and card.was_copied)
        if card.number == REMARKS_STEP:
            self.back_button.setVisible(current)
        text = self.prompt_text(card.number)
        if card.prompt_view.toPlainText() != text:
            card.prompt_view.setPlainText(text)
        card.copy_button.setEnabled(card.number != 1 or bool(self.task.toPlainText().strip()))
        # One primary button: Copy prompt until it is pressed, then the button that moves on.
        primary = current and not card.was_copied
        if card.number == FILE_STEP:
            primary = primary and not self.answer.toPlainText()
        card.copy_button.setProperty("primary", primary)
        if card.number == REMARKS_STEP:
            self.back_button.setProperty("primary", card.was_copied)
        for w in (card, card.head, card.title):
            w.setProperty("state", card.state)
        _repolish(card, card.head, card.title, card.copy_button, card.forward or card.copy_button)

    def _go(self, number: int) -> None:
        for card in self.cards:
            if card.number < number:
                card.state = "done"
            elif card.number == number:
                card.state = "current"
                card.expanded = False
            else:
                card.state = "future"
                card.expanded = False
                card.was_copied = False
            self._render(card)
        self.scroll.ensureWidgetVisible(self.cards[number - 1])

    # --- actions

    def copy(self, card: StepCard) -> None:
        """Put the step's prompt on the clipboard."""
        QGuiApplication.clipboard().setText(self.prompt_text(card.number))
        card.was_copied = True
        self._render(card)

    def next_step(self, card: StepCard) -> None:
        """Fold the step and open the next one."""
        self._go(card.number + 1)

    def toggle_again(self, card: StepCard) -> None:
        """Show or hide the prompt of a done step."""
        card.expanded = not card.expanded
        self._render(card)

    def load(self) -> None:
        """Load the pasted answer; close on success, else show why it was not accepted."""
        ok, result = self._load(self.answer.toPlainText())
        if ok:
            self.accept()
            return
        if isinstance(result, str):
            self.error.setText(result)
            self._render(self.cards[FILE_STEP - 1])
            return
        self.error.setText("")
        self._remarks = list(result)
        self._go(REMARKS_STEP)

    def back_to_file(self) -> None:
        """Open step 5 again for the corrected file."""
        self.answer.clear()
        self.error.setText("")
        self._go(FILE_STEP)
