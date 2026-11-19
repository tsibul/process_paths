# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""PDF report of the comparison: answer, steps and assumptions pages, A4 landscape.

The report is built in two passes. :func:`pages` lays every page out as plain data: positioned
lines of text and rules, in points, already wrapped to their boxes. :func:`write` draws that list
into a PDF file with ``QPdfWriter`` and ``QPainter``. Only Qt is used.

Fonts are sized in pixels and the writer runs at 72 dots per inch, so a pixel is a point both
when the text is measured and when it is drawn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import QFont, QFontMetricsF, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen

from measure_twice.calc import Comparison, Row, compare, fmt, groups, series
from measure_twice.export import _group_name, _header, _row, number
from measure_twice.project import Project

ANSWER = "answer"
STEPS = "steps"
ASSUMPTIONS = "assumptions"
PAGES = (ANSWER, STEPS, ASSUMPTIONS)
HEADINGS = {ANSWER: "Answer", STEPS: "Steps", ASSUMPTIONS: "Assumptions"}

POINTS_PER_MM = 72 / 25.4
PAGE_WIDTH = 297 * POINTS_PER_MM  # A4 landscape, points
PAGE_HEIGHT = 210 * POINTS_PER_MM
MARGIN = 36  # half an inch on every side, points
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN
BOTTOM = PAGE_HEIGHT - MARGIN
DPI = 72  # one device pixel of the writer is one point

TITLE = 14  # font sizes, points
SECTION = 11
BODY = 9
PAD = 3  # padding of a table cell, points
GAP = 8  # space between blocks, points
COLUMN_GAP = 24  # space between the two ways of a steps page, points
RULE_WIDTH = 0.5

SEP = " · "
SAME_UNIT = "Risk left is in the same unit as labour."
REASON = "Reason: "
EXECUTOR_COEFFICIENTS = "Executor coefficients"
SCOPE_COEFFICIENTS = "Scope coefficients"
SKIP_PRICES = "Skip prices"
WAITING_WEIGHT = "Labour per hour of waiting"


@dataclass
class Text:
    """One line of text in its box, points from the top left corner of the page.

    :ivar x: left edge of the box.
    :ivar y: top edge of the box.
    :ivar width: width of the box; the text fits in it.
    :ivar height: height of the line.
    :ivar text: the line.
    :ivar size: font size.
    :ivar bold: bold font.
    """

    x: float
    y: float
    width: float
    height: float
    text: str
    size: int = BODY
    bold: bool = False


@dataclass
class Rule:
    """A thin horizontal line, points from the top left corner of the page."""

    x1: float
    x2: float
    y: float


@dataclass
class Page:
    """One page of the report.

    :ivar kind: ``"answer"``, ``"steps"`` or ``"assumptions"``.
    :ivar texts: lines of text.
    :ivar rules: thin lines.
    """

    kind: str
    texts: list[Text] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)


def font(size: int, bold: bool = False) -> QFont:
    """The report font of a size.

    :param size: size, points.
    :param bold: bold font.
    :return: the font.
    :rtype: QFont
    """
    f = QFont()
    f.setPixelSize(size)
    f.setBold(bold)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def text_width(text: str, f: QFont) -> float:
    """Width of one line of text, points.

    :param text: the line.
    :param f: the font.
    :return: the width.
    :rtype: float
    """
    return QFontMetricsF(f).horizontalAdvance(text)


def line_height(f: QFont) -> float:
    """Height of one line of text, points."""
    return QFontMetricsF(f).lineSpacing()


def _split_word(word: str, f: QFont, width: float) -> list[str]:
    """A word wider than the box, cut into pieces that fit."""
    out, piece = [], ""
    for ch in word:
        if piece and text_width(piece + ch, f) > width:
            out.append(piece)
            piece = ch
        else:
            piece += ch
    return out + [piece]


def wrap(text: str, f: QFont, width: float) -> list[str]:
    """Lines of a text that fit a width: cut between words, a too long word cut inside.

    :param text: the text; line breaks in it start new lines.
    :param f: the font.
    :param width: width of the box, points.
    :return: the lines; one empty line for an empty text.
    :rtype: list[str]
    """
    out: list[str] = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            candidate = f"{line} {word}" if line else word
            if text_width(candidate, f) <= width:
                line = candidate
                continue
            if line:
                out.append(line)
            pieces = _split_word(word, f, width)
            out += pieces[:-1]
            line = pieces[-1]
        out.append(line)
    return out


def _fit(natural: list[float], width: float) -> list[float]:
    """Column widths: the natural ones when they fit, else the widest ones cut to one cap."""
    if sum(natural) <= width:
        return natural
    rest, count = width, len(natural)
    for w in sorted(natural):
        cap = rest / count
        if w > cap:
            return [min(n, cap) for n in natural]
        rest -= w
        count -= 1
    return natural


class _Flow:
    """Pages of one kind filled from the top down; a new page starts when one is full."""

    def __init__(self, kind: str, heading: str) -> None:
        self.kind = kind
        self.heading = heading
        self.pages: list[Page] = []
        self.y = MARGIN
        self.new_page()

    def new_page(self) -> None:
        """Start a page with the heading on top."""
        self.pages.append(Page(self.kind))
        self.y = MARGIN
        self.lines(self.heading, TITLE, True)
        self.y += GAP

    @property
    def page(self) -> Page:
        return self.pages[-1]

    def room(self, height: float) -> bool:
        """Whether a block of a height fits below the cursor."""
        return self.y + height <= BOTTOM

    def lines(self, text: str, size: int = BODY, bold: bool = False) -> None:
        """A wrapped paragraph over the whole width."""
        f = font(size, bold)
        h = line_height(f)
        for line in wrap(text, f, CONTENT_WIDTH):
            if not self.room(h):
                self.new_page()
            self.page.texts.append(Text(MARGIN, self.y, CONTENT_WIDTH, h, line, size, bold))
            self.y += h

    def table(self, header: list[str], body: list[list[str] | tuple[str, bool]],
              widths: list[float] | None = None, rules: bool = True) -> None:
        """A table; the header is repeated on every page it takes.

        :param header: column names, bold.
        :param body: rows: a list of cells, or ``(text, bold)`` for a line over all columns.
        :param widths: column widths; by default they follow the texts.
        :param rules: thin lines under the header and between rows.
        """
        if widths is None:
            widths = _widths(header, [r for r in body if isinstance(r, list)])
        self._row(header, widths, True, rules)
        for r in body:
            cells = r if isinstance(r, list) else [r[0]]
            bold = False if isinstance(r, list) else r[1]
            row_widths = widths if isinstance(r, list) else [sum(widths)]
            if not self.room(self._height(cells, row_widths, bold)):
                self.new_page()
                self._row(header, widths, True, rules)
            self._row(cells, row_widths, bold, rules)

    def _height(self, cells: list[str], widths: list[float], bold: bool) -> float:
        f = font(BODY, bold)
        count = max(len(wrap(c, f, w - 2 * PAD)) for c, w in zip(cells, widths))
        return count * line_height(f) + 2 * PAD

    def _row(self, cells: list[str], widths: list[float], bold: bool, rules: bool) -> None:
        f = font(BODY, bold)
        h = line_height(f)
        x = MARGIN
        for c, w in zip(cells, widths):
            for i, line in enumerate(wrap(c, f, w - 2 * PAD)):
                if not line:
                    continue
                self.page.texts.append(Text(x + PAD, self.y + PAD + i * h, w - 2 * PAD, h, line,
                                            BODY, bold))
            x += w
        self.y += self._height(cells, widths, bold)
        if rules:
            self.page.rules.append(Rule(MARGIN, MARGIN + sum(widths), self.y))

    def gap(self) -> None:
        """Space between blocks."""
        self.y += GAP


def _widths(header: list[str], body: list[list[str]]) -> list[float]:
    """Column widths of a table that follow its texts and fit the page."""
    head, cell = font(BODY, True), font(BODY)
    natural = []
    for i, name in enumerate(header):
        w = max([text_width(name, head)] + [text_width(r[i], cell) for r in body])
        natural.append(w + 2 * PAD + 1)
    return _fit(natural, CONTENT_WIDTH)


def _heading(project: Project, kind: str) -> str:
    return f"{project.name}{SEP}{HEADINGS[kind]}"


def _chosen_groups(cmp: Comparison, ways: set[str]):
    """The groups of the table with the chosen ways only; empty groups are dropped."""
    out = []
    for g in groups(cmp):
        rows = [r for r in g.rows if r.code in ways]
        if rows:
            out.append((g, rows))
    return out


def _answer(project: Project, cmp: Comparison, ways: set[str]) -> list[Page]:
    flow = _Flow(ANSWER, _heading(project, ANSWER))
    body: list[list[str] | tuple[str, bool]] = []
    for g, rows in _chosen_groups(cmp, ways):
        body.append((_group_name(g), True))
        for r in rows:
            body.append(_row(cmp, r))
            if g.kind == "out" and r.reason:
                body.append((REASON + r.reason, False))
    flow.table(_header(cmp), body)
    return flow.pages


def _way_lines(project: Project, r: Row) -> list[str]:
    """Steps of one way: number, kind and the labour so far in brackets."""
    if r.error is not None:
        return [r.reason or ""]
    return [f"{p.number}. {p.kind} ({number(p.labour)})" for p in series(project, r.code)]


def _steps(project: Project, rows: list[Row]) -> list[Page]:
    half = (CONTENT_WIDTH - COLUMN_GAP) / 2
    widths = [half + COLUMN_GAP, half]
    out = []
    for i in range(0, len(rows), 2):
        pair = rows[i:i + 2]
        header = [f"{r.code}: {r.title}" for r in pair] + [""] * (2 - len(pair))
        columns = [_way_lines(project, r) for r in pair] + [[]] * (2 - len(pair))
        count = max(len(c) for c in columns)
        body = [[c[n] if n < len(c) else "" for c in columns] for n in range(count)]
        flow = _Flow(STEPS, _heading(project, STEPS))
        flow.table(header, body, widths, rules=False)
        out += flow.pages
    return out


def _numbers(items: Iterable[tuple[str, Decimal]]) -> list[list[str]]:
    return [[name, fmt(value)] for name, value in items]


def _assumptions(project: Project, rows: list[Row]) -> list[Page]:
    codes = {r.code for r in rows}
    calls = [c for v in project.model.variants if v.code in codes for c in v.calls]
    executors = {c.executor for c in calls}
    scopes = {c.scope for c in calls}
    norm = project.norm
    flow = _Flow(ASSUMPTIONS, _heading(project, ASSUMPTIONS))
    flow.lines(SAME_UNIT)
    flow.gap()
    flow.lines(EXECUTOR_COEFFICIENTS, SECTION, True)
    flow.table(["Executor", "Coefficient"],
               _numbers((x, k) for x, k in norm.executor_coefficients.items() if x in executors))
    flow.gap()
    flow.lines(SCOPE_COEFFICIENTS, SECTION, True)
    flow.table(["Scope", "Coefficient"],
               _numbers((s, k) for s, k in norm.scope_coefficients.items() if s in scopes))
    flow.gap()
    flow.lines(SKIP_PRICES, SECTION, True)
    flow.table(["Entity", "Check axis", "Skip price"],
               [[e, a, fmt(p)] for (e, a), p in norm.skip_prices.items()])
    flow.gap()
    flow.lines(f"{WAITING_WEIGHT}: {fmt(norm.labour_per_waiting_hour)}")
    return flow.pages


def pages(project: Project, chosen: Iterable[str] = PAGES,
          ways: Iterable[str] | None = None) -> list[Page]:
    """The pages of the report, laid out, in the order answer, steps, assumptions.

    :param project: a checked project.
    :param chosen: the kinds of pages to put in.
    :param ways: codes of the ways to put in, on every page; ``None`` for all.
    :return: the pages.
    :rtype: list[Page]
    """
    cmp = compare(project)
    every = [r for g in groups(cmp) for r in g.rows]
    keep = {r.code for r in every} if ways is None else set(ways)
    rows = [r for r in every if r.code in keep]
    chosen = set(chosen)
    out: list[Page] = []
    if ANSWER in chosen:
        out += _answer(project, cmp, keep)
    if STEPS in chosen:
        out += _steps(project, rows)
    if ASSUMPTIONS in chosen:
        out += _assumptions(project, rows)
    return out


def _draw(painter: QPainter, page: Page) -> None:
    pen = QPen(Qt.GlobalColor.gray)
    pen.setWidthF(RULE_WIDTH)
    painter.setPen(pen)
    for r in page.rules:
        painter.drawLine(r.x1, r.y, r.x2, r.y)
    painter.setPen(Qt.GlobalColor.black)
    for t in page.texts:
        painter.setFont(font(t.size, t.bold))
        box = QRectF(t.x, t.y, t.width, t.height)
        painter.drawText(box, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, t.text)


def draw(laid: list[Page], path: Path, title: str = "") -> None:
    """Draw laid out pages into a PDF file.

    :param laid: the pages from :func:`pages`; at least one.
    :param path: the file to write.
    :param title: document title in the file.
    """
    writer = QPdfWriter(str(path))
    writer.setResolution(DPI)
    writer.setTitle(title)
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4),
                                     QPageLayout.Orientation.Landscape, QMarginsF(0, 0, 0, 0)))
    painter = QPainter(writer)
    try:
        for i, page in enumerate(laid):
            if i:
                writer.newPage()
            _draw(painter, page)
    finally:
        painter.end()


def write(project: Project, path: Path, chosen: Iterable[str] = PAGES,
          ways: Iterable[str] | None = None) -> None:
    """Write the PDF report.

    :param project: a checked project.
    :param path: the file to write.
    :param chosen: the kinds of pages to put in.
    :param ways: codes of the ways to put in, on every page; ``None`` for all.
    :raises ValueError: no page to write.
    """
    laid = pages(project, chosen, ways)
    if not laid:
        raise ValueError("nothing to write: no page chosen")
    draw(laid, Path(path), project.name)
