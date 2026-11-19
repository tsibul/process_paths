# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Step chains tab: the paths by group on the left, the human steps of one path with their transitions.

The header holds the editable code and title and the buttons ``Copy`` and ``Delete``; under them
the side, the task, the reason to keep the path out of comparison and the variant parameters;
under them the folded block ``Entities and initial state``.
``New`` above the path list adds a variant.
Each transition has the buttons ``↑ ↓ ✕ +`` right of ``Scope``; ``+`` opens an input row under it.
Its list ``Kind`` offers the kinds allowed at that place, the others grey with their reason; under
it ``State here`` shows the slice at that place. The tab only asks for an edit
(``edit_requested``); the window applies it and refills the tab."""

from __future__ import annotations

from collections.abc import Callable
from html import escape

from PySide6.QtCore import QT_TRANSLATE_NOOP, QRect, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QPainter, QPen, QStandardItem,
                           QStandardItemModel)
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
                               QRadioButton, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

from measure_twice.calc import (
    Link,
    Row,
    allowed_kinds,
    chain,
    compare,
    empty_steps,
    groups,
    slice_at,
)
from measure_twice.project import Project
from measure_twice.ui import style
from measure_twice.ui.comparison import NO_PAIR, OUT, PAD_X, GroupHeader
from measure_twice.ui.pages import Page
from measure_twice.ui.tables import Table, item, label, mono, plural, translate

LIST_WIDTH = 300  # px, as the mockup's path list
STEP_COL = 32  # step number column, px
RESERVED = 150  # the editing buttons right of Scope, px
SLICE_ROW = 26  # height of a slice marker row, px
INPUT_ROW = 42  # height of the input row of a new transition, px
SLACK = 4  # rounding room so a measured text does not wrap, px
ROW_PAD = 14  # vertical padding and border of a row, px
NO_TRANSITIONS = QT_TRANSLATE_NOOP("ChainsPage", "No transitions")
STEPS_NOT_GIVEN = QT_TRANSLATE_NOOP("ChainsPage", "Steps not given")
SEP = " · "
UP, DOWN, REMOVE, ADD = "↑", "↓", "✕", "+"
TIPS = {
    UP: QT_TRANSLATE_NOOP("ChainsPage", "Move up"),
    DOWN: QT_TRANSLATE_NOOP("ChainsPage", "Move down"),
    REMOVE: QT_TRANSLATE_NOOP("ChainsPage", "Remove"),
    ADD: QT_TRANSLATE_NOOP("ChainsPage", "Add transition below"),
}
FIELDS = ("kind", "executor", "instrument", "scope")
TASK_HINT = QT_TRANSLATE_NOOP("ChainsPage", "variants with the same task are compared")
SIDES = ("own", "other")
FOLD_TITLE = QT_TRANSLATE_NOOP("ChainsPage", "Entities and initial state")
FOLD_NOTE = QT_TRANSLATE_NOOP("ChainsPage", "no box ticked = entities of the transitions")
FOLD_OPEN = "▾"
FOLD_SHUT = "▸"
AS_DICTIONARY = QT_TRANSLATE_NOOP("ChainsPage", "as in dictionary: {}")
NOT_ALLOWED = QT_TRANSLATE_NOOP("ChainsPage", "Not allowed here")
STATE_HERE = QT_TRANSLATE_NOOP("ChainsPage", "State here:")
NO_VALUE = "—"  # an axis of an entity that does not exist, or an empty slice
STATE_GAP = "   "  # between the axes of State here; it wraps only there
KIND_POPUP = 440  # least width of the open list Kind, px, as the mockup
REASON_ROLE = Qt.ItemDataRole.UserRole + 1  # the reason of a kind not allowed here
SEPARATOR_ROLE = Qt.ItemDataRole.UserRole + 2  # the line Not allowed here


NO_EXECUTOR_HINT = QT_TRANSLATE_NOOP(
    "ChainsPage",
    "Add an executor on the Dictionary tab first: "
    "every new path needs one for each variant parameter.",
)


CLEARED_NOTE = QT_TRANSLATE_NOOP("ChainsPage", "Initial-state changes of {} were cleared.")


def new_is_off(p: Project | None) -> bool:
    """Whether a new path cannot be made: variant parameters exist and no executor does."""
    m = p.model if p is not None else None
    if m is None:
        return False
    return bool(m.variant_params) and not m.executors


def _headers() -> list[str]:
    return [
        "",
        "#",
        translate("ChainsPage", "Kind"),
        translate("ChainsPage", "Executor"),
        translate("ChainsPage", "Instrument"),
        translate("ChainsPage", "Scope"),
        "",
    ]


def _transitions(n: int) -> str:
    text = translate("ChainsPage", "%n transition", "", n)
    return plural(text, "%n transition", "%n transitions", n)


def _steps(n: int) -> str:
    return plural(translate("ChainsPage", "%n step", "", n), "%n step", "%n steps", n)


def _slice_text(name: str) -> str:
    return translate("ChainsPage", "slice “{name}” reached").format(name=name)


def _title_html(code: str, title: str) -> str:
    return f"<b>{escape(code)}</b> {escape(title)}"


def _shown_entities(p: Project, v: dict) -> list[str]:
    """Entities of a stored variant in dictionary order: the ticked ones, else those of its
    transitions."""
    m = p.model
    names = set(v.get("entities") or [])
    if not names:
        for c in v.get("calls", []):
            k = m.kind(c[0])
            if k is not None:
                names.add(k.entity)
    return [e.name for e in m.entities if e.name in names]


def _place(p: Project, code: str, after: int) -> tuple[dict[str, str | None], list[str] | None]:
    """The kinds allowed under transition ``after`` of a variant, and ``State here`` there:
    ``entity / axis = value`` in the order of the slice; ``None`` when the run failed before."""
    allowed = allowed_kinds(p, code, after)
    here = slice_at(p, code, after)
    if here is None:
        return allowed, None
    lines = []
    for (entity, axis), value in here.items():
        shown = NO_VALUE if value is None else value
        lines.append(f"{entity} / {axis} = {shown}")
    return allowed, lines


def _clear(layout) -> None:
    """Remove and drop every widget of a layout."""
    while layout.count():
        w = layout.takeAt(0).widget()
        if w is not None:
            w.hide()
            w.deleteLater()


class PathItem(QFrame):
    """One path of the list: code and title; side and transitions; steps without transitions."""

    def __init__(self, row: Row, empty: int, grey: bool, chosen: Callable[[str], None]) -> None:
        super().__init__()
        self.setObjectName("path")
        self.code = row.code
        self.own = row.side == "own"
        self.grey = grey
        self.selected = False
        self._chosen = chosen
        self._plain_title = f"{row.code} {row.title}"
        self.setProperty("own", self.own)
        self.setProperty("grey", grey)
        self.setProperty("cur", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        box = QVBoxLayout(self)
        box.setContentsMargins(10, 6, 10, 6)
        box.setSpacing(1)
        self.title = QLabel(_title_html(row.code, row.title))
        self.title.setObjectName("pathTitle")
        self.title.setWordWrap(True)
        box.addWidget(self.title)
        self.meta = QLabel(f"{style.side_text(row.side)}{SEP}{_transitions(row.steps)}")
        self.meta.setObjectName("groupNote")
        under = QHBoxLayout()
        under.setContentsMargins(0, 0, 0, 0)
        under.addWidget(self.meta, 1)
        self.mark = None
        if row.error:
            self.mark = QLabel(self.tr("error"))
            self.mark.setObjectName("err")
            under.addWidget(self.mark, 0, Qt.AlignmentFlag.AlignRight)
        box.addLayout(under)
        self.warn = None
        if empty:
            self.warn = QLabel(
                plural(
                    self.tr("%n step without transitions", "", empty),
                    "%n step without transitions",
                    "%n steps without transitions",
                    empty,
                )
            )
            self.warn.setObjectName("warn")
            box.addWidget(self.warn)

    def set_selected(self, on: bool) -> None:
        """Highlight the path as chosen."""
        self.selected = on
        self.setProperty("cur", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if event.button() == Qt.MouseButton.LeftButton:
            self._chosen(self.code)
        super().mousePressEvent(event)

    def title_text(self) -> str:
        """``<code> <title>`` without markup."""
        return self._plain_title

    def meta_text(self) -> str:
        """``● Ours`` / ``○ Theirs`` · ``N transitions``."""
        return self.meta.text()

    def error_text(self) -> str | None:
        """``error`` for a path whose run failed; ``None`` otherwise."""
        return self.mark.text() if self.mark is not None else None

    def warn_text(self) -> str | None:
        """``N step(s) without transitions``; ``None`` when every step has transitions."""
        return self.warn.text() if self.warn is not None else None


class SliceMark(QWidget):
    """A dashed accent line across the chain with ``slice “<name>” reached`` on it."""

    def __init__(self, text: str, offset: Callable[[], int]) -> None:
        super().__init__()
        self.text = text
        self._offset = offset
        self.setAutoFillBackground(False)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt name)
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(style.BG))
        accent = QColor(style.ACCENT)
        pen = QPen(accent, 1.5, Qt.PenStyle.DashLine)
        y = self.height() // 2
        p.setPen(pen)
        p.drawLine(10, y, self.width() - 10, y)
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        fm = QFontMetrics(f)
        x = self._offset()
        w = fm.horizontalAdvance(self.text) + 12
        box = QRect(x, 0, w, self.height())
        p.fillRect(box, QColor(style.BG))
        p.setPen(accent)
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, self.text)
        p.end()


class CallButtons(QWidget):
    """The editing buttons of one row: ``↑ ↓ ✕ +`` of a transition, or only ``+`` of an empty step.

    :ivar up: ``↑``, ``None`` on an empty step; likewise ``down`` and ``remove``.
    :ivar add: ``+``.
    """

    def __init__(self, full: bool) -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 0, 6, 0)
        row.setSpacing(4)
        self.up = self.down = self.remove = None
        self._all: list[QPushButton] = []
        for icon in (UP, DOWN, REMOVE, ADD) if full else (ADD,):
            b = QPushButton(icon)
            b.setObjectName("icon")
            b.setToolTip(translate("ChainsPage", TIPS[icon]))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(b)
            self._all.append(b)
        if full:
            self.up, self.down, self.remove, self.add = self._all
        else:
            self.add = self._all[0]
        row.addStretch(1)

    def texts(self) -> list[str]:
        """The icons, left to right."""
        return [b.text() for b in self._all]

    def tips(self) -> list[str]:
        """The tooltips, left to right."""
        return [b.toolTip() for b in self._all]


class KindDelegate(QStyledItemDelegate):
    """Draws the open list ``Kind``: the line ``Not allowed here`` on a panel, and a kind not
    allowed in grey with its reason grey at the right, cut with ``…`` when long."""

    def paint(self, painter, option, index) -> None:
        separator = index.data(SEPARATOR_ROLE)
        reason = index.data(REASON_ROLE)
        if not separator and reason is None:
            super().paint(painter, option, index)
            return
        painter.save()
        box = option.rect.adjusted(10, 0, -10, 0)
        if separator:
            painter.fillRect(option.rect, QColor(style.PANEL))
            f = QFont(option.font)
            f.setPixelSize(12)
            f.setBold(True)
            painter.setFont(f)
            painter.setPen(QColor(style.TEXT2))
            painter.drawText(box, Qt.AlignmentFlag.AlignVCenter, index.data())
            painter.restore()
            return
        grey = QColor(style.NOT_ALLOWED)
        painter.setPen(grey)
        painter.setFont(option.font)
        name = index.data()
        painter.drawText(box, Qt.AlignmentFlag.AlignVCenter, name)
        name_width = QFontMetrics(option.font).horizontalAdvance(name)
        small = QFont(option.font)
        small.setPixelSize(12)
        painter.setFont(small)
        room = box.width() - name_width - 12
        text = QFontMetrics(small).elidedText(reason, Qt.TextElideMode.ElideRight, max(room, 0))
        right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        painter.drawText(box, right, text)
        painter.restore()


class StateHere(QWidget):
    """``State here:`` and the slice at a place, ``entity / axis = value``, in one monospace line
    that wraps between the axes."""

    def __init__(self, lines: list[str]) -> None:
        super().__init__()
        self.lines = list(lines)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 3, 6, 3)
        frame = QFrame()
        frame.setObjectName("stateHere")
        outer.addWidget(frame)
        row = QHBoxLayout(frame)
        row.setContentsMargins(12, 6, 12, 6)
        row.setSpacing(10)
        head = QLabel(translate("ChainsPage", STATE_HERE))
        head.setObjectName("stateHead")
        row.addWidget(head, 0, Qt.AlignmentFlag.AlignTop)
        parts = []
        for line in self.lines:
            parts.append(line.replace(" ", "\u00a0"))  # no break inside one axis
        self.label = QLabel(STATE_GAP.join(parts) or NO_VALUE)
        self.label.setObjectName("stateLines")
        self.label.setFont(mono())
        self.label.setWordWrap(True)
        row.addWidget(self.label, 1)


class InputRow(QWidget):
    """Four lists of a new transition: ``Kind``, ``Executor``, ``Instrument``, ``Scope``.

    ``actions`` holds ``Add`` and ``Cancel``; the table puts it in the buttons column.
    With ``allowed`` the list ``Kind`` has the allowed kinds first, then ``Not allowed here`` and
    the others in grey with their reason; those cannot be chosen.
    """

    def __init__(self, choices: dict[str, list[str]], values: list[str],
                 allowed: dict[str, str | None] | None = None) -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(6)
        self.lists: dict[str, QComboBox] = {}
        self._reasons: dict[str, str] = {}
        for field_, value in zip(FIELDS, values):
            box = QComboBox()
            box.setObjectName("pick")
            if field_ == "kind" and allowed is not None:
                self._fill_kinds(box, allowed, value)
            else:
                names = list(choices.get(field_, []))
                if value not in names:
                    names.append(value)
                box.addItems(names)
                box.setCurrentText(value)
            box.setToolTip(self._field_names()[field_])
            row.addWidget(box, 2 if field_ == "kind" else 1)
            self.lists[field_] = box
        self.actions = QWidget()
        buttons = QHBoxLayout(self.actions)
        buttons.setContentsMargins(6, 0, 6, 0)
        buttons.setSpacing(4)
        self.add_button = QPushButton(self.tr("Add"))
        self.add_button.setObjectName("small")
        self.add_button.setProperty("primary", True)
        self.cancel_button = QPushButton(self.tr("Cancel"))
        self.cancel_button.setObjectName("small")
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)
        self.add_button.setEnabled(bool(self.values()[0]))

    def _field_names(self) -> dict[str, str]:
        return {
            "kind": self.tr("Kind"),
            "executor": self.tr("Executor"),
            "instrument": self.tr("Instrument"),
            "scope": self.tr("Scope"),
        }

    def _fill_kinds(self, box: QComboBox, allowed: dict[str, str | None], value: str) -> None:
        """The allowed kinds, then ``Not allowed here`` and the others greyed with their reason.
        The kind given stays chosen when allowed, else the first allowed one; none when no kind
        is allowed."""
        model = QStandardItemModel(box)
        free = []
        for name, reason in allowed.items():
            if reason is None:
                free.append(name)
                model.appendRow(QStandardItem(name))
            else:
                self._reasons[name] = reason
        if self._reasons:
            line = QStandardItem(translate("ChainsPage", NOT_ALLOWED))
            line.setFlags(Qt.ItemFlag.NoItemFlags)
            line.setData(True, SEPARATOR_ROLE)
            model.appendRow(line)
        for name, reason in self._reasons.items():
            it = QStandardItem(name)
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            it.setToolTip(reason)
            it.setData(reason, REASON_ROLE)
            model.appendRow(it)
        box.setModel(model)
        box.setItemDelegate(KindDelegate(box))
        box.view().setMinimumWidth(KIND_POPUP)
        self._free = free
        if value in free:
            box.setCurrentIndex(free.index(value))
        elif free:
            box.setCurrentIndex(0)
        else:
            box.setCurrentIndex(-1)

    def values(self) -> list[str]:
        """``[kind, executor, instrument, scope]`` as chosen."""
        return [self.lists[f].currentText() for f in FIELDS]

    def choices(self, field_: str) -> list[str]:
        """The names a list offers, ``Not allowed here`` left out."""
        box = self.lists[field_]
        names = []
        for i in range(box.count()):
            if not box.itemData(i, SEPARATOR_ROLE):
                names.append(box.itemText(i))
        return names

    def allowed(self) -> list[str]:
        """The kinds that can be chosen."""
        return [k for k in self.choices("kind") if k not in self._reasons]

    def reasons(self) -> dict[str, str]:
        """``{kind: reason}`` of the kinds not allowed here."""
        return dict(self._reasons)

    def set_value(self, field_: str, name: str) -> None:
        """Choose a name in a list, as the user does: a grey kind cannot be chosen."""
        box = self.lists[field_]
        index = box.findText(name)
        if index < 0:
            return
        if not box.model().flags(box.model().index(index, 0)) & Qt.ItemFlag.ItemIsEnabled:
            return
        box.setCurrentIndex(index)
        if field_ == "kind":
            self.add_button.setEnabled(True)


class ChainTable(Table):
    """Human steps across the table, each followed by its transitions; slice markers between them.

    Columns: step number, ``#``, ``Kind``, ``Executor``, ``Instrument``, ``Scope`` and the editing
    buttons. ``Kind`` takes the rest of the width.

    ``edit(op, args)`` asks for an edit of the shown path: ``("move", (number, ±1))``,
    ``("remove", (number,))``, ``("add", (after, [kind, executor, instrument, scope], step))``.

    ``place(after)`` gives, for the place under transition ``after``, ``{kind: reason or None}``
    and the lines of ``State here`` (``None`` for no slice there); unset, every kind is offered.
    """

    edit = Signal(str, tuple)

    def __init__(self) -> None:
        super().__init__(_headers(), {1})
        self.kinds: list[str] = []
        self.failed: list[int] = []
        self.input: InputRow | None = None
        self.state_label: QLabel | None = None
        self.choices: dict[str, list[str]] = {}
        self.place: Callable[[int], tuple[dict[str, str | None], list[str] | None]] | None = None
        self._links: list[Link] = []
        self._error: tuple[int, str] | None = None
        self.setWordWrap(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def set_chain(self, links: list[Link], error: tuple[int, str] | None = None,
                  adding: tuple[str, int] | None = None) -> None:
        """Replace all rows with the links of one path.

        :param links: the chain.
        :param error: ``(call number, text)`` of a run error: that call is drawn in the error colour,
            bold, and the text goes on the row under it.
        :param adding: where the input row of a new transition is open: ``("call", number)`` under a
            transition, ``("none", link index)`` under an empty step; ``None`` for no input row.
        """
        self.clearSpans()
        self.setRowCount(0)
        self.kinds = []
        self.failed = []
        self.input = None
        self.state_label = None
        self._links, self._error = links, error
        total = sum(len(link.calls) for link in links)
        rows: list[tuple[str, object]] = []
        n = before = 0
        for k, link in enumerate(links):
            step = None if link.text is None else k
            if link.text is not None:
                n += 1
                rows.append(("step", (str(n), link.text)))
            if link.empty or (link.text is None and not link.calls):
                rows.append(("none", (k, before, step)))
                if adding == ("none", k):
                    rows += self._input_rows(self._defaults(before), before, step)
            marks = dict()
            for number, name in link.slices:
                marks.setdefault(number, []).append(name)
            for c in link.calls:
                rows.append(("call", c))
                if adding == ("call", c.number):
                    values = [c.kind, c.executor, c.instrument, c.scope]
                    rows += self._input_rows(values, c.number, None)
                if error is not None and c.number == error[0]:
                    rows.append(("error", error[1]))
                rows += [("slice", name) for name in marks.get(c.number, [])]
            before += len(link.calls)
        self.setRowCount(len(rows))
        step_bg = QColor(style.STEP_BG)
        for r, (kind, data) in enumerate(rows):
            self.kinds.append(kind)
            if kind == "step":
                number, text = data
                for c in range(self.columnCount()):
                    it = item("")
                    it.setBackground(step_bg)
                    self.setItem(r, c, it)
                num = self.item(r, 0)
                num.setText(number)
                num.setForeground(QColor(style.ACCENT))
                f = num.font()
                f.setBold(True)
                num.setFont(f)
                txt = self.item(r, 1)
                txt.setText(text)
                f = txt.font()
                f.setBold(True)
                txt.setFont(f)
                self.setSpan(r, 1, 1, 5)
            elif kind == "none":
                it = item(translate("ChainsPage", NO_TRANSITIONS))
                it.setForeground(QColor(style.TEXT2))
                f = it.font()
                f.setItalic(True)
                it.setFont(f)
                self.setItem(r, 2, it)
                self.setSpan(r, 2, 1, 4)
                k, after, step = data
                b = CallButtons(False)
                b.add.clicked.connect(lambda _=False, k=k: self.open_input(("none", k)))
                self.setCellWidget(r, 6, b)
            elif kind == "input":
                values, after, step, allowed = data
                self.input = InputRow(self.choices, values, allowed)
                self.input.add_button.clicked.connect(
                    lambda _=False, a=after, s=step: self.edit.emit("add", (a, self.input.values(), s)))
                self.input.cancel_button.clicked.connect(lambda: self.open_input(None))
                self.setSpan(r, 1, 1, 5)
                self.setCellWidget(r, 1, self.input)
                self.setCellWidget(r, 6, self.input.actions)
            elif kind == "call":
                bad = error is not None and data.number == error[0]
                if bad:
                    self.failed.append(r)
                for c, text in enumerate([str(data.number), data.kind, data.executor, data.instrument,
                                          data.scope], 1):
                    it = item(text, c in self.numeric)
                    if bad:
                        it.setForeground(QColor(style.ERR))
                        f = it.font()
                        f.setBold(True)
                        it.setFont(f)
                    self.setItem(r, c, it)
                b = CallButtons(True)
                number = data.number
                b.up.setEnabled(number > 1)
                b.down.setEnabled(number < total)
                b.up.clicked.connect(lambda _=False, x=number: self.edit.emit("move", (x, -1)))
                b.down.clicked.connect(lambda _=False, x=number: self.edit.emit("move", (x, 1)))
                b.remove.clicked.connect(lambda _=False, x=number: self.edit.emit("remove", (x,)))
                b.add.clicked.connect(lambda _=False, x=number: self.open_input(("call", x)))
                self.setCellWidget(r, 6, b)
            elif kind == "state":
                state = StateHere(data)
                self.state_label = state.label
                self.setSpan(r, 1, 1, 6)
                self.setCellWidget(r, 1, state)
            elif kind == "error":
                it = item(data)
                it.setForeground(QColor(style.ERR))
                self.setItem(r, 1, it)
                self.setSpan(r, 1, 1, 5)
            else:
                self.setSpan(r, 0, 1, self.columnCount())
                self.setCellWidget(r, 0, SliceMark(_slice_text(data), self._kind_left))
        self.fit()

    def _input_rows(self, values: list[str], after: int, step: int | None) -> list[tuple]:
        """The input row under transition ``after`` and, when there is a slice, ``State here``."""
        allowed, lines = self.place(after) if self.place is not None else (None, None)
        rows: list[tuple] = [("input", (values, after, step, allowed))]
        if lines is not None:
            rows.append(("state", lines))
        return rows

    def _defaults(self, before: int) -> list[str]:
        """Values of a new transition in an empty step: the transition above it, else the one below,
        else the first names of the dictionary."""
        calls = [c for link in self._links for c in link.calls]
        if calls:
            c = calls[before - 1] if before > 0 else calls[0]
            return [c.kind, c.executor, c.instrument, c.scope]
        return [(self.choices.get(f) or [""])[0] for f in FIELDS]

    def open_input(self, adding: tuple[str, int] | None) -> None:
        """Open the input row under a transition or an empty step (closing any other); ``None`` closes it."""
        self.set_chain(self._links, self._error, adding)

    def buttons_at(self, r: int) -> CallButtons | None:
        """The editing buttons of a row; ``None`` for a row without them."""
        w = self.cellWidget(r, self.columnCount() - 1)
        return w if isinstance(w, CallButtons) else None

    def call_row(self, number: int) -> int:
        """Row of the transition with this 1-based number."""
        return next(r for r, kind in enumerate(self.kinds)
                    if kind == "call" and self.item(r, 1).text() == str(number))

    def _kind_left(self) -> int:
        return self.columnWidth(0) + self.columnWidth(1)

    def fit(self) -> None:
        """Columns by the transitions and the labels; ``Kind`` takes the rest; rows by wrapped text."""
        if not hasattr(self, "kinds"):
            return
        self.ensurePolished()  # the stylesheet's font, before the columns are measured
        hh = self.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setMinimumSectionSize(0)
        head = QFont(self.font())
        head.setPixelSize(13)
        head.setBold(True)
        bold = QFont(self.font())
        bold.setBold(True)
        hm, fm, nm, bm = QFontMetrics(head), self.fontMetrics(), QFontMetrics(mono()), QFontMetrics(bold)
        pad = 2 * self._pad() + SLACK
        for c in range(1, 6):
            width = hm.horizontalAdvance(_headers()[c]) + pad
            for r, kind in enumerate(self.kinds):
                it = self.item(r, c)
                if kind == "call" and it is not None:
                    m = nm if c in self.numeric else bm if r in self.failed else fm  # the failed one is bold
                    width = max(width, m.horizontalAdvance(it.text()) + pad)
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(c, width)
        for c, w in ((0, STEP_COL), (6, RESERVED)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(c, w)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._content_width = 0
        self._fit_rows()

    def _pad(self) -> int:
        """Space between a cell's edge and its text: stylesheet padding plus the style's text margin."""
        return PAD_X + self.style().pixelMetric(QStyle.PixelMetric.PM_FocusFrameHMargin, None, self) + 1

    def _fit_rows(self) -> None:
        """Every row tall enough for its wrapped text; slice markers of a fixed height."""
        fm = self.fontMetrics()
        bold = QFont(self.font())
        bold.setBold(True)
        bm = QFontMetrics(bold)
        pad = 2 * self._pad()
        for r, kind in enumerate(self.kinds):
            if kind == "slice":
                self.setRowHeight(r, SLICE_ROW)
                continue
            if kind == "input":
                self.setRowHeight(r, INPUT_ROW)
                continue
            if kind == "state":
                span = sum(self.columnWidth(c) for c in range(1, self.columnCount()))
                w = self.cellWidget(r, 1)
                need = w.heightForWidth(span)
                if need <= 0:
                    need = w.sizeHint().height()
                self.setRowHeight(r, need)
                continue
            need = fm.height()
            for c in range(self.columnCount()):
                it = self.item(r, c)
                if it is None or not it.text():
                    continue
                span = sum(self.columnWidth(c + i) for i in range(self.columnSpan(r, c)))
                m = bm if kind == "step" else fm
                box = QRect(0, 0, max(span - pad, 1), 100000)
                need = max(need, m.boundingRect(box, Qt.TextFlag.TextWordWrap, it.text()).height())
            self.setRowHeight(r, need + ROW_PAD)
        self._fit_height()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().resizeEvent(event)
        self._fit_rows()

    def rows(self) -> list[tuple[str, ...]]:
        """Rows as texts: ``("step", n, text)``, ``("call", #, kind, executor, instrument, scope)``,
        ``("none", "No transitions")``, ``("slice", "slice “<name>” reached")``,
        ``("error", "Error at transition N: …")`` under the failed call, ``("input", kind, executor,
        instrument, scope)`` for the open input row, ``("state", "State here:", line, …)`` under
        it."""
        out: list[tuple[str, ...]] = []
        for r, kind in enumerate(self.kinds):
            if kind == "step":
                out.append(("step", self.item(r, 0).text(), self.item(r, 1).text()))
            elif kind == "none":
                out.append(("none", self.item(r, 2).text()))
            elif kind == "call":
                out.append(("call",) + tuple(self.item(r, c).text() for c in range(1, 6)))
            elif kind == "error":
                out.append(("error", self.item(r, 1).text()))
            elif kind == "input":
                out.append(("input",) + tuple(self.input.values()))
            elif kind == "state":
                head = translate("ChainsPage", STATE_HERE)
                out.append(("state", head) + tuple(self.cellWidget(r, 1).lines))
            else:
                out.append(("slice", self.cellWidget(r, 0).text))
        return out

    def failed_rows(self) -> list[int]:
        """Rows of the failed call: one for a path with a run error, none otherwise."""
        return list(self.failed)

    def state_lines(self) -> list[str]:
        """``entity / axis = value`` of ``State here``; empty when it is not shown."""
        for r, kind in enumerate(self.kinds):
            if kind == "state":
                return list(self.cellWidget(r, 1).lines)
        return []


class ChainsPage(Page):
    """Paths of the current project by group, and the chain of the chosen one.

    ``edit_requested(op, args)`` asks the window for an edit of the chosen path; ``args`` start with
    its code: ``("move", (code, number, ±1))``, ``("remove", (code, number))``,
    ``("add", (code, after, call, step))``, ``("copy", (code,))``, ``("delete", (code,))``,
    ``("rename", (code, new code, title))``, ``("header", (code, field, value))`` with a field of
    :func:`measure_twice.edit.set_variant` (``side``, ``task``, ``out_of_comparison``, ``params``,
    ``entities``, ``initial``).
    ``("new", ())`` asks for a new variant.
    """

    edit_requested = Signal(str, tuple)

    def __init__(self) -> None:
        super().__init__()
        self._project: Project | None = None
        self._rows: dict[str, Row] = {}
        self._items: dict[str, PathItem] = {}
        self._groups: list[tuple[str, bool, list[str]]] = []
        self._current: str | None = None
        self._next_input: tuple[str, tuple[str, int]] | None = None  # (code, place) after Add
        self._cleared: tuple[str, str] | None = None  # (code, line) after an untick cleared changes
        split = QHBoxLayout()
        split.setSpacing(16)
        self.list = QFrame()
        self.list.setObjectName("pathList")
        self.list.setFixedWidth(LIST_WIDTH)
        self.list_box = QVBoxLayout(self.list)
        self.list_box.setContentsMargins(1, 1, 1, 1)
        self.list_box.setSpacing(0)
        self.list_box.addWidget(self._new_row())
        split.addWidget(self.list, 0, Qt.AlignmentFlag.AlignTop)
        right = QVBoxLayout()
        right.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 10, 8)
        head.setSpacing(6)
        self.code_edit = QLineEdit()
        self.code_edit.setObjectName("chainCode")
        self.code_edit.setToolTip(self.tr("Code"))
        self.title_edit = QLineEdit()
        self.title_edit.setObjectName("chainTitle")
        self.title_edit.setToolTip(self.tr("Title"))
        for e in (self.code_edit, self.title_edit):
            e.editingFinished.connect(self._renamed)
        head.addWidget(self.code_edit, 0)
        head.addWidget(self.title_edit, 1)
        self.copy_button = QPushButton(self.tr("Copy"))
        self.copy_button.setObjectName("small")
        self.copy_button.clicked.connect(lambda: self._edit("copy", ()))
        self.delete_button = QPushButton(self.tr("Delete"))
        self.delete_button.setObjectName("small")
        self.delete_button.clicked.connect(lambda: self._edit("delete", ()))
        head.addWidget(self.copy_button, 0)
        head.addWidget(self.delete_button, 0)
        self.meta = QLabel("")
        self.meta.setObjectName("groupNote")
        head.addWidget(self.meta, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        right.addLayout(head)
        right.addWidget(self._header_fields())
        self.table = ChainTable()
        self.table.edit.connect(self._edit)
        right.addWidget(self.table)
        self.refusal = label("", "err")
        self.refusal.setWordWrap(True)
        self.refusal.hide()
        right.addWidget(self.refusal)
        right.addStretch(1)
        split.addLayout(right, 1)
        self.box.addLayout(split)
        self.box.addStretch(1)

    def _new_row(self) -> QWidget:
        """The row of ``New`` at the top of the path list."""
        row = QWidget()
        row.setObjectName("newRow")
        column = QVBoxLayout(row)
        column.setContentsMargins(10, 8, 10, 8)
        column.setSpacing(6)
        line = QHBoxLayout()
        self.new_button = QPushButton(self.tr("New"))
        self.new_button.setObjectName("small")
        self.new_button.setProperty("primary", True)
        self.new_button.setToolTip(self.tr("Add a variant"))
        self.new_button.clicked.connect(lambda: self.edit_requested.emit("new", ()))
        line.addWidget(self.new_button)
        line.addStretch(1)
        column.addLayout(line)
        self.new_hint = label(translate("ChainsPage", NO_EXECUTOR_HINT), "note")
        self.new_hint.hide()
        column.addWidget(self.new_hint)
        return row

    def _show_new_state(self) -> None:
        """``New`` is off, with a hint, while variant parameters have no executor to take."""
        off = new_is_off(self._project)
        self.new_button.setEnabled(not off)
        self.new_hint.setVisible(off)

    def _header_fields(self) -> QWidget:
        """Side, task, out of comparison with its reason, and a list of executors per parameter."""
        self.fields = QWidget()
        self.fields.setObjectName("chainFields")
        rows = QVBoxLayout(self.fields)
        rows.setContentsMargins(4, 0, 10, 10)
        rows.setSpacing(8)

        first = QHBoxLayout()
        first.setSpacing(8)
        first.addWidget(self._field_label(self.tr("Side")))
        self.ours_radio = QRadioButton(style.side_name("own"))
        self.theirs_radio = QRadioButton(style.side_name("other"))
        self.side_group = QButtonGroup(self)
        self.side_group.addButton(self.ours_radio, 0)
        self.side_group.addButton(self.theirs_radio, 1)
        self.side_group.idClicked.connect(self._side_clicked)
        first.addWidget(self.ours_radio)
        first.addWidget(self.theirs_radio)
        first.addSpacing(10)
        first.addWidget(self._field_label(self.tr("Task")))
        self.task_edit = QLineEdit()
        self.task_edit.setPlaceholderText(self.tr("task"))
        self.task_edit.setMinimumWidth(220)
        self.task_edit.editingFinished.connect(self._task_left)
        first.addWidget(self.task_edit)
        self.task_hint = QLabel(translate("ChainsPage", TASK_HINT))
        self.task_hint.setObjectName("note")
        first.addWidget(self.task_hint)
        first.addStretch(1)
        rows.addLayout(first)

        second = QHBoxLayout()
        second.setSpacing(8)
        self.out_check = QCheckBox(self.tr("Out of comparison"))
        self.out_check.clicked.connect(self._out_clicked)
        second.addWidget(self.out_check)
        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText(self.tr("reason"))
        self.reason_edit.setMinimumWidth(220)
        self.reason_edit.editingFinished.connect(self._reason_left)
        second.addWidget(self.reason_edit)
        self.params_line = QHBoxLayout()
        self.params_line.setSpacing(8)
        second.addLayout(self.params_line)
        second.addStretch(1)
        rows.addLayout(second)
        rows.addWidget(self._entities_block())

        self.param_boxes: dict[str, QComboBox] = {}
        self.fields.hide()
        return self.fields

    def _entities_block(self) -> QFrame:
        """The folded block: a tick per entity and a list per axis of the initial state."""
        self.fold = QFrame()
        self.fold.setObjectName("fold")
        box = QVBoxLayout(self.fold)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(8, 4, 10, 4)
        head.setSpacing(10)
        self.fold_button = QPushButton()
        self.fold_button.setObjectName("foldButton")
        self.fold_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fold_button.clicked.connect(self._fold_clicked)
        head.addWidget(self.fold_button)
        self.fold_note = QLabel(translate("ChainsPage", FOLD_NOTE))
        self.fold_note.setObjectName("note")
        head.addWidget(self.fold_note)
        head.addStretch(1)
        box.addLayout(head)

        self.entities_body = QWidget()
        body = QVBoxLayout(self.entities_body)
        body.setContentsMargins(12, 2, 12, 10)
        body.setSpacing(8)
        self.ticks_line = QHBoxLayout()
        self.ticks_line.setSpacing(16)
        body.addLayout(self.ticks_line)
        self.cleared_note = label("", "note")
        self.cleared_note.hide()
        body.addWidget(self.cleared_note)
        self.axes_grid = QGridLayout()
        self.axes_grid.setHorizontalSpacing(10)
        self.axes_grid.setVerticalSpacing(4)
        body.addLayout(self.axes_grid)
        box.addWidget(self.entities_body)

        self.entity_checks: dict[str, QCheckBox] = {}
        self.initial_boxes: dict[tuple[str, str], QComboBox] = {}
        self._fold_open = False
        self._show_fold()
        return self.fold

    def _show_fold(self) -> None:
        mark = FOLD_OPEN if self._fold_open else FOLD_SHUT
        self.fold_button.setText(f"{mark} {translate("ChainsPage", FOLD_TITLE)}")
        self.entities_body.setVisible(self._fold_open)

    def _fold_clicked(self) -> None:
        """Open or fold the block; it stays so for other paths."""
        self._fold_open = not self._fold_open
        self._show_fold()

    @staticmethod
    def _field_label(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("fieldLabel")
        return lab

    # --- filling

    def show_project(self, p: Project | None, keep: bool = False) -> None:
        """Rebuild the list and show the first path; ``None`` empties the tab.

        :param p: the project.
        :param keep: after an edit of the same project: keep the chosen path and the scroll place.
        """
        chosen = self._current if keep else None
        scroll = self.verticalScrollBar().value()
        self._project = p
        while self.list_box.count() > 1:  # the row of New stays
            w = self.list_box.takeAt(1).widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        self._rows, self._items, self._groups, self._current = {}, {}, [], None
        self.clear_refusal()
        m = p.model if p is not None else None
        self.table.choices = {} if m is None else {
            "kind": [k.name for k in m.kinds], "executor": [x.name for x in m.executors],
            "instrument": list(m.instruments), "scope": list(m.scopes)}
        self.list.setVisible(p is not None)
        self._show_new_state()
        if p is not None:
            head = QLabel(self.tr("Paths"))
            head.setObjectName("listHead")
            self.list_box.addWidget(head)
            for g in groups(compare(p)):
                if g.kind == "task":
                    title = translate("ChainsPage", "Task: {task}").format(task=g.task)
                    grey = False
                else:
                    name = NO_PAIR if g.kind == "no-pair" else OUT
                    title = translate("ComparisonPage", name)
                    grey = True
                self.list_box.addWidget(GroupHeader(title, "", None, grey))
                for r in g.rows:
                    self._rows[r.code] = r
                    it = PathItem(r, empty_steps(p, r.code), g.kind == "out", self.select_path)
                    self._items[r.code] = it
                    self.list_box.addWidget(it)
                self._groups.append((title, grey, [r.code for r in g.rows]))
        codes = self.codes()
        self.select_path(chosen if chosen in codes else codes[0] if codes else None)
        if keep:
            self.verticalScrollBar().setValue(scroll)

    def select_path(self, code: str | None) -> None:
        """Show the chain of a path and highlight it in the list; ``None`` shows nothing."""
        if code is not None and code not in self._items:
            return
        self._current = code
        if self._cleared is not None and self._cleared[0] != code:
            self._cleared = None
        for c, it in self._items.items():
            it.set_selected(c == code)
        self._fill_fields(code)
        if code is None:
            self._set_head("", "")
            self.meta.setText("")
            self.table.place = None
            self.table.set_chain([])
            return
        r = self._rows[code]
        steps = self._project.steps.get(code)
        parts = [style.side_text(r.side)]
        if r.task is not None:
            parts.append(translate("ChainsPage", "Task: {task}").format(task=r.task))
        if steps is None:
            parts.append(translate("ChainsPage", STEPS_NOT_GIVEN))
        else:
            parts.append(_steps(len(steps)))
        parts.append(_transitions(r.steps))
        self._set_head(r.code, r.title)
        self.meta.setText(SEP.join(parts))
        project = self._project
        self.table.place = lambda after: _place(project, code, after)
        adding = None
        if self._next_input is not None and self._next_input[0] == code:
            adding = self._next_input[1]
        error = (r.error[0], r.reason) if r.error else None
        self.table.set_chain(chain(self._project, code), error, adding)

    # --- editing

    def _edit(self, op: str, args: tuple) -> None:
        """Ask for an edit of the chosen path; after an accepted ``add`` the input row opens under
        the new transition."""
        if self._current is None:
            return
        if op == "add":
            self._next_input = (self._current, ("call", args[0] + 1))
        try:
            self.edit_requested.emit(op, (self._current,) + tuple(args))
        finally:
            self._next_input = None

    def _set_head(self, code: str, title: str) -> None:
        for e, text in ((self.code_edit, code), (self.title_edit, title)):
            e.setText(text)
            e.setCursorPosition(0)
        bold = QFont(self.code_edit.font())
        bold.setBold(True)
        self.code_edit.setFixedWidth(QFontMetrics(bold).horizontalAdvance(code) + 28)
        for b in (self.copy_button, self.delete_button):
            b.setEnabled(bool(code))

    def _renamed(self) -> None:
        """Code or title left by the user: ask for a rename if either changed."""
        r = self._rows.get(self._current) if self._current else None
        if r is None:
            return
        code, title = self.code_edit.text().strip(), self.title_edit.text().strip()
        if (code, title) != (r.code, r.title):
            self.edit_requested.emit("rename", (r.code, code, title))

    def _stored(self, code: str | None) -> dict | None:
        """The variant as stored in the project file; ``None`` for no path."""
        if code is None or self._project is None:
            return None
        variants = self._project.data.get("variants", [])
        return next((v for v in variants if v.get("code") == code), None)

    def _fill_fields(self, code: str | None) -> None:
        """Put the stored header of a path into the fields; hide them for no path."""
        v = self._stored(code)
        if v is None:
            self.fields.hide()
            return
        self.fields.show()
        side = v.get("side", "own")
        self.ours_radio.setChecked(side == "own")
        self.theirs_radio.setChecked(side == "other")
        task = v.get("task") or ""
        self.task_edit.setText(task)
        self.task_edit.setCursorPosition(0)
        self.task_hint.setVisible(not task)
        reason = v.get("out_of_comparison") or ""
        self.out_check.setChecked(bool(reason))
        self.reason_edit.setText(reason)
        self.reason_edit.setEnabled(bool(reason))
        self._fill_params(v.get("params") or {})
        self._fill_entities(v)

    def _fill_params(self, params: dict) -> None:
        """A label and a list of executors for every variant parameter of the project."""
        while self.params_line.count():
            w = self.params_line.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        self.param_boxes = {}
        m = self._project.model
        executors = [x.name for x in m.executors]
        names = self._project.data.get("variant_params", [])
        for k, name in enumerate(names):
            if k == 0:
                self.params_line.addSpacing(10)
            self.params_line.addWidget(self._field_label(name))
            box = QComboBox()
            box.setObjectName("pick")
            box.addItems(executors)
            box.setCurrentIndex(box.findText(params.get(name, "")))
            box.activated.connect(lambda _=0, n=name: self._param_chosen(n))
            self.params_line.addWidget(box)
            self.param_boxes[name] = box

    def _fill_entities(self, v: dict) -> None:
        """Ticks of the stored entities; a list per axis of the entities the path has, with the
        stored deviation chosen or ``as in dictionary: <first value>``."""
        _clear(self.ticks_line)
        _clear(self.axes_grid)
        self.entity_checks = {}
        self.initial_boxes = {}
        shown = self._cleared is not None and self._cleared[0] == self._current
        self.cleared_note.setText(self._cleared[1] if shown else "")
        self.cleared_note.setVisible(shown)
        m = self._project.model
        ticked = set(v.get("entities") or [])
        for e in m.entities:
            check = QCheckBox(e.name)
            check.setChecked(e.name in ticked)
            check.clicked.connect(self._entity_clicked)
            self.ticks_line.addWidget(check)
            self.entity_checks[e.name] = check
        self.ticks_line.addStretch(1)
        initial = v.get("initial") or {}
        row = 0
        for name in _shown_entities(self._project, v):
            for ax in m.entity(name).axes:
                lab = QLabel(f"{name} / {ax.name}")
                lab.setObjectName("note")
                self.axes_grid.addWidget(lab, row, 0)
                box = QComboBox()
                box.setObjectName("pick")
                box.addItem(translate("ChainsPage", AS_DICTIONARY).format(ax.values[0]))
                box.addItems(list(ax.values))
                value = initial.get(name, {}).get(ax.name)
                index = box.findText(value) if value is not None else 0
                box.setCurrentIndex(max(index, 0))
                box.activated.connect(
                    lambda _=0, e=name, a=ax.name: self._initial_chosen(e, a))
                self.axes_grid.addWidget(box, row, 1, Qt.AlignmentFlag.AlignLeft)
                self.initial_boxes[(name, ax.name)] = box
                row += 1
        self.axes_grid.setColumnStretch(2, 1)

    def _entity_clicked(self) -> None:
        """The ticked entities, in dictionary order; none ticked removes ``entities``."""
        v = self._stored(self._current)
        if v is None:
            return
        self._cleared = None
        names = []
        for name, check in self.entity_checks.items():
            if check.isChecked():
                names.append(name)
        stored_names = list(v.get("entities") or [])
        if names == stored_names:
            return
        stored = v.get("initial") or {}
        initial = {}
        unticked = []
        for name in stored_names:
            if name not in names:
                unticked.append(name)
        for name, axes in stored.items():
            if name not in unticked:
                initial[name] = axes
        cleared = [name for name in unticked if name in stored]
        if cleared:
            note = translate("ChainsPage", CLEARED_NOTE).format(", ".join(cleared))
            self._cleared = (self._current, note)
            self.edit_requested.emit(
                "variant", (self._current, {"entities": names, "initial": initial}))
        else:
            self._header("entities", names)

    def _initial_chosen(self, entity: str, axis: str) -> None:
        """A value deviates the initial state; ``as in dictionary`` removes the deviation."""
        v = self._stored(self._current)
        if v is None:
            return
        self._cleared = None
        stored = v.get("initial") or {}
        initial = {}
        for name, axes in stored.items():
            initial[name] = dict(axes)
        axes = initial.setdefault(entity, {})
        box = self.initial_boxes[(entity, axis)]
        if box.currentIndex() == 0:
            axes.pop(axis, None)
        else:
            axes[axis] = box.currentText()
        if not axes:
            initial.pop(entity)
        if initial != stored:
            self._header("initial", initial)

    def _header(self, field_: str, value) -> None:
        if self._current is not None:
            self.edit_requested.emit("header", (self._current, field_, value))

    def _side_clicked(self, index: int) -> None:
        v = self._stored(self._current)
        if v is not None and v.get("side") != SIDES[index]:
            self._header("side", SIDES[index])

    def _task_left(self) -> None:
        v = self._stored(self._current)
        task = self.task_edit.text().strip()
        if v is not None and task != (v.get("task") or ""):
            self._header("task", task)

    def _out_clicked(self, checked: bool) -> None:
        """A tick only opens the reason; the path leaves comparison once a reason is typed.
        Taking the tick off brings the path back."""
        v = self._stored(self._current)
        if v is None:
            return
        self.reason_edit.setEnabled(checked)
        if checked:
            self.reason_edit.setFocus()
            return
        self.reason_edit.setText("")
        if v.get("out_of_comparison"):
            self._header("out_of_comparison", "")

    def _reason_left(self) -> None:
        v = self._stored(self._current)
        if v is None or not self.out_check.isChecked():
            return
        reason = self.reason_edit.text().strip()
        if reason != (v.get("out_of_comparison") or ""):
            self._header("out_of_comparison", reason)

    def _param_chosen(self, name: str) -> None:
        v = self._stored(self._current)
        if v is None:
            return
        params = dict(v.get("params") or {})
        params[name] = self.param_boxes[name].currentText()
        self._header("params", params)

    def choose_next(self, code: str | None) -> None:
        """Name the path to show after the next ``show_project(keep=True)``; unknown codes are ignored."""
        self._current = code

    def show_refusal(self, text: str) -> None:
        """Show under the chain why an edit was refused, and give the header its stored texts back."""
        self._cleared = None
        r = self._rows.get(self._current) if self._current else None
        if r is not None:
            self._set_head(r.code, r.title)
            self._fill_fields(r.code)
        self.refusal.setText(text)
        self.refusal.show()

    def clear_refusal(self) -> None:
        """Hide the red line."""
        self.refusal.hide()
        self.refusal.setText("")

    # --- reading, for tests and other parts of the window

    def codes(self) -> list[str]:
        """Codes of the paths, top to bottom."""
        return [c for _, _, codes in self._groups for c in codes]

    def groups(self) -> list[tuple[str, bool, list[str]]]:
        """Groups of the list: header text, grey, codes."""
        return [(t, g, list(c)) for t, g, c in self._groups]

    def path(self, code: str) -> PathItem:
        """Row of a path in the list."""
        return self._items[code]

    def current_code(self) -> str | None:
        """Code of the chosen path."""
        return self._current

    def head_title(self) -> str:
        """``<code> <title>`` of the chosen path as stored, without markup."""
        r = self._rows.get(self._current) if self._current else None
        return f"{r.code} {r.title}" if r else ""

    def head_meta(self) -> str:
        """Side · ``Task: <task>`` · ``N steps`` or ``Steps not given`` · ``M transitions``."""
        return self.meta.text()

    def rows(self) -> list[tuple[str, ...]]:
        """Rows of the chain as texts."""
        return self.table.rows()

    def row_kinds(self) -> list[str]:
        """``step``, ``call``, ``none``, ``slice``, ``error`` or ``input`` for every row of the chain."""
        return list(self.table.kinds)
