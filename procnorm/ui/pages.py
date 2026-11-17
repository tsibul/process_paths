# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tabs Dictionary (words renamed and deleted in place), and Normalization with variants (numbers
edited in place)."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import QModelIndex, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QStyledItemDelegate, QVBoxLayout, QWidget)

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
ADD_NOTE = "To add words, load a new file."
PLACES_SHOWN = 10  # places of a refused deletion listed; the rest are counted
WORD = Qt.ItemDataRole.UserRole + 2  # (what, old) of a dictionary word's cell


class WordDelegate(QStyledItemDelegate):
    """Editor of a word's name: a changed name is handed to the table, the cell itself is not
    written (the page refills it after the edit)."""

    def __init__(self, table: WordTable) -> None:
        super().__init__(table)
        self.table = table

    def setModelData(self, editor: QLineEdit, model, index: QModelIndex) -> None:  # noqa: N802 (Qt name)
        text = editor.text()
        if text.strip() == index.data(Qt.ItemDataRole.DisplayRole):
            return
        what, old = index.data(WORD)
        # Later: the editor is still closing, the table is refilled after the edit.
        QTimer.singleShot(0, lambda: self.table.edited.emit(what, old, text))


class WordTable(Table):
    """A dictionary table whose word cells are renamed by a double click; each word row ends with
    ``✕``, which deletes the word."""

    edited = Signal(str, object, str)
    removed = Signal(str, object)

    def __init__(self, headers: list[str]) -> None:
        super().__init__(headers + [""])
        self.setItemDelegate(WordDelegate(self))
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                             | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._buttons: dict[tuple[str, object], QPushButton] = {}

    def set_words(self, rows: list[tuple[str | None, object, int, list[str]]]) -> None:
        """Fill the table.

        :param rows: ``(what, old, column of the name, cells)``; ``what`` is ``None`` for a row
            without a word (a dash).
        """
        self.set_rows([cells + [""] for _, _, _, cells in rows])
        self.clearSelection()
        self._buttons = {}
        last = self.columnCount() - 1
        for r, (what, old, col, _) in enumerate(rows):
            if what is None:
                continue
            it = self.item(r, col)
            it.setData(WORD, (what, old))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
            it.setToolTip("Double-click to rename")
            box = QWidget()
            lay = QHBoxLayout(box)
            lay.setContentsMargins(6, 0, 6, 0)
            b = QPushButton(REMOVE)
            b.setObjectName("icon")
            b.setToolTip("Delete")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, w=what, o=old: self.removed.emit(w, o))
            lay.addWidget(b)
            lay.addStretch(1)
            self.setCellWidget(r, last, box)
            self._buttons[(what, old)] = b
        self.fit()

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


class DictionaryPage(Page):
    """Entities, kinds, executors, instruments, scopes, variant parameters, named slices.

    A word is renamed by a double click in its cell and deleted by ``✕`` of its row:
    ``word_edited(what, old, name)`` and ``word_removed(what, old)`` are emitted, the window applies
    the edit and refills the page. Words are added only by loading a new file.
    """

    word_edited = Signal(str, object, str)
    word_removed = Signal(str, object)

    def __init__(self) -> None:
        super().__init__()
        self._refusals: dict[WordTable, tuple[QLabel, QLabel]] = {}
        self._shown: WordTable | None = None
        self.box.addWidget(label("Dictionary", "h2"))
        self.info = label("", "note")
        self.box.addWidget(self.info)
        self.add_note = label(ADD_NOTE, "note")
        self.box.addWidget(self.add_note)
        self.box.addWidget(label("ENTITY → AXES → VALUES", "h3"))
        self.entities = self._words(self.box, ["Entity", "Axis", "Value", "Inherits from"])
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
        self.scopes = self._words(right, ["Scope", "Batch"])
        right.addWidget(label("VARIANT PARAMETERS", "h3"))
        self.params = self._words(right, ["Parameter"])
        _end(right)
        self.box.addWidget(label("NAMED SLICES", "h3"))
        self.slices = self._words(self.box, ["Slice", "Reached when"])
        self.box.addStretch(1)

    def _words(self, col: QVBoxLayout, headers: list[str]) -> WordTable:
        t = WordTable(headers)
        t.edited.connect(self.word_edited)
        t.removed.connect(self.word_removed)
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

    # --- refusal

    def show_refusal(self, what: str, line: str, places: list[str] = ()) -> None:
        """Show why an edit of a word was refused, under its table: a red line, then the places
        (the first ten and ``and N more``). Other refusals go."""
        self.clear_refusal()
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
            self.info.setText("")
            for t in self.tables():
                t.set_words([])
            return
        m = p.model
        self.info.setText(f"Existence axis: {m.existence_axis} (absent: {m.absent_value}). "
                          f"Batch scope: {m.batch_scope}.")
        rows = []
        for e in m.entities:
            rows.append(("entity", e.name, 0, [e.name, "", "", ""]))
            for a in e.axes:
                rows.append(("axis", (e.name, a.name), 1,
                             ["", a.name, "", ", ".join(f"{se}/{sa}" for se, sa in a.inherit)]))
                rows += [("value", (e.name, a.name, v), 2, ["", "", v, ""]) for v in a.values]
        self.entities.set_words(rows)
        self.kinds.set_words([("kind", k.name, 0, [
            k.name, k.entity, f"{k.axis}: {k.source} {ARROW} {k.target}",
            "; ".join(f"{e}/{a} = {v}" for e, a, v in k.requires),
            CHECK if k.check else "",
            (CHECK + (f" {k.zero_weight_note}" if k.zero_weight_note else "")) if k.zero_weight else ""])
            for k in m.kinds])
        self.executors.set_words([("executor", x.name, 0, [x.name]) for x in m.executors])
        self.instruments.set_words([("instrument", x, 0, [x]) for x in m.instruments])
        self.scopes.set_words([("scope", s, 0, [s, CHECK if s == m.batch_scope else ""]) for s in m.scopes])
        self.params.set_words([("variant_param", x, 0, [x]) for x in m.variant_params]
                              or [(None, None, 0, [DASH])])
        self.slices.set_words([("named_slice", ns.name, 0, [ns.name, " or ".join(
            " and ".join([f"{e}/{a} = {v}" for e, a, v in g.states] + [f"{q} = {x}" for q, x in g.params])
            for g in ns.groups)]) for ns in m.named_slices] or [(None, None, 0, [DASH, ""])])
        if keep:
            self.verticalScrollBar().setValue(scroll)


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

