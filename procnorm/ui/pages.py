# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Read-only tabs: Dictionary, and Normalization with variants."""

from __future__ import annotations

from PySide6.QtWidgets import QAbstractItemView, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from procnorm.calc import fmt
from procnorm.project import Project
from procnorm.ui.tables import ARROW, CHECK, DASH, Table, label


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


class DictionaryPage(Page):
    """Entities, kinds, executors, instruments, scopes, variant parameters, named slices."""

    def __init__(self) -> None:
        super().__init__()
        self.box.addWidget(label("Dictionary", "h2"))
        self.info = label("", "note")
        self.box.addWidget(self.info)
        self.box.addWidget(label("ENTITY → AXES → VALUES", "h3"))
        self.entities = Table(["Entity", "Axis", "Values", "Inherits from"])
        self.box.addWidget(self.entities)
        self.box.addWidget(label("TRANSITION KINDS", "h3"))
        self.kinds = Table(["Kind", "Entity", "Axis: from → to", "Condition", "Check", "Zero weight"])
        self.box.addWidget(self.kinds)
        left, right = self.columns()
        left.addWidget(label("EXECUTORS", "h3"))
        self.executors = Table(["Executor"])
        left.addWidget(self.executors)
        left.addWidget(label("INSTRUMENTS", "h3"))
        self.instruments = Table(["Instrument"])
        left.addWidget(self.instruments)
        _end(left)
        right.addWidget(label("SCOPES", "h3"))
        self.scopes = Table(["Scope", "Batch"])
        right.addWidget(self.scopes)
        right.addWidget(label("VARIANT PARAMETERS", "h3"))
        self.params = Table(["Parameter"])
        right.addWidget(self.params)
        _end(right)
        self.box.addWidget(label("NAMED SLICES", "h3"))
        self.slices = Table(["Slice", "Reached when"])
        self.box.addWidget(self.slices)
        self.box.addStretch(1)

    def show_project(self, p: Project | None) -> None:
        """Fill the page; ``None`` empties it."""
        if p is None:
            self.info.setText("")
            for t in (self.entities, self.kinds, self.executors, self.instruments, self.scopes,
                      self.params, self.slices):
                t.set_rows([])
            return
        m = p.model
        self.info.setText(f"Existence axis: {m.existence_axis} (absent: {m.absent_value}). "
                          f"Batch scope: {m.batch_scope}.")
        rows = []
        for e in m.entities:
            for i, a in enumerate(e.axes):
                rows.append([e.name if i == 0 else "", a.name, ", ".join(a.values),
                             ", ".join(f"{se}/{sa}" for se, sa in a.inherit)])
        self.entities.set_rows(rows)
        self.kinds.set_rows([
            [k.name, k.entity, f"{k.axis}: {k.source} {ARROW} {k.target}",
             "; ".join(f"{e}/{a} = {v}" for e, a, v in k.requires),
             CHECK if k.check else "",
             (CHECK + (f" {k.zero_weight_note}" if k.zero_weight_note else "")) if k.zero_weight else ""]
            for k in m.kinds])
        self.executors.set_rows([[x.name] for x in m.executors])
        self.instruments.set_rows([[x] for x in m.instruments])
        self.scopes.set_rows([[s, CHECK if s == m.batch_scope else ""] for s in m.scopes])
        self.params.set_rows([[x] for x in m.variant_params] or [[DASH]])
        self.slices.set_rows([[ns.name, " or ".join(
            " and ".join([f"{e}/{a} = {v}" for e, a, v in g.states] + [f"{q} = {x}" for q, x in g.params])
            for g in ns.groups)] for ns in m.named_slices] or [[DASH, ""]])


class NormPage(Page):
    """Normalization numbers and the list of variants with their calls."""

    def __init__(self) -> None:
        super().__init__()
        self._project: Project | None = None
        self.box.addWidget(label("Normalization (numbers only)", "h2"))
        self.batch = label("", "note")
        self.box.addWidget(self.batch)
        left, right = self.columns()
        left.addWidget(label("TRANSITION KINDS — COST", "h3"))
        self.costs = Table(["Kind", "Cost"], {1})
        left.addWidget(self.costs)
        left.addWidget(label("SKIP PRICES", "h3"))
        self.prices = Table(["Entity", "Check axis", "Skip price"], {2})
        left.addWidget(self.prices)
        _end(left)
        right.addWidget(label("EXECUTOR COEFFICIENTS", "h3"))
        self.exec_coef = Table(["Executor", "×"], {1})
        right.addWidget(self.exec_coef)
        right.addWidget(label("SCOPE COEFFICIENTS", "h3"))
        self.scope_coef = Table(["Scope", "×"], {1})
        right.addWidget(self.scope_coef)
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

    def show_project(self, p: Project | None) -> None:
        """Fill the page; ``None`` empties it."""
        self._project = p
        if p is None:
            self.batch.setText("")
            for t in (self.costs, self.prices, self.exec_coef, self.scope_coef, self.errors, self.variants):
                t.set_rows([])
            self._variant_selected()
            return
        n, m = p.norm, p.model
        self.batch.setText("" if n.batch_size is None else f"Batch size: {fmt(n.batch_size)}")
        self.costs.set_rows([[k.name, fmt(n.kind_costs[k.name]) if k.name in n.kind_costs else DASH]
                             for k in m.kinds])
        self.prices.set_rows([[e, a, fmt(x)] for (e, a), x in n.skip_prices.items()])
        self.exec_coef.set_rows([[x, fmt(c)] for x, c in n.executor_coefficients.items()])
        self.scope_coef.set_rows([[s, fmt(c)] for s, c in n.scope_coefficients.items()])
        self.errors.set_rows([[g, t] for g, texts in n.uncounted_errors.items() for t in texts] or [[DASH, ""]])
        self.variants.set_rows([[v.code, v.title, p.sides[v.code], str(len(v.calls)), v.out_of_comparison or ""]
                                for v in m.variants])
        if m.variants:
            self.variants.selectRow(0)
        self._variant_selected()

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

