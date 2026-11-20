# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Read-only tables and section labels shared by the tabs."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QModelIndex, QPersistentModelIndex,
                            QSize, Qt, QTime)
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetrics, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QLabel, QPushButton, QStyle, QStyledItemDelegate,
                               QStyleOptionViewItem, QTableWidget, QTableWidgetItem, QWidget)

from measure_twice import i18n
from measure_twice.ui.style import TEXT2

DASH = "—"
ARROW = "→"
CHECK = "✓"
NOTE_ROLE = Qt.ItemDataRole.UserRole + 1  # the grey column of a list row
NOTE_GAP = 24  # pixels between the name and the grey column

translate = QCoreApplication.translate


class CheckButton(QPushButton):
    """A button wide enough for its text in bold when it is checkable.

    The style sheet draws a checked button in bold (``QPushButton:checked``), while the size of
    a button is reckoned from its normal font: the bold text would be cut at the sides.
    """

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt name)
        return self._wider(super().sizeHint())

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt name)
        return self._wider(super().minimumSizeHint())

    def _wider(self, size: QSize) -> QSize:
        if not self.isCheckable():
            return size
        bold = QFont(self.font())
        bold.setWeight(QFont.Weight.DemiBold)
        extra = (QFontMetrics(bold).horizontalAdvance(self.text())
                 - self.fontMetrics().horizontalAdvance(self.text()))
        return QSize(size.width() + max(0, extra), size.height())


def plural(text: str, one: str, many: str, n: int) -> str:
    """The text of a count; English when the language has no translation for it.

    :param text: ``translate(context, one, "", n)``: the translation with ``n`` put in.
    :param one: the English singular source with ``%n``, exactly as given to ``translate``.
    :param many: the English plural with ``%n``, used only when ``text`` is not translated.
    :param n: the count.
    :return: ``text``, or ``many`` with ``n`` for a count other than 1 without translation.
    :rtype: str
    """
    if n != 1 and text == one.replace("%n", str(n)):
        return many.replace("%n", str(n))
    return text


def label(text: str, name: str = "") -> QLabel:
    """A label with a style name: ``title``, ``h2``, ``h3``, ``note`` or ``err``."""
    w = QLabel(text)
    w.setWordWrap(name in ("note", "err"))
    w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if name:
        w.setObjectName(name)
    return w


def project_note(ways: int, updated: str, now: datetime | None = None) -> str:
    """The grey column of a project row: ``6 ways · 18 Nov 14:32``, for a past year ``18 Nov 2025``.

    :param ways: number of ways in the project.
    :param updated: time of the last write, ISO, UTC.
    :param now: the current local time with its zone; the clock when absent.
    :return: the text of the column.
    :rtype: str
    """
    if now is None:
        now = datetime.now().astimezone()
    local = datetime.fromisoformat(updated).astimezone(now.tzinfo)
    # The month name and the order come from the locale of the window language.
    stamp = QDateTime(QDate(local.year, local.month, local.day), QTime(local.hour, local.minute))
    shape = "d MMM HH:mm" if local.year == now.year else "d MMM yyyy"
    when = i18n.locale().toString(stamp, shape)
    count = plural(translate("Project list", "%n way", "", ways), "%n way", "%n ways", ways)
    return f"{count} · {when}"


class NoteDelegate(QStyledItemDelegate):
    """A list row with its text on the left and the grey ``NOTE_ROLE`` text on the right."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        super().paint(painter, option, index)
        note = index.data(NOTE_ROLE)
        if not note:
            return
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(option.palette.highlightedText().color())
        else:
            painter.setPen(QColor(TEXT2))
        rect = option.rect.adjusted(0, 0, -8, 0)
        align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        painter.drawText(rect, align, note)
        painter.restore()

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QSize:
        size = super().sizeHint(option, index)
        note = index.data(NOTE_ROLE)
        if note:
            size.setWidth(size.width() + NOTE_GAP + option.fontMetrics.horizontalAdvance(note))
        return size


def mono():
    """System fixed-width font for numbers."""
    f = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    f.setPixelSize(14)
    return f


def item(text: str, numeric: bool = False) -> QTableWidgetItem:
    """A read-only cell; numbers right-aligned in the fixed-width font."""
    it = QTableWidgetItem(text)
    it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    if numeric:
        it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it.setFont(mono())
    return it


class Table(QTableWidget):
    """A read-only table that takes the height of its rows (the page scrolls, not the table)."""

    def __init__(self, headers: list[str], numeric: set[int] = frozenset(), parent: QWidget | None = None):
        super().__init__(0, len(headers), parent)
        self.numeric = set(numeric)
        self.setHorizontalHeaderLabels(headers)
        for c in self.numeric:
            h = self.horizontalHeaderItem(c)
            h.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.verticalHeader().hide()
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content_width = 0
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.fit()

    def set_rows(self, rows: list[list[str]]) -> None:
        """Replace all rows with texts."""
        self.setSortingEnabled(False)
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, text in enumerate(row):
                self.setItem(r, c, item(text, c in self.numeric))
        self.fit()

    def fit(self) -> None:
        """Size the table to its contents: full height; a horizontal scroll bar when too narrow."""
        hh = self.horizontalHeader()
        hh.setStretchLastSection(False)
        # The header's own size hint ignores the stylesheet's 13px font: measure the header text here.
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setBold(True)
        fm = QFontMetrics(f)
        extra = 16 + (16 if hh.isSortIndicatorShown() else 0)
        for c in range(self.columnCount()):
            head = fm.horizontalAdvance(self.horizontalHeaderItem(c).text()) + extra
            self.setColumnWidth(c, max(self.sizeHintForColumn(c), head))
        self.resizeRowsToContents()
        self._content_width = sum(self.columnWidth(c) for c in range(self.columnCount()))
        hh.setStretchLastSection(True)
        self._fit_height()

    def _fit_height(self) -> None:
        rows = sum(self.rowHeight(r) for r in range(self.rowCount()) if not self.isRowHidden(r))
        h = self.horizontalHeader().sizeHint().height() + rows + 2 * self.frameWidth()
        if self._content_width > self.width() - 2 * self.frameWidth():
            h += self.horizontalScrollBar().sizeHint().height()
        self.setFixedHeight(h)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().resizeEvent(event)
        self._fit_height()

    def texts(self) -> list[str]:
        """All header and cell texts, for tests."""
        out = [self.horizontalHeaderItem(c).text() for c in range(self.columnCount())]
        out += [self.item(r, c).text() for r in range(self.rowCount()) for c in range(self.columnCount())
                if self.item(r, c)]
        return out

