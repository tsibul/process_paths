# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tabs Dictionary (words added, renamed, reordered and deleted in place), and Normalization with
variants (numbers edited in place)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from PySide6.QtCore import QModelIndex, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QStyledItemDelegate, QTableWidgetItem, QVBoxLayout, QWidget)

from procnorm.calc import fmt
from procnorm.project import Project, check_axes
from procnorm.ui import style
from procnorm.ui.tables import ARROW, CHECK, DASH, Table, label

NOT_SET = "not set"
SAVED_NOTE = "Changes are saved at once. To keep the old numbers, copy the project."
RAW = Qt.ItemDataRole.UserRole  # the number as typed into the editor; "" when not set
KEY = Qt.ItemDataRole.UserRole + 1  # name, or (entity, axis) for a skip price


class Page(QScrollArea):
    """A scrolling page of sections laid out top to bottom."""

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        self.box = QVBoxLayout(body)
        self.box.setContentsMargins(16, 20, 16, 20)
        self.box.setSpacing(6)
        self.setWidget(body)

    def columns(self) -> tuple[QVBoxLayout, QVBoxLayout]:
        """Two columns side by side, as ``.cols`` of the mockup."""
        row = QHBoxLayout()
        row.setSpacing(20)
        left, right = QVBoxLayout(), QVBoxLayout()
        for c in (left, right):
            c.setSpacing(6)
            row.addLayout(c, 1)
        self.box.addLayout(row)
        return left, right

    def all_text(self) -> str:
        """Every label and table text of the page, for tests."""
        parts = [w.text() for w in self.widget().findChildren(QLabel)]
        for t in self.widget().findChildren(Table):
            parts += t.texts()
        return "\n".join(parts)


def _end(col: QVBoxLayout) -> None:
    col.addStretch(1)


REMOVE = "✕"
UP, DOWN = "↑", "↓"
BATCH_TAG = "batch scope"
PLACES_SHOWN = 10  # places of a refused deletion listed; the rest are counted
WORD = Qt.ItemDataRole.UserRole + 2  # (what, old) of a dictionary word's cell
HINT = "Double-click a name to rename it."
OPEN, SHUT = "▾", "▸"  # an expanded and a collapsed entity
ARROW_WIDTH = 28  # px of an entity cell that count as the arrow
ADD = Qt.ItemDataRole.UserRole + 3  # (what, owner) of an add row's cell
ADD_TEXTS = {
    "kind": "+ Add kind",
    "named_slice": "+ Add slice",
    "entity": "+ Add entity",
    "axis": "+ Add axis",
    "value": "+ Add value",
    "executor": "+ Add executor",
    "instrument": "+ Add instrument",
    "scope": "+ Add scope",
    "variant_param": "+ Add parameter",
}
NAME_HINTS = {
    "entity": "entity name",
    "axis": "axis name",
    "value": "value",
    "executor": "executor name",
    "instrument": "instrument name",
    "scope": "scope name",
    "variant_param": "parameter name",
}
SPECIAL = "special"  # refusal key of the row with the existence axis and the batch scope
FORM_WORDS = ("kind", "named_slice")  # words added and changed in a form under their row
EDIT = "✎"
START_HINT = ("Start with entities, their axes and values. Then add kinds, executors, instruments "
              "and scopes. Add variants on the Step chains tab.")
ZERO_NOTE = "Zero weight clears the cost of this kind."
CHECK_NOTE = "a check changes the axis it checks; a skipped one is priced"
ROW_NOTE = "A row is either a state (entity, axis, value) or a parameter (parameter, executor)."
GROUP_HINT = "all rows must hold"
ROW_SORT = Qt.ItemDataRole.UserRole + 4  # STATE or PARAM of an item of a slice row's first list
STATE, PARAM = "state", "param"


@dataclass
class WordRow:
    """A row of a dictionary table that holds a word, or a dash when ``what`` is ``None``.

    :param what: one of ``edit.WORDS``; ``None`` for a dash row.
    :param old: the name; ``(entity, axis)`` for an axis, ``(entity, axis, value)`` for a value.
    :param col: the column of the name.
    :param cells: the texts of the row.
    :param up: whether the word can move up in its list.
    :param down: whether the word can move down in its list.
    :param removable: whether the row has ``✕``.
    :param tag: a grey tag in place of ``✕``.
    :param form: whether the row has ``✎``, which opens the form of the word under the row.
    """

    what: str | None
    old: object
    col: int
    cells: list[str]
    up: bool = False
    down: bool = False
    removable: bool = True
    tag: str = ""
    form: bool = False


@dataclass
class AddRow:
    """The last row of a list: a click on it opens the input of a new word.

    :param what: one of ``edit.ADDED_WORDS``.
    :param owner: ``(entity,)`` for an axis, ``(entity, axis)`` for a value, else ``()``.
    :param col: the column of the ``+ Add …`` text.
    :param executors: for a variant parameter of a project with variants: the executors to
        choose from; else ``None``.
    """

    what: str
    owner: tuple[str, ...]
    col: int
    executors: list[str] | None = None


def _edges(index: int, count: int) -> dict[str, bool]:
    """Whether a word at ``index`` of a list of ``count`` words can move up and down."""
    return {"up": index > 0, "down": index < count - 1}


def _icon(text: str, tip: str) -> QPushButton:
    """A small square button of a word row."""
    b = QPushButton(text)
    b.setObjectName("icon")
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


class AddEditor(QWidget):
    """The input of a new word: its name (and the first value of an axis, or the executor of a
    parameter), ``Add`` and ``Esc``. Enter submits, Esc cancels."""

    submitted = Signal()
    cancelled = Signal()

    def __init__(self, what: str, executors: list[str] | None = None) -> None:
        super().__init__()
        self.setObjectName("addEditor")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.setSpacing(8)
        self.name = QLineEdit()
        self.name.setObjectName("addField")
        self.name.setPlaceholderText(NAME_HINTS[what])
        self.name.returnPressed.connect(self.submitted)
        lay.addWidget(self.name)
        self.first: QLineEdit | None = None
        if what == "axis":
            self.first = QLineEdit()
            self.first.setObjectName("addField")
            self.first.setPlaceholderText("first value")
            self.first.returnPressed.connect(self.submitted)
            lay.addWidget(self.first)
        self.executor: QComboBox | None = None
        if executors is not None:
            self.executor = QComboBox()
            self.executor.setObjectName("pick")
            self.executor.setToolTip("Every variant takes this executor for the parameter")
            self.executor.addItems(executors)
            lay.addWidget(self.executor)
        self.add_button = QPushButton("Add")
        self.add_button.setObjectName("small")
        self.add_button.setProperty("primary", True)
        self.add_button.clicked.connect(self.submitted)
        lay.addWidget(self.add_button)
        self.esc_button = QPushButton("Esc")
        self.esc_button.setObjectName("small")
        self.esc_button.setToolTip("Cancel")
        self.esc_button.clicked.connect(self.cancelled)
        lay.addWidget(self.esc_button)
        lay.addStretch(1)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def values(self) -> tuple[str, str | None, str | None]:
        """The typed name, the first value (``None`` when not an axis) and the chosen executor
        (``None`` when not asked)."""
        first = None
        if self.first is not None:
            first = self.first.text()
        executor = None
        if self.executor is not None:
            executor = self.executor.currentText()
        return self.name.text(), first, executor


def _pick(width: int) -> QComboBox:
    """A small list of a form."""
    combo = QComboBox()
    combo.setObjectName("pick")
    combo.setMinimumWidth(width)
    return combo


def _refill(combo: QComboBox, names: list[str]) -> None:
    """Replace the items of a list without signals; the first one is chosen."""
    combo.blockSignals(True)
    combo.clear()
    combo.addItems(names)
    if names:
        combo.setCurrentIndex(0)
    combo.blockSignals(False)


def _choose(combo: QComboBox, name: str) -> None:
    """Choose an item by its text, if the list has it."""
    index = combo.findText(name)
    if index >= 0:
        combo.setCurrentIndex(index)


def _form_label(text: str) -> QLabel:
    w = QLabel(text)
    w.setObjectName("formLabel")
    return w


class _Words:
    """Entities, their axes and the values of an axis, as the lists of a form take them."""

    def __init__(self, model) -> None:
        self.axes: dict[str, list[str]] = {}
        self.values: dict[tuple[str, str], list[str]] = {}
        if model is None:
            return
        for e in model.entities:
            self.axes[e.name] = [a.name for a in e.axes]
            for a in e.axes:
                self.values[(e.name, a.name)] = list(a.values)

    def entities(self) -> list[str]:
        return list(self.axes)

    def axes_of(self, entity: str) -> list[str]:
        return self.axes.get(entity, [])

    def values_of(self, entity: str, axis: str) -> list[str]:
        return self.values.get((entity, axis), [])


class ConditionRow(QWidget):
    """A row of a kind's condition: entity, axis and value lists, and ``✕``. The axis list
    follows the entity, the value list follows the axis."""

    removed = Signal()

    def __init__(self, words: _Words, triple: tuple[str, str, str] | None = None) -> None:
        super().__init__()
        self.words = words
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.entity = _pick(110)
        self.axis = _pick(110)
        self.value = _pick(110)
        for combo in (self.entity, self.axis, self.value):
            lay.addWidget(combo)
        self.remove_button = _icon(REMOVE, "Remove the condition")
        self.remove_button.clicked.connect(self.removed)
        lay.addWidget(self.remove_button)
        lay.addStretch(1)
        _refill(self.entity, words.entities())
        self._entity_changed()
        self.entity.currentIndexChanged.connect(self._entity_changed)
        self.axis.currentIndexChanged.connect(self._axis_changed)
        if triple is not None:
            entity, axis, value = triple
            _choose(self.entity, entity)
            _choose(self.axis, axis)
            _choose(self.value, value)

    def _entity_changed(self) -> None:
        _refill(self.axis, self.words.axes_of(self.entity.currentText()))
        self._axis_changed()

    def _axis_changed(self) -> None:
        values = self.words.values_of(self.entity.currentText(), self.axis.currentText())
        _refill(self.value, values)

    def values(self) -> tuple[str, str, str]:
        """The chosen entity, axis and value."""
        return self.entity.currentText(), self.axis.currentText(), self.value.currentText()


class KindForm(QFrame):
    """The form of a transition kind: name; entity, axis, "from" and "to" lists, each filled by
    the one before; condition rows; ``Check``; ``Zero weight`` with its note; ``Add`` (a new kind)
    or ``Apply`` (a changed kind) and ``Cancel``. Enter in the name submits, Esc cancels;
    ``resized`` is emitted when a condition row comes or goes.

    :param model: the dictionary the lists are filled from.
    :param kind: the kind to change; ``None`` for a new kind.
    """

    submitted = Signal()
    cancelled = Signal()
    resized = Signal()

    def __init__(self, model, kind=None) -> None:
        super().__init__()
        self.setObjectName("kindForm")
        self.words = _Words(model)
        self.adding = kind is None
        self._rows: list[ConditionRow] = []
        grid = QGridLayout(self)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)

        self.name = QLineEdit()
        self.name.setObjectName("addField")
        self.name.setPlaceholderText("kind name")
        self.name.setMinimumWidth(150)
        self.name.returnPressed.connect(self.submitted)
        grid.addWidget(_form_label("Name"), 0, 0)
        grid.addLayout(self._line([self.name]), 0, 1)

        self.entity = _pick(150)
        self.axis = _pick(150)
        grid.addWidget(_form_label("Entity"), 1, 0)
        grid.addLayout(self._line([self.entity, _form_label("Axis"), self.axis]), 1, 1)

        self.source = _pick(150)
        self.target = _pick(150)
        grid.addWidget(_form_label("From"), 2, 0)
        grid.addLayout(self._line([self.source, _form_label("To"), self.target]), 2, 1)

        self.condition_box = QVBoxLayout()
        self.condition_box.setContentsMargins(0, 0, 0, 0)
        self.condition_box.setSpacing(5)
        self.add_condition = QPushButton("+ Add condition")
        self.add_condition.setObjectName("addLink")
        self.add_condition.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_condition.clicked.connect(lambda: self._add_row(None))
        self.condition_box.addWidget(self.add_condition, 0, Qt.AlignmentFlag.AlignLeft)
        condition = _form_label("Condition")
        grid.addWidget(condition, 3, 0, Qt.AlignmentFlag.AlignTop)
        grid.addLayout(self.condition_box, 3, 1)

        self.check = QCheckBox("Check")
        check_note = _form_label(CHECK_NOTE)
        grid.addLayout(self._line([self.check, check_note]), 4, 1)

        self.zero_weight = QCheckBox("Zero weight")
        self.note = QLineEdit()
        self.note.setObjectName("addField")
        self.note.setPlaceholderText("note")
        self.note.setMinimumWidth(240)
        self.note.setEnabled(False)
        self.zero_weight.toggled.connect(self.note.setEnabled)
        grid.addLayout(self._line([self.zero_weight, self.note]), 5, 1)
        self.zero_line = label(ZERO_NOTE, "note")
        grid.addWidget(self.zero_line, 6, 1)

        self.submit_button = QPushButton("Add" if self.adding else "Apply")
        self.submit_button.setObjectName("small")
        self.submit_button.setProperty("primary", True)
        self.submit_button.clicked.connect(self.submitted)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("small")
        self.cancel_button.clicked.connect(self.cancelled)
        grid.addLayout(self._line([self.submit_button, self.cancel_button]), 7, 0, 1, 2)

        _refill(self.entity, self.words.entities())
        self._entity_changed()
        self.entity.currentIndexChanged.connect(self._entity_changed)
        self.axis.currentIndexChanged.connect(self._axis_changed)
        if kind is not None:
            self._fill(kind)

    @staticmethod
    def _line(widgets: list[QWidget]) -> QHBoxLayout:
        """Widgets side by side, left-aligned."""
        lay = QHBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        for w in widgets:
            lay.addWidget(w)
        lay.addStretch(1)
        return lay

    def _fill(self, kind) -> None:
        """Show a kind of the dictionary; its name cannot be changed here."""
        self.name.setText(kind.name)
        self.name.setReadOnly(True)
        self.name.setToolTip("To rename the kind, double-click its name in the table")
        _choose(self.entity, kind.entity)
        _choose(self.axis, kind.axis)
        _choose(self.source, kind.source)
        _choose(self.target, kind.target)
        for triple in kind.requires:
            self._add_row(tuple(triple))
        self.check.setChecked(bool(kind.check))
        self.zero_weight.setChecked(bool(kind.zero_weight))
        self.note.setText(kind.zero_weight_note or "")

    def _entity_changed(self) -> None:
        _refill(self.axis, self.words.axes_of(self.entity.currentText()))
        self._axis_changed()

    def _axis_changed(self) -> None:
        values = self.words.values_of(self.entity.currentText(), self.axis.currentText())
        _refill(self.source, values)
        _refill(self.target, values)
        if len(values) > 1:
            self.target.setCurrentIndex(1)

    def _add_row(self, triple: tuple[str, str, str] | None) -> None:
        row = ConditionRow(self.words, triple)
        row.removed.connect(lambda r=row: self._remove_row(r))
        self.condition_box.insertWidget(len(self._rows), row)
        row.show()
        self._rows.append(row)
        self.resized.emit()

    def _remove_row(self, row: ConditionRow) -> None:
        self._rows.remove(row)
        self.condition_box.removeWidget(row)
        row.hide()
        row.deleteLater()
        self.resized.emit()

    def conditions(self) -> list[ConditionRow]:
        """The condition rows, top to bottom."""
        return list(self._rows)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def structure(self) -> dict:
        """Everything but the name, in the shape ``edit.add_kind`` takes; the note only with
        ``Zero weight``."""
        structure = {
            "entity": self.entity.currentText(),
            "axis": self.axis.currentText(),
            "from": self.source.currentText(),
            "to": self.target.currentText(),
            "requires": [list(row.values()) for row in self._rows],
            "check": self.check.isChecked(),
            "zero_weight": self.zero_weight.isChecked(),
        }
        if self.zero_weight.isChecked():
            structure["zero_weight_note"] = self.note.text()
        return structure


class _SliceWords(_Words):
    """The words of a slice form: entities, axes, values, variant parameters and executors."""

    def __init__(self, model) -> None:
        super().__init__(model)
        self.params: list[str] = []
        self.executors: list[str] = []
        if model is None:
            return
        self.params = list(model.variant_params)
        self.executors = [x.name for x in model.executors]


class SliceRow(QWidget):
    """A row of a slice group: a state (entity, axis and value lists) or a parameter (parameter
    and executor lists), and ``✕``. The first list holds the entities, then the variant
    parameters; a parameter chosen in it makes the row a pair, the axis list goes."""

    removed = Signal()

    def __init__(self, words: _SliceWords, cells: tuple[str, ...] | None = None) -> None:
        super().__init__()
        self.words = words
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.first = _pick(130)
        self.axis = _pick(110)
        self.value = _pick(110)
        lay.addWidget(self.first)
        lay.addWidget(self.axis)
        lay.addWidget(_form_label("="))
        lay.addWidget(self.value)
        self.remove_button = _icon(REMOVE, "Remove the row")
        self.remove_button.clicked.connect(self.removed)
        lay.addWidget(self.remove_button)
        lay.addStretch(1)
        self._fill_first()
        self._first_changed()
        self.first.currentIndexChanged.connect(self._first_changed)
        self.axis.currentIndexChanged.connect(self._axis_changed)
        if cells is not None:
            self._show(cells)

    def _fill_first(self) -> None:
        """Entities, a separator, variant parameters; the first item is chosen."""
        self.first.blockSignals(True)
        self.first.clear()
        for name in self.words.entities():
            self.first.addItem(name, STATE)
        params = self.words.params
        if params and self.first.count():
            self.first.insertSeparator(self.first.count())
        for name in params:
            self.first.addItem(name, PARAM)
        if self.first.count():
            self.first.setCurrentIndex(0)
        self.first.blockSignals(False)

    def _show(self, cells: tuple[str, ...]) -> None:
        sort = PARAM if len(cells) == 2 else STATE
        for i in range(self.first.count()):
            if self.first.itemText(i) == cells[0] and self.first.itemData(i) == sort:
                self.first.setCurrentIndex(i)
                break
        if sort == STATE:
            _choose(self.axis, cells[1])
        _choose(self.value, cells[-1])

    def is_pair(self) -> bool:
        """Whether the row is a parameter (parameter, executor)."""
        return self.first.currentData() == PARAM

    def _first_changed(self) -> None:
        if self.is_pair():
            self.axis.hide()
            _refill(self.axis, [])
            _refill(self.value, self.words.executors)
            return
        self.axis.show()
        _refill(self.axis, self.words.axes_of(self.first.currentText()))
        self._axis_changed()

    def _axis_changed(self) -> None:
        if self.is_pair():
            return
        values = self.words.values_of(self.first.currentText(), self.axis.currentText())
        _refill(self.value, values)

    def values(self) -> tuple[str, ...]:
        """The chosen ``(entity, axis, value)`` or ``(parameter, executor)``."""
        if self.is_pair():
            return self.first.currentText(), self.value.currentText()
        return self.first.currentText(), self.axis.currentText(), self.value.currentText()


class SliceGroupBox(QWidget):
    """A group of a slice form: ``or`` above it (but above the first), a frame with the title,
    ``✕`` of the group, its rows and ``+ Add row``."""

    removed = Signal()
    resized = Signal()

    def __init__(self, words: _SliceWords, rows: list[tuple[str, ...] | None]) -> None:
        super().__init__()
        self.words = words
        self._rows: list[SliceRow] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        self.or_line = QLabel("or")
        self.or_line.setObjectName("orLine")
        outer.addWidget(self.or_line)

        frame = QFrame()
        frame.setObjectName("sliceGroup")
        outer.addWidget(frame)
        box = QVBoxLayout(frame)
        box.setContentsMargins(10, 6, 10, 8)
        box.setSpacing(5)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        self.title = QLabel("")
        self.title.setObjectName("groupTitle")
        head.addWidget(self.title)
        self.hint = _form_label(GROUP_HINT)
        head.addWidget(self.hint)
        head.addStretch(1)
        self.remove_button = _icon(REMOVE, "Remove the group")
        self.remove_button.clicked.connect(self.removed)
        head.addWidget(self.remove_button)
        box.addLayout(head)

        self.row_box = QVBoxLayout()
        self.row_box.setContentsMargins(0, 0, 0, 0)
        self.row_box.setSpacing(5)
        box.addLayout(self.row_box)
        self.add_row = QPushButton("+ Add row")
        self.add_row.setObjectName("addLink")
        self.add_row.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_row.clicked.connect(lambda: self._add_row(None))
        box.addWidget(self.add_row, 0, Qt.AlignmentFlag.AlignLeft)
        for cells in rows:
            self._add_row(cells)

    def set_place(self, index: int) -> None:
        """Title ``Group N`` by the place of the group; ``or`` above all but the first."""
        self.title.setText(f"Group {index + 1}")
        self.or_line.setVisible(index > 0)

    def _add_row(self, cells: tuple[str, ...] | None) -> None:
        row = SliceRow(self.words, cells)
        row.removed.connect(lambda r=row: self._remove_row(r))
        self.row_box.addWidget(row)
        row.show()
        self._rows.append(row)
        self.resized.emit()

    def _remove_row(self, row: SliceRow) -> None:
        self._rows.remove(row)
        self.row_box.removeWidget(row)
        row.hide()
        row.deleteLater()
        self.resized.emit()

    def rows(self) -> list[SliceRow]:
        """The rows of the group, top to bottom."""
        return list(self._rows)


class SliceForm(QFrame):
    """The form of a named slice: name; groups "or", each with rows "and"; ``+ Add group``;
    ``Add`` (a new slice) or ``Apply`` (a changed slice) and ``Cancel``. A new slice starts with
    one group of one row. Enter in the name submits, Esc cancels; ``resized`` is emitted when a
    group or a row comes or goes.

    :param model: the dictionary the lists are filled from.
    :param named: the named slice to change; ``None`` for a new slice.
    """

    submitted = Signal()
    cancelled = Signal()
    resized = Signal()

    def __init__(self, model, named=None) -> None:
        super().__init__()
        self.setObjectName("sliceForm")
        self.words = _SliceWords(model)
        self.adding = named is None
        self._boxes: list[SliceGroupBox] = []
        grid = QGridLayout(self)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)

        self.name = QLineEdit()
        self.name.setObjectName("addField")
        self.name.setPlaceholderText("slice name")
        self.name.setMinimumWidth(150)
        self.name.returnPressed.connect(self.submitted)
        grid.addWidget(_form_label("Name"), 0, 0)
        grid.addLayout(KindForm._line([self.name]), 0, 1)

        self.group_box = QVBoxLayout()
        self.group_box.setContentsMargins(0, 0, 0, 0)
        self.group_box.setSpacing(6)
        grid.addLayout(self.group_box, 1, 0, 1, 2)
        self.add_group = QPushButton("+ Add group")
        self.add_group.setObjectName("addLink")
        self.add_group.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_group.clicked.connect(lambda: self._add_group([None]))
        grid.addWidget(self.add_group, 2, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
        self.row_note = label(ROW_NOTE, "note")
        grid.addWidget(self.row_note, 3, 0, 1, 2)

        self.submit_button = QPushButton("Add" if self.adding else "Apply")
        self.submit_button.setObjectName("small")
        self.submit_button.setProperty("primary", True)
        self.submit_button.clicked.connect(self.submitted)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("small")
        self.cancel_button.clicked.connect(self.cancelled)
        buttons = KindForm._line([self.submit_button, self.cancel_button])
        grid.addLayout(buttons, 4, 0, 1, 2)

        if named is None:
            self._add_group([None])
        else:
            self._fill(named)

    def _fill(self, named) -> None:
        """Show a named slice of the dictionary; its name cannot be changed here."""
        self.name.setText(named.name)
        self.name.setReadOnly(True)
        self.name.setToolTip("To rename the slice, double-click its name in the table")
        for group in named.groups:
            rows = [tuple(s) for s in group.states] + [tuple(p) for p in group.params]
            self._add_group(rows)

    def _add_group(self, rows: list[tuple[str, ...] | None]) -> None:
        """Add a group at the end; ``None`` in ``rows`` is a row of the first items."""
        box = SliceGroupBox(self.words, rows)
        box.removed.connect(lambda b=box: self._remove_group(b))
        box.resized.connect(self.resized)
        self.group_box.addWidget(box)
        box.show()
        self._boxes.append(box)
        self._renumber()
        self.resized.emit()

    def _remove_group(self, box: SliceGroupBox) -> None:
        self._boxes.remove(box)
        self.group_box.removeWidget(box)
        box.hide()
        box.deleteLater()
        self._renumber()
        self.resized.emit()

    def _renumber(self) -> None:
        for i, box in enumerate(self._boxes):
            box.set_place(i)

    def group_boxes(self) -> list[SliceGroupBox]:
        """The groups, top to bottom."""
        return list(self._boxes)

    def groups(self) -> list[list[tuple[str, ...]]]:
        """The groups in the shape ``edit.add_slice`` takes: a list of rows each."""
        return [[row.values() for row in box.rows()] for box in self._boxes]

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class FormCell(QWidget):
    """The cell that holds a form across a whole table row. Its width does not count when the
    table sizes its columns; its height is the form's."""

    def __init__(self, form: QWidget) -> None:
        super().__init__()
        self.form = form
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 4, 10, 8)
        lay.addWidget(form)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt name)
        margins = self.layout().contentsMargins()
        height = self.form.sizeHint().height() + margins.top() + margins.bottom()
        return QSize(0, height)


class WordDelegate(QStyledItemDelegate):
    """Editor of a word's name: a changed name is handed to the table, the cell itself is not
    written (the page refills it after the edit)."""

    def __init__(self, table: WordTable) -> None:
        super().__init__(table)
        self.table = table

    def setEditorData(self, editor: QLineEdit, index: QModelIndex) -> None:  # noqa: N802 (Qt name)
        what, old = index.data(WORD)
        editor.setText(old[-1] if isinstance(old, tuple) else old)

    def setModelData(self, editor: QLineEdit, model, index: QModelIndex) -> None:  # noqa: N802 (Qt name)
        text = editor.text()
        what, old = index.data(WORD)
        if text.strip() == (old[-1] if isinstance(old, tuple) else old):
            return
        # Later: the editor is still closing, the table is refilled after the edit.
        QTimer.singleShot(0, lambda: self.table.edited.emit(what, old, text))


class WordTable(Table):
    """A dictionary table whose word cells are renamed by a double click; each word row ends with
    ``↑ ↓``, which move the word in its list, and ``✕``, which deletes the word. A click on an add
    row opens the input of a new word in that row. A word of ``FORM_WORDS`` is added and changed
    in a form under its row instead: its add row and its ``✎`` emit
    ``form_requested(what, old)``, ``old`` is ``None`` for a new word."""

    edited = Signal(str, object, str)
    removed = Signal(str, object)
    moved = Signal(str, object, int)
    added = Signal(str, object, str, object, object)  # what, owner, name, first value, executor
    add_opened = Signal()
    add_closed = Signal()
    form_requested = Signal(str, object)

    def __init__(self, headers: list[str]) -> None:
        super().__init__(headers + [""])
        self.setItemDelegate(WordDelegate(self))
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                             | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._buttons: dict[tuple[str, object], QPushButton] = {}
        self._arrows: dict[tuple[str, object, int], QPushButton] = {}
        self._tags: dict[tuple[str, object], QLabel] = {}
        self._adds: dict[tuple[str, tuple[str, ...]], tuple[int, AddRow]] = {}
        self._editor: AddEditor | None = None
        self._editor_row = -1
        self._edits: dict[tuple[str, object], QPushButton] = {}
        self._form: QWidget | None = None
        self._form_row = -1
        self.cellClicked.connect(self._clicked)

    def _cells(self, row: WordRow | AddRow) -> list[str]:
        if isinstance(row, WordRow):
            return row.cells + [""]
        cells = [""] * self.columnCount()
        cells[row.col] = ADD_TEXTS[row.what]
        return cells

    def set_words(self, rows: list[WordRow | AddRow]) -> None:
        """Fill the table; an open input of a new word goes.

        :param rows: the word rows, dash rows and add rows, top to bottom.
        """
        self._editor = None
        self._editor_row = -1
        self.close_form()
        self.set_rows([self._cells(row) for row in rows])
        self.clearSelection()
        self._buttons = {}
        self._arrows = {}
        self._edits = {}
        self._tags = {}
        self._adds = {}
        for r, row in enumerate(rows):
            if isinstance(row, AddRow):
                self._set_add_row(r, row)
            elif row.what is not None:
                self._set_word_row(r, row)
        self.fit()

    def _set_add_row(self, r: int, row: AddRow) -> None:
        it = self.item(r, row.col)
        it.setData(ADD, (row.what, row.owner))
        it.setFlags(Qt.ItemFlag.ItemIsEnabled)
        it.setForeground(QBrush(QColor(style.ACCENT)))
        font = QFont(self.font())
        font.setPixelSize(13)
        it.setFont(font)
        self._adds[(row.what, row.owner)] = (r, row)

    def _set_word_row(self, r: int, row: WordRow) -> None:
        what = row.what
        old = row.old
        it = self.item(r, row.col)
        it.setData(WORD, (what, old))
        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
        it.setToolTip("Double-click to rename")
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(2)
        if row.form:
            pencil = _icon(EDIT, "Edit")
            pencil.clicked.connect(
                lambda _=False, w=what, o=old: self.form_requested.emit(w, o)
            )
            lay.addWidget(pencil)
            self._edits[(what, old)] = pencil
        for delta, text, tip, on in ((-1, UP, "Move up", row.up), (1, DOWN, "Move down", row.down)):
            arrow = _icon(text, tip)
            arrow.setEnabled(on)
            arrow.clicked.connect(
                lambda _=False, w=what, o=old, d=delta: self.moved.emit(w, o, d)
            )
            lay.addWidget(arrow)
            self._arrows[(what, old, delta)] = arrow
        if row.removable:
            b = _icon(REMOVE, "Delete")
            b.clicked.connect(lambda _=False, w=what, o=old: self.removed.emit(w, o))
            lay.addWidget(b)
            self._buttons[(what, old)] = b
        if row.tag:
            tag = QLabel(row.tag)
            tag.setObjectName("tag")
            lay.addWidget(tag)
            self._tags[(what, old)] = tag
        lay.addStretch(1)
        self.setCellWidget(r, self.columnCount() - 1, box)

    def word_item(self, what: str, old: object):
        """The name cell of a word; ``None`` when absent."""
        for r in range(self.rowCount()):
            for c in range(self.columnCount()):
                it = self.item(r, c)
                if it is not None and it.data(WORD) == (what, old):
                    return it
        return None

    def remove_button(self, what: str, old: object) -> QPushButton | None:
        """The ``✕`` of a word; ``None`` when absent."""
        return self._buttons.get((what, old))

    def move_button(self, what: str, old: object, delta: int) -> QPushButton | None:
        """The ``↑`` (``delta`` -1) or ``↓`` (+1) of a word; ``None`` when absent."""
        return self._arrows.get((what, old, delta))

    def edit_button(self, what: str, old: object) -> QPushButton | None:
        """The ``✎`` of a word; ``None`` when absent."""
        return self._edits.get((what, old))

    def tag(self, what: str, old: object) -> str:
        """The grey tag of a word's row; empty when none."""
        label_ = self._tags.get((what, old))
        if label_ is None:
            return ""
        return label_.text()

    # --- adding

    def add_item(self, what: str, owner: tuple[str, ...] = ()):
        """The ``+ Add …`` cell of a list; ``None`` when absent."""
        found = self._adds.get((what, tuple(owner)))
        if found is None:
            return None
        r, row = found
        return self.item(r, row.col)

    def open_editor(self) -> AddEditor | None:
        """The open input of a new word; ``None`` when closed."""
        return self._editor

    def _clicked(self, r: int, c: int) -> None:
        it = self.item(r, c)
        if it is None:
            return
        data = it.data(ADD)
        if data is None:
            return
        what, owner = data
        if what in FORM_WORDS:
            self.form_requested.emit(what, None)
            return
        self.open_add(what, owner)

    def open_add(self, what: str, owner: tuple[str, ...] = ()) -> None:
        """Open the input of a new word in its add row, the last cell of the row."""
        self.close_add()
        r, row = self._adds[(what, tuple(owner))]
        editor = AddEditor(what, row.executors)
        editor.submitted.connect(lambda: self._submit(what, row.owner))
        editor.cancelled.connect(self.cancel_add)
        self.setCellWidget(r, self.columnCount() - 1, editor)
        self._editor = editor
        self._editor_row = r
        self.fit()
        self.add_opened.emit()
        editor.name.setFocus()

    def _submit(self, what: str, owner: tuple[str, ...]) -> None:
        name, first, executor = self._editor.values()
        self.added.emit(what, owner, name, first, executor)

    def cancel_add(self) -> None:
        """Close the input of a new word or the open form without a change."""
        if self._editor is None and self._form is None:
            return
        self.close_add()
        self.add_closed.emit()

    def close_add(self) -> None:
        """Close the input of a new word and the form, if open."""
        self.close_form()
        if self._editor is None:
            return
        self.removeCellWidget(self._editor_row, self.columnCount() - 1)
        self._editor = None
        self._editor_row = -1
        self.fit()

    # --- form under a row

    def form(self) -> QWidget | None:
        """The open form; ``None`` when closed."""
        return self._form

    def open_form(self, what: str, old: object, form: QWidget) -> None:
        """Open a form in a new row under the word's row, or under the add row when ``old`` is
        ``None``. Another open input or form of the table goes."""
        self.close_add()
        if old is None:
            r = self._adds[(what, ())][0]
        else:
            r = self.word_item(what, old).row()
        r += 1
        self.insertRow(r)
        for c in range(self.columnCount()):
            blank = QTableWidgetItem("")
            blank.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.setItem(r, c, blank)
        self.setSpan(r, 0, 1, self.columnCount())
        self.setCellWidget(r, 0, FormCell(form))
        self._shift_adds(r, 1)
        self._form = form
        self._form_row = r
        self.fit()
        self.add_opened.emit()

    def refit_form(self) -> None:
        """Take the new height of the open form."""
        if self._form is None:
            return
        cell = self.cellWidget(self._form_row, 0)
        self._form.layout().invalidate()
        cell.layout().invalidate()
        self.fit()

    def close_form(self) -> None:
        """Close the open form, if any, and take its row away."""
        if self._form is None:
            return
        r = self._form_row
        self._form = None
        self._form_row = -1
        self.removeCellWidget(r, 0)
        self.removeRow(r)
        self._shift_adds(r, -1)
        self.fit()

    def _shift_adds(self, row: int, delta: int) -> None:
        """Move the remembered rows of the add rows at ``row`` and below by ``delta``."""
        for key, (r, add) in list(self._adds.items()):
            if r >= row:
                self._adds[key] = (r + delta, add)


class EntityTable(WordTable):
    """The table of entities: an entity row is a header that collapses its axes and values;
    ``toggled(entity)`` is emitted by a click on its arrow or on the empty cells of the row."""

    toggled = Signal(str)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        index = self.indexAt(event.position().toPoint())
        head = self.item(index.row(), 0) if index.isValid() else None
        data = head.data(WORD) if head is not None else None
        if data is not None and data[0] == "entity":
            on_arrow = (index.column() == 0 and
                        event.position().x() - self.visualRect(index).left() < ARROW_WIDTH)
            if on_arrow or index.column() != 0:
                self.toggled.emit(data[1])
                event.accept()
                return
        super().mousePressEvent(event)


class DictionaryPage(Page):
    """Entities, kinds, executors, instruments, scopes, variant parameters, named slices.

    A word is renamed by a double click in its cell and deleted by ``✕`` of its row:
    ``word_edited(what, old, name)`` and ``word_removed(what, old)`` are emitted, the window applies
    the edit and refills the page. A word is added in the last row of its list
    (``word_added(what, name, first value, executor)``) and moved by ``↑ ↓`` of its row
    (``word_moved(what, old, delta)``). The row above the tables sets the existence axis
    (``existence_set(name, absent)``) and the batch scope (``batch_set(scope)``). A kind is added
    and changed in a form under its row (``kind_added(name, structure)``,
    ``kind_set(name, structure)``), and so is a named slice (``slice_added(name, groups)``,
    ``slice_set(name, groups)``).
    """

    word_edited = Signal(str, object, str)
    word_removed = Signal(str, object)
    word_added = Signal(str, object, object, object)
    word_moved = Signal(str, object, int)
    existence_set = Signal(str, str)
    batch_set = Signal(str)
    kind_added = Signal(str, object)
    kind_set = Signal(str, object)
    slice_added = Signal(str, object)
    slice_set = Signal(str, object)

    def __init__(self) -> None:
        super().__init__()
        self._refusals: dict[object, tuple[QLabel, QLabel]] = {}
        self._shown: object | None = None
        self._special_now: tuple[str, str] | None = None
        self._batch_now: str | None = None
        self._model = None
        self.box.addWidget(label("Dictionary", "h2"))
        self._special_row()
        self.amber = label("")
        self.amber.setObjectName("amber")
        self.amber.setWordWrap(True)
        self.amber.hide()
        self.box.addWidget(self.amber)
        self.start_hint = label("", "note")
        self.start_hint.hide()
        self.box.addWidget(self.start_hint)
        self.hint = label(HINT, "note")
        self.box.addWidget(self.hint)
        self._collapsed: set[str] = set()  # entities folded in this session
        self.box.addWidget(label("ENTITY → AXES → VALUES", "h3"))
        self.entities = self._words(self.box, ["Entity", "Axis", "Value", "Inherits from"], EntityTable)
        self.entities.toggled.connect(self.toggle_entity)
        self.box.addWidget(label("TRANSITION KINDS", "h3"))
        self.kinds = self._words(self.box, ["Kind", "Entity", "Axis: from → to", "Condition", "Check",
                                            "Zero weight"])
        left, right = self.columns()
        left.addWidget(label("EXECUTORS", "h3"))
        self.executors = self._words(left, ["Executor"])
        left.addWidget(label("INSTRUMENTS", "h3"))
        self.instruments = self._words(left, ["Instrument"])
        _end(left)
        right.addWidget(label("SCOPES", "h3"))
        self.scopes = self._words(right, ["Scope"])
        right.addWidget(label("VARIANT PARAMETERS", "h3"))
        self.params = self._words(right, ["Parameter"])
        _end(right)
        self.box.addWidget(label("NAMED SLICES", "h3"))
        self.slices = self._words(self.box, ["Slice", "Reached when"])
        self.box.addStretch(1)

    def _special_row(self) -> None:
        """The row with the existence axis, its absent value and the batch scope, and its red
        line."""
        self.special = QFrame()
        self.special.setObjectName("special")
        lay = QHBoxLayout(self.special)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(8)
        lay.addWidget(self._bold("Existence axis:"))
        self.existence_name = QLineEdit()
        self.existence_name.setObjectName("specialField")
        self.existence_name.setMinimumWidth(150)
        self.existence_name.editingFinished.connect(self._existence_entered)
        lay.addWidget(self.existence_name)
        lay.addWidget(self._bold("absent value:"))
        self.absent_value = QLineEdit()
        self.absent_value.setObjectName("specialField")
        self.absent_value.setMinimumWidth(80)
        self.absent_value.editingFinished.connect(self._existence_entered)
        lay.addWidget(self.absent_value)
        lay.addSpacing(24)
        lay.addWidget(self._bold("Batch scope:"))
        self.batch_box = QComboBox()
        self.batch_box.setObjectName("pick")
        self.batch_box.setMinimumWidth(100)
        self.batch_box.activated.connect(self._batch_chosen)
        lay.addWidget(self.batch_box)
        lay.addStretch(1)
        self.box.addWidget(self.special)
        line = label("", "err")
        places = label("")
        for w in (line, places):
            w.hide()
            self.box.addWidget(w)
        self._refusals[SPECIAL] = (line, places)

    @staticmethod
    def _bold(text: str) -> QLabel:
        w = QLabel(text)
        w.setObjectName("specialLabel")
        return w

    def _existence_entered(self) -> None:
        if self._special_now is None:
            return
        typed = (self.existence_name.text(), self.absent_value.text())
        if typed == self._special_now:
            return
        self.existence_set.emit(*typed)

    def _batch_chosen(self, index: int) -> None:
        scope = self.batch_box.itemText(index)
        if self._special_now is None or scope == self._batch_now:
            return
        self.batch_set.emit(scope)

    def _words(self, col: QVBoxLayout, headers: list[str], cls: type[WordTable] = WordTable) -> WordTable:
        t = cls(headers)
        t.edited.connect(self.word_edited)
        t.removed.connect(self.word_removed)
        t.moved.connect(self.word_moved)
        t.added.connect(self._added)
        t.add_opened.connect(lambda table=t: self._close_other_adds(table))
        t.add_closed.connect(self.clear_refusal)
        t.form_requested.connect(lambda what, old, table=t: self._open_form(table, what, old))
        col.addWidget(t)
        line = label("", "err")
        places = label("")
        places.setWordWrap(True)
        for w in (line, places):
            w.hide()
            col.addWidget(w)
        self._refusals[t] = (line, places)
        return t

    def tables(self) -> list[WordTable]:
        """The tables of words, top to bottom."""
        return [self.entities, self.kinds, self.executors, self.instruments, self.scopes, self.params,
                self.slices]

    def table_of(self, what: str) -> WordTable:
        """The table that holds a sort of word (one of ``edit.WORDS``)."""
        return {"entity": self.entities, "axis": self.entities, "value": self.entities,
                "kind": self.kinds, "executor": self.executors, "instrument": self.instruments,
                "scope": self.scopes, "variant_param": self.params,
                "named_slice": self.slices}[what]

    def word_item(self, what: str, old: object):
        """The name cell of a word; ``None`` when there is no such word."""
        return self.table_of(what).word_item(what, old)

    def remove_button(self, what: str, old: object) -> QPushButton | None:
        """The ``✕`` of a word; ``None`` when there is no such word."""
        return self.table_of(what).remove_button(what, old)

    def move_button(self, what: str, old: object, delta: int) -> QPushButton | None:
        """The ``↑`` (``delta`` -1) or ``↓`` (+1) of a word; ``None`` when there is no such word."""
        return self.table_of(what).move_button(what, old, delta)

    def scope_tag(self, scope: str) -> str:
        """The grey tag of a scope's row: ``batch scope`` or empty."""
        return self.scopes.tag("scope", scope)

    # --- adding

    def add_item(self, what: str, owner: tuple[str, ...] = ()):
        """The ``+ Add …`` cell of a list; ``None`` when absent.

        :param owner: ``(entity,)`` for an axis, ``(entity, axis)`` for a value.
        """
        return self.table_of(what).add_item(what, owner)

    def open_editor(self) -> AddEditor | None:
        """The open input of a new word; ``None`` when none is open."""
        for t in self.tables():
            editor = t.open_editor()
            if editor is not None:
                return editor
        return None

    def _close_other_adds(self, table: WordTable) -> None:
        self.clear_refusal()
        for t in self.tables():
            if t is not table:
                t.close_add()

    def _added(self, what: str, owner: tuple, name: str, first: object, executor: object) -> None:
        """Hand a typed word to the window, its name in the shape ``edit.add_word`` takes."""
        if what in ("axis", "value"):
            full = tuple(owner) + (name,)
        else:
            full = name
        self.word_added.emit(what, full, first, executor)

    # --- kind form

    def edit_button(self, what: str, old: object) -> QPushButton | None:
        """The ``✎`` of a word; ``None`` when the word has none."""
        return self.table_of(what).edit_button(what, old)

    def kind_form(self) -> KindForm | None:
        """The open form of a kind; ``None`` when closed."""
        return self.kinds.form()

    def slice_form(self) -> SliceForm | None:
        """The open form of a named slice; ``None`` when closed."""
        return self.slices.form()

    def _open_form(self, table: WordTable, what: str, old: object) -> None:
        """Open the form of a new kind or named slice (``old`` is ``None``) or of an existing
        one."""
        if what == "kind":
            form = self._kind_form(old)
        elif what == "named_slice":
            form = self._slice_form(old)
        else:
            return
        form.cancelled.connect(table.cancel_add)
        form.resized.connect(table.refit_form)
        table.open_form(what, old, form)
        form.name.setFocus()

    def _kind_form(self, old: str | None) -> KindForm:
        kind = None
        if old is not None and self._model is not None:
            kind = next((k for k in self._model.kinds if k.name == old), None)
        form = KindForm(self._model, kind)
        form.submitted.connect(lambda: self._kind_submitted(form, old))
        return form

    def _slice_form(self, old: str | None) -> SliceForm:
        named = None
        if old is not None and self._model is not None:
            named = next((ns for ns in self._model.named_slices if ns.name == old), None)
        form = SliceForm(self._model, named)
        form.submitted.connect(lambda: self._slice_submitted(form, old))
        return form

    def _slice_submitted(self, form: SliceForm, old: str | None) -> None:
        if old is None:
            self.slice_added.emit(form.name.text(), form.groups())
        else:
            self.slice_set.emit(old, form.groups())

    def _kind_submitted(self, form: KindForm, old: str | None) -> None:
        if old is None:
            self.kind_added.emit(form.name.text(), form.structure())
        else:
            self.kind_set.emit(old, form.structure())

    # --- amber line

    def show_amber(self, codes: list[str]) -> None:
        """Show the amber line about the variants that got errors after a dictionary edit;
        an empty list hides it."""
        if not codes:
            self.amber.setText("")
            self.amber.hide()
            return
        if len(codes) == 1:
            count = "1 path has"
        else:
            count = f"{len(codes)} paths have"
        text = (f"{count} errors after this change: {', '.join(codes)}. "
                "Fix them on the Step chains tab.")
        self.amber.setText(text)
        self.amber.show()

    def amber_text(self) -> str:
        """The text of the amber line; empty when hidden."""
        if self.amber.isHidden():
            return ""
        return self.amber.text()

    # --- collapsing

    def toggle_entity(self, name: str) -> None:
        """Collapse an entity to its row, or expand it again."""
        self._collapsed ^= {name}
        self._fold()

    def _fold(self) -> None:
        """Show the arrows and hide the rows of the collapsed entities."""
        t = self.entities
        owner = None
        for r in range(t.rowCount()):
            it = t.item(r, 0)
            data = it.data(WORD)
            if it.data(ADD) is not None:
                owner = None
            if data is not None and data[0] == "entity":
                owner = data[1]
                it.setText(f"{SHUT if owner in self._collapsed else OPEN} {owner}")
            else:
                t.setRowHidden(r, owner in self._collapsed)
        t.fit()

    # --- refusal

    def show_refusal(self, what: str, line: str, places: list[str] = ()) -> None:
        """Show why an edit of a word was refused, under its table: a red line, then the places
        (the first ten and ``and N more``). Other refusals go."""
        self.clear_refusal()
        if what in ("existence_axis", "batch_scope"):
            t = SPECIAL
        else:
            t = self.table_of(what)
        red, rest = self._refusals[t]
        red.setText(line)
        red.show()
        if places:
            shown = list(places[:PLACES_SHOWN])
            if len(places) > PLACES_SHOWN:
                shown.append(f"and {len(places) - PLACES_SHOWN} more")
            rest.setText("\n".join(shown))
            rest.show()
        self._shown = t
        last = rest if places else red
        # Later: the layout has not placed the lines yet.
        QTimer.singleShot(0, lambda: self.ensureWidgetVisible(last))

    def clear_refusal(self) -> None:
        """Hide the refusal."""
        for red, rest in self._refusals.values():
            for w in (red, rest):
                w.hide()
                w.setText("")
        self._shown = None

    def refusal_line(self) -> str:
        """The red line of the shown refusal; empty when none."""
        return self._refusals[self._shown][0].text() if self._shown else ""

    def refusal_places(self) -> list[str]:
        """The listed places of the shown refusal, ``and N more`` included."""
        text = self._refusals[self._shown][1].text() if self._shown else ""
        return text.split("\n") if text else []

    def refusal_text(self) -> str:
        """The red line and the places in one text; empty when none."""
        return "\n".join([self.refusal_line()] + self.refusal_places()) if self._shown else ""

    # --- filling

    def show_project(self, p: Project | None, keep: bool = False) -> None:
        """Fill the page; ``None`` empties it.

        :param keep: after an edit of the same project: keep the scroll place.
        """
        scroll = self.verticalScrollBar().value()
        self.clear_refusal()
        if p is None:
            self._model = None
            self._show_start_hint(False)
            self._show_special(None)
            for t in self.tables():
                t.set_words([])
            return
        m = p.model
        self._model = m
        self._show_start_hint(not m.variants)
        self._show_special(m)
        self.entities.set_words(self._entity_rows(m))
        self._collapsed &= {e.name for e in m.entities}
        self._fold()
        self.entities.setColumnHidden(3, not any(a.inherit for e in m.entities for a in e.axes))
        kinds = [WordRow("kind", k.name, 0, [
            k.name, k.entity, f"{k.axis}: {k.source} {ARROW} {k.target}",
            "; ".join(f"{e}/{a} = {v}" for e, a, v in k.requires),
            CHECK if k.check else "",
            (CHECK + (f" {k.zero_weight_note}" if k.zero_weight_note else "")) if k.zero_weight else ""],
            form=True, **_edges(i, len(m.kinds)))
            for i, k in enumerate(m.kinds)]
        kinds.append(AddRow("kind", (), 0))
        self.kinds.set_words(kinds)
        executors = [x.name for x in m.executors]
        self.executors.set_words(self._list_rows("executor", executors))
        self.instruments.set_words(self._list_rows("instrument", list(m.instruments)))
        self.scopes.set_words(self._scope_rows(m))
        choices = None
        if m.variants:
            choices = executors
        self.params.set_words(self._list_rows("variant_param", list(m.variant_params), choices))
        slices = [WordRow("named_slice", ns.name, 0, [ns.name, " or ".join(
            " and ".join([f"{e}/{a} = {v}" for e, a, v in g.states] + [f"{q} = {x}" for q, x in g.params])
            for g in ns.groups)], form=True, **_edges(i, len(m.named_slices)))
            for i, ns in enumerate(m.named_slices)]
        slices.append(AddRow("named_slice", (), 0))
        self.slices.set_words(slices)
        if keep:
            self.verticalScrollBar().setValue(scroll)


    def _show_start_hint(self, shown: bool) -> None:
        """Show or hide the grey line on where to start in a project without variants."""
        if shown:
            self.start_hint.setText(START_HINT)
            self.start_hint.show()
        else:
            self.start_hint.setText("")
            self.start_hint.hide()

    def _show_special(self, m) -> None:
        """Fill the row of the existence axis and the batch scope; ``None`` empties it."""
        self.batch_box.blockSignals(True)
        self.batch_box.clear()
        if m is None:
            self._special_now = None
            self._batch_now = None
            self.existence_name.setText("")
            self.absent_value.setText("")
        else:
            self._special_now = (m.existence_axis, m.absent_value)
            self._batch_now = m.batch_scope
            self.existence_name.setText(m.existence_axis)
            self.absent_value.setText(m.absent_value)
            self.batch_box.addItems(list(m.scopes))
            self.batch_box.setCurrentText(m.batch_scope)
        self.batch_box.blockSignals(False)
        self.special.setEnabled(m is not None)

    @staticmethod
    def _entity_rows(m) -> list[WordRow | AddRow]:
        """Entities, each with its axes and their values, an add row closing every level."""
        rows: list[WordRow | AddRow] = []
        for i, e in enumerate(m.entities):
            rows.append(WordRow("entity", e.name, 0, [e.name, "", "", ""],
                                **_edges(i, len(m.entities))))
            for j, a in enumerate(e.axes):
                inherits = ", ".join(f"{se}/{sa}" for se, sa in a.inherit)
                rows.append(WordRow("axis", (e.name, a.name), 1, ["", a.name, "", inherits],
                                    **_edges(j, len(e.axes))))
                for k, v in enumerate(a.values):
                    rows.append(WordRow("value", (e.name, a.name, v), 2, ["", "", v, ""],
                                        **_edges(k, len(a.values))))
                rows.append(AddRow("value", (e.name, a.name), 2))
            rows.append(AddRow("axis", (e.name,), 1))
        rows.append(AddRow("entity", (), 0))
        return rows

    @staticmethod
    def _list_rows(what: str, names: list[str], executors: list[str] | None = None
                   ) -> list[WordRow | AddRow]:
        """A flat list of words and its add row."""
        rows: list[WordRow | AddRow] = []
        for i, name in enumerate(names):
            rows.append(WordRow(what, name, 0, [name], **_edges(i, len(names))))
        rows.append(AddRow(what, (), 0, executors))
        return rows

    @staticmethod
    def _scope_rows(m) -> list[WordRow | AddRow]:
        """The scopes: the batch scope is tagged and has no ``✕``."""
        rows: list[WordRow | AddRow] = []
        scopes = list(m.scopes)
        for i, s in enumerate(scopes):
            batch = s == m.batch_scope
            tag = ""
            if batch:
                tag = BATCH_TAG
            rows.append(WordRow("scope", s, 0, [s], removable=not batch, tag=tag,
                                **_edges(i, len(scopes))))
        rows.append(AddRow("scope", (), 0))
        return rows


class NumberDelegate(QStyledItemDelegate):
    """Editor of a number cell: starts from the number itself (empty when not set); a commit is
    handed to the page, the cell itself is not written (the page refills it after the edit)."""

    def __init__(self, table: NumberTable) -> None:
        super().__init__(table)
        self.table = table

    def paint(self, painter, option, index) -> None:
        # The stylesheet's ``::item`` rule drops the cell background: paint it first.
        bg = index.data(Qt.ItemDataRole.BackgroundRole)
        if bg is not None:
            painter.fillRect(option.rect, bg)
        super().paint(painter, option, index)

    def setEditorData(self, editor: QLineEdit, index: QModelIndex) -> None:  # noqa: N802 (Qt name)
        editor.setText(index.data(RAW) or "")

    def setModelData(self, editor: QLineEdit, model, index: QModelIndex) -> None:  # noqa: N802 (Qt name)
        text = editor.text()
        if text.strip() == (index.data(RAW) or ""):
            return
        key = index.data(KEY)
        # Later: the editor is still closing, the table is refilled after the edit.
        QTimer.singleShot(0, lambda: self.table.committed.emit(key, text))


class NumberTable(Table):
    """A table of names and one number column that is edited in place.

    :param name: the normalization table: ``kind_costs``, ``executor_coefficients``,
        ``scope_coefficients`` or ``axis_skip_prices``.
    """

    committed = Signal(object, str)

    def __init__(self, name: str, headers: list[str]) -> None:
        super().__init__(headers, {len(headers) - 1})
        self.name = name
        self.setItemDelegateForColumn(len(headers) - 1, NumberDelegate(self))
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                             | QAbstractItemView.EditTrigger.SelectedClicked
                             | QAbstractItemView.EditTrigger.EditKeyPressed
                             | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_numbers(self, rows: list[tuple[object, list[str], object, bool]]) -> None:
        """Fill the table.

        :param rows: ``(key, name cells, number or None, editable)``; ``None`` is a number not set.
        """
        self.set_rows([names + [NOT_SET if x is None else fmt(x)] for _, names, x, _ in rows])
        self.clearSelection()  # the selection tint would hide the mark of a number not set
        col = self.columnCount() - 1
        for r, (key, _, x, editable) in enumerate(rows):
            for c in range(self.columnCount()):
                self.item(r, c).setData(KEY, key)
            it = self.item(r, col)
            it.setData(RAW, "" if x is None else fmt(x))
            if editable:
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
            if x is None:
                it.setBackground(QBrush(QColor(style.MISSING_BG)))
                it.setForeground(QBrush(QColor(style.WARN)))

    def row_of(self, key: object) -> int:
        """Row of a key; -1 when absent."""
        return next((r for r in range(self.rowCount()) if self.item(r, 0).data(KEY) == key), -1)


class NormPage(Page):
    """Normalization numbers, edited in place, and the list of variants with their calls.

    ``number_edited(table, key, text)`` is emitted when a number cell is committed (Enter or leaving
    the cell); the window applies it and refills the page.
    """

    number_edited = Signal(str, object, str)

    def __init__(self) -> None:
        super().__init__()
        self._project: Project | None = None
        self.box.addWidget(label("Normalization (numbers only)", "h2"))
        self.saved_note = label(SAVED_NOTE, "note")
        self.box.addWidget(self.saved_note)
        self.batch = label("", "note")
        self.box.addWidget(self.batch)
        self.missing_label = label("", "warn")
        self.missing_label.hide()
        self.box.addWidget(self.missing_label)
        self._refusals: dict[str, QLabel] = {}
        left, right = self.columns()
        left.addWidget(label("TRANSITION KINDS — COST", "h3"))
        self.costs = self._numbers(left, "kind_costs", ["Kind", "Cost"])
        left.addWidget(label("SKIP PRICES", "h3"))
        self.prices = self._numbers(left, "axis_skip_prices", ["Entity", "Check axis", "Skip price"])
        _end(left)
        right.addWidget(label("EXECUTOR COEFFICIENTS", "h3"))
        self.exec_coef = self._numbers(right, "executor_coefficients", ["Executor", "×"])
        right.addWidget(label("SCOPE COEFFICIENTS", "h3"))
        self.scope_coef = self._numbers(right, "scope_coefficients", ["Scope", "×"])
        right.addWidget(label("UNCOUNTED ERRORS", "h3"))
        self.errors = Table(["Group", "Error"])
        right.addWidget(self.errors)
        _end(right)
        self.box.addWidget(label("Variants", "h2"))
        self.variants = Table(["Code", "Title", "Side", "Calls", "Out of comparison"], {3})
        self.variants.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.variants.itemSelectionChanged.connect(self._variant_selected)
        self.box.addWidget(self.variants)
        self.calls_title = label("", "h3")
        self.box.addWidget(self.calls_title)
        self.calls = Table(["#", "Kind", "Executor", "Instrument", "Scope"], {0})
        self.box.addWidget(self.calls)
        self.box.addStretch(1)

    def _numbers(self, col: QVBoxLayout, name: str, headers: list[str]) -> NumberTable:
        t = NumberTable(name, headers)
        t.committed.connect(lambda key, text, name=name: self.number_edited.emit(name, key, text))
        col.addWidget(t)
        line = label("", "err")
        line.hide()
        col.addWidget(line)
        self._refusals[name] = line
        return t

    def show_project(self, p: Project | None, keep: bool = False) -> None:
        """Fill the page; ``None`` empties it.

        :param p: the project.
        :param keep: after an edit of the same project: keep the chosen variant and the scroll place.
        """
        chosen = self._chosen_code() if keep else None
        scroll = self.verticalScrollBar().value()
        self._project = p
        self.clear_refusal()
        if p is None:
            self.batch.setText("")
            self.missing_label.hide()
            for t in (self.costs, self.prices, self.exec_coef, self.scope_coef, self.errors, self.variants):
                t.set_rows([])
            self._variant_selected()
            return
        n, m = p.norm, p.model
        self.batch.setText("" if n.batch_size is None else f"Batch size: {fmt(n.batch_size)}")
        self.costs.set_numbers([(k.name, [k.name], Decimal(0) if k.zero_weight and k.name not in n.kind_costs
                                 else n.kind_costs.get(k.name), not k.zero_weight) for k in m.kinds])
        self.prices.set_numbers([((e, a), [e, a], n.skip_prices.get((e, a)), True)
                                 for e, a in check_axes(m)])
        self.exec_coef.set_numbers([(x.name, [x.name], n.executor_coefficients.get(x.name), True)
                                    for x in m.executors])
        self.scope_coef.set_numbers([(s, [s], n.scope_coefficients.get(s), True) for s in m.scopes])
        missing = sum(t.item(r, t.columnCount() - 1).data(RAW) == ""
                      for t in self.number_tables() for r in range(t.rowCount()))
        self.missing_label.setText(f"{missing} {'number' if missing == 1 else 'numbers'} not set")
        self.missing_label.setVisible(missing > 0)
        self.errors.set_rows([[g, t] for g, texts in n.uncounted_errors.items() for t in texts] or [[DASH, ""]])
        self.variants.set_rows([[v.code, v.title, p.sides[v.code], str(len(v.calls)), v.out_of_comparison or ""]
                                for v in m.variants])
        if m.variants:
            self.variants.selectRow(0)
        if chosen is not None:
            self.select_variant(chosen)
        self._variant_selected()
        if keep:
            self.verticalScrollBar().setValue(scroll)

    # --- numbers

    def number_tables(self) -> list[NumberTable]:
        """The four tables of numbers."""
        return [self.costs, self.prices, self.exec_coef, self.scope_coef]

    def number_table(self, name: str) -> NumberTable:
        """The table of numbers by its normalization name, e.g. ``kind_costs``."""
        return next(t for t in self.number_tables() if t.name == name)

    def number_item(self, name: str, key: object):
        """The number cell of a key (a name, or ``(entity, axis)`` for a skip price)."""
        t = self.number_table(name)
        return t.item(t.row_of(key), t.columnCount() - 1)

    def is_missing(self, name: str, key: object) -> bool:
        """Whether the number cell is marked as not set."""
        return self.number_item(name, key).data(RAW) == ""

    def refusal(self, name: str) -> QLabel:
        """The red line under a table of numbers."""
        return self._refusals[name]

    def show_refusal(self, name: str, text: str) -> None:
        """Show why an edit of this table was refused; the other lines go."""
        self.clear_refusal()
        self._refusals[name].setText(text)
        self._refusals[name].show()

    def clear_refusal(self) -> None:
        """Hide the red lines."""
        for line in self._refusals.values():
            line.hide()
            line.setText("")

    def _chosen_code(self) -> str | None:
        rows = self.variants.selectionModel().selectedRows()
        return self.variants.item(rows[0].row(), 0).text() if rows else None

    def select_variant(self, code: str) -> None:
        """Select a variant by code and show its calls."""
        for r in range(self.variants.rowCount()):
            if self.variants.item(r, 0).text() == code:
                self.variants.selectRow(r)
                return

    def _variant_selected(self) -> None:
        rows = self.variants.selectionModel().selectedRows()
        if self._project is None or not rows:
            self.calls_title.setText("")
            self.calls.set_rows([])
            return
        v = self._project.model.variants[rows[0].row()]
        self.calls_title.setText(f"{v.code} · {v.title} — calls")
        self.calls.set_rows([[str(i), c.kind, c.executor, c.instrument, c.scope]
                             for i, c in enumerate(v.calls, 1)])

