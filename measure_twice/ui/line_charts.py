# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Line charts of the comparison: labour, labour with waiting, and price of checks done, by step."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCharts import QChart, QChartView, QLegend, QLineSeries, QValueAxis
from PySide6.QtCore import (QT_TRANSLATE_NOOP, QCoreApplication, QMargins, QRectF, QSizeF, Qt,
                            Signal)
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from measure_twice.calc import Point, Row, series, start_point
from measure_twice.project import Project
from measure_twice.ui import style

HEIGHT = 260  # least height of a chart, pixels
LEGEND_ITEM_MARGIN = 4  # Qt puts this margin above and below a legend entry, pixels
LEGEND_PAD = 10  # room Qt leaves above the first legend entry and below the last, pixels

LABOUR = "labour"
LABOUR_WAITING = "labour_waiting"
CHECKS = "checks"
# kind of chart: title, title of the value axis, value of a point
CHARTS: dict[str, tuple[str, str, Callable[[Point], object]]] = {
    LABOUR: (
        QT_TRANSLATE_NOOP("LineCharts", "Labour by step"),
        QT_TRANSLATE_NOOP("LineCharts", "Labour"),
        lambda p: p.labour,
    ),
    LABOUR_WAITING: (
        QT_TRANSLATE_NOOP("LineCharts", "Labour + waiting by step"),
        QT_TRANSLATE_NOOP("LineCharts", "Labour + waiting"),
        lambda p: p.labour_waiting,
    ),
    CHECKS: (
        QT_TRANSLATE_NOOP("LineCharts", "Checks done by step"),
        QT_TRANSLATE_NOOP("LineCharts", "Price of checks done"),
        lambda p: p.done_total,
    ),
}


def titles(kind: str) -> tuple[str, str]:
    """The title of a chart and the title of its value axis, in the language of the window."""
    title, y_title, _ = CHARTS[kind]
    translate = QCoreApplication.translate
    return translate("LineCharts", title), translate("LineCharts", y_title)


def drawn(rows: Sequence[Row]) -> list[Row]:
    """The rows that have a line: a number set and no run error."""
    return [r for r in rows if not (r.missing or r.error)]


def points(project: Project, rows: Sequence[Row]) -> dict[str, list[Point]]:
    """The points of each line: point 0 (the initial slice), then the steps of the path."""
    return {r.code: [start_point(project, r.code)] + series(project, r.code) for r in rows}


def kinds(project: Project) -> list[str]:
    """The charts shown for a project, top to bottom."""
    if project.norm.labour_per_waiting_hour > 0:
        return [LABOUR, LABOUR_WAITING, CHECKS]
    return [LABOUR, CHECKS]


def chart(kind: str, project: Project, rows: Sequence[Row],
          pts: dict[str, list[Point]]) -> QChartView:
    """One chart as the window shows it, with the lines of ``rows``.

    :param kind: :data:`LABOUR`, :data:`LABOUR_WAITING` or :data:`CHECKS`.
    :param project: a checked project.
    :param rows: rows to draw, all with a line.
    :param pts: points of each row, as from :func:`points`.
    :return: the chart in its view.
    :rtype: QChartView
    """
    value = CHARTS[kind][2]
    view = _view(*titles(kind))
    order = [v.code for v in project.model.variants]
    LineCharts._fill(view, rows, pts, order, value)
    return view


def fit_height(view: QChartView, width: float) -> float:
    """Height at which a chart shows every entry of its legend; at least :data:`HEIGHT`.

    :param view: the chart, with its lines.
    :param width: width the chart is laid out at, pixels.
    :return: the height, pixels.
    :rtype: float
    """
    c = view.chart()
    c.resize(QSizeF(width, HEIGHT))
    if c.layout() is not None:
        c.layout().activate()
    rest = HEIGHT - c.legend().geometry().height()
    entry = QFontMetricsF(c.legend().font()).height() + 2 * LEGEND_ITEM_MARGIN
    return max(HEIGHT, rest + len(c.series()) * entry + 2 * LEGEND_PAD)


def render(view: QChartView, painter: QPainter, target: QRectF, size: QSizeF) -> None:
    """Paint a chart onto any painter, in vectors when the device takes them.

    :param view: the chart.
    :param painter: an active painter.
    :param target: where to paint, in the painter's coordinates.
    :param size: size the chart is laid out at, as on screen; it is scaled to ``target``.
    """
    c = view.chart()
    c.resize(size)
    if c.layout() is not None:
        c.layout().activate()
    view.scene().render(painter, target, QRectF(c.pos(), size))


class ChartView(QChartView):
    """A chart with a small ``Copy chart`` button in its top-right corner."""

    copied = Signal(str)  # the status text after the chart is copied
    CORNER = 4  # gap between the button and the corner of the view, pixels

    def __init__(self, chart: QChart) -> None:
        super().__init__(chart)
        self.copy_button = QPushButton(self.tr("Copy chart"), self)
        self.copy_button.setObjectName("copyChart")
        self.copy_button.setStyleSheet("padding: 1px 6px; font-size: 11px;")
        self.copy_button.adjustSize()
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self.copy_chart)
        self._place()

    def copy_chart(self) -> None:
        """Put the chart on the clipboard as an image, without the button."""
        self.copy_button.hide()
        image = self.grab().toImage()
        self.copy_button.show()
        QGuiApplication.clipboard().setImage(image)
        self.copied.emit(self.tr("Copied chart"))

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().resizeEvent(event)
        self._place()

    def _place(self) -> None:
        b = self.copy_button
        b.move(self.width() - b.width() - self.CORNER, self.CORNER)
        b.raise_()


def _view(title: str, y_title: str) -> ChartView:
    """An empty chart with integer step axis and a value axis."""
    chart = QChart()
    chart.setTitle(title)
    font = QFont()
    font.setPixelSize(15)
    font.setBold(True)
    chart.setTitleFont(font)
    chart.setTitleBrush(QColor(style.TEXT))
    chart.setBackgroundBrush(QColor(style.BG))
    chart.setMargins(QMargins(4, 4, 4, 4))
    chart.legend().setAlignment(Qt.AlignRight)
    chart.legend().setLabelColor(QColor(style.TEXT))
    chart.legend().setMarkerShape(QLegend.MarkerShapeFromSeries)
    step = QCoreApplication.translate("LineCharts", "Step")
    for title_, align, fmt in ((step, Qt.AlignBottom, "%d"), (y_title, Qt.AlignLeft, "%g")):
        axis = QValueAxis()
        axis.setTitleText(title_)
        axis.setLabelFormat(fmt)
        axis.setLabelsColor(QColor(style.TEXT2))
        axis.setTitleBrush(QColor(style.TEXT2))
        axis.setGridLineColor(QColor(style.BORDER))
        axis.setLinePenColor(QColor(style.BORDER))
        axis.setRange(0, 1)
        chart.addAxis(axis, align)
    view = ChartView(chart)
    view.setRenderHint(QPainter.Antialiasing)
    view.setMinimumHeight(HEIGHT)
    return view


class LineCharts(QWidget):
    """``Labour by step`` above ``Checks done by step``; one line per given variant. When the
    project sets ``labour_per_waiting_hour`` above 0, ``Labour + waiting by step`` goes between
    them.

    A line goes from point 0 (the initial slice) to the last step of its path. Own variants
    are drawn solid, other variants dashed; the colour of a line is fixed by the place of its
    variant in the project; a line is named by the variant code and side, as ``T1 · Ours``.
    """

    copied = Signal(str)  # a chart was copied; the status text

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.labour = _view(*titles(LABOUR))
        self.labour_waiting = _view(*titles(LABOUR_WAITING))
        self.labour_waiting.hide()
        self.checks = _view(*titles(CHECKS))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.labour)
        lay.addWidget(self.labour_waiting)
        lay.addWidget(self.checks)
        for view in (self.labour, self.labour_waiting, self.checks):
            view.copied.connect(self.copied)

    def set_rows(self, project: Project | None, rows: Sequence[Row]) -> None:
        """Replace the lines by those of ``rows``, in their order.

        :param project: a checked project; ``None`` clears the lines.
        :param rows: variants to draw; a variant with a number not set or a run error is not drawn.
        """
        rows = drawn(rows) if project is not None else []
        order = [v.code for v in project.model.variants] if project else []
        pts = points(project, rows)
        self._fill(self.labour, rows, pts, order, CHARTS[LABOUR][2])
        weighted = project is not None and LABOUR_WAITING in kinds(project)
        self.labour_waiting.setVisible(weighted)
        self._fill(self.labour_waiting, rows if weighted else [], pts, order,
                   CHARTS[LABOUR_WAITING][2])
        self._fill(self.checks, rows, pts, order, CHARTS[CHECKS][2])

    @staticmethod
    def _fill(view: QChartView, rows: Sequence[Row], pts: dict[str, list[Point]],
              order: list[str], value: Callable[[Point], object]) -> None:
        view.copy_button.setEnabled(bool(rows))
        chart = view.chart()
        chart.removeAllSeries()
        x_axis = chart.axes(Qt.Horizontal)[0]
        y_axis = chart.axes(Qt.Vertical)[0]
        x_max, y_max = 1, 0.0
        for r in rows:
            s = QLineSeries()
            s.setName(f"{r.code} · {style.side_name(r.side)}")
            pen = QPen(QColor(style.SERIES[order.index(r.code) % len(style.SERIES)]))
            pen.setWidth(2)
            pen.setStyle(Qt.SolidLine if r.side == "own" else Qt.DashLine)
            s.setPen(pen)
            for p in pts[r.code]:
                y = float(value(p))
                s.append(p.number, y)
                y_max = max(y_max, y)
            x_max = max(x_max, pts[r.code][-1].number)
            chart.addSeries(s)
            s.attachAxis(x_axis)
            s.attachAxis(y_axis)
        x_axis.setRange(0, x_max)
        x_axis.setTickType(QValueAxis.TicksDynamic)
        x_axis.setTickAnchor(0)
        x_axis.setTickInterval(1)
        y_axis.setRange(0, y_max * 1.1 or 1)
        y_axis.applyNiceNumbers()
