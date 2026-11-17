# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Main window of procnorm, version 1: stored projects, remarks, four read-only tabs."""

from __future__ import annotations

import html
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QTextDocumentFragment
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout,
                               QInputDialog, QLabel, QMainWindow, QMessageBox, QPushButton,
                               QStackedWidget, QTabWidget, QVBoxLayout, QWidget)

from procnorm.calc import empty_steps, project_empty_steps
from procnorm import edit
from procnorm.edit import (add_call, copy_code, copy_variant, delete_variant, move_call, remove_call,
                           rename_variant, set_number)
from procnorm.project import Project, load_file, read_project
from procnorm.store import Store, default_path
from procnorm.ui.chains import ChainsPage
from procnorm.ui.comparison import ComparisonPage
from procnorm.ui.pages import DictionaryPage, NormPage
from procnorm.ui.remarks import RemarksPanel
from procnorm.ui.style import ACCENT, STYLE
from procnorm.ui.tables import label

LAST = "last_project"
NEW_NAME = "New project"
JSON_FILTER = "Project files (*.json);;All files (*)"


def _dot_icon() -> QIcon:
    """A small accent dot for a tab."""
    pix = QPixmap(10, 10)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(ACCENT))
    painter.drawEllipse(1, 1, 8, 8)
    painter.end()
    return QIcon(pix)


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


class OfferTabs(QTabWidget):
    """Tabs with a full-width strip between the tab bar and the pages."""

    def __init__(self) -> None:
        super().__init__()
        self.strip = QFrame(self)
        self.strip.hide()

    def place(self) -> None:
        """Put the strip under the tab bar and push the pages down by its height."""
        stack = self.findChild(QStackedWidget)
        if stack is None:
            return
        bar_h = self.tabBar().height()
        h = self.strip.layout().totalHeightForWidth(self.width()) if not self.strip.isHidden() else 0
        self.strip.setGeometry(0, bar_h, self.width(), h)
        stack.setGeometry(0, bar_h + h, self.width(), max(0, self.height() - bar_h - h))
        self.strip.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.place()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.place()


class MainWindow(QMainWindow):
    """The window over one store.

    :param store: the project store.
    :param settings: where the last selected project is remembered; ``None`` remembers nothing.
    """

    def __init__(self, store: Store, settings: QSettings | None = None) -> None:
        super().__init__()
        self.store = store
        self.settings = settings
        self.current_id: int | None = None
        self.setWindowTitle("procnorm")
        self.setStyleSheet(STYLE)
        self.resize(1100, 780)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        head = QVBoxLayout()
        head.setContentsMargins(16, 14, 16, 12)
        head.addWidget(label("procnorm", "title"))
        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(label("<b>Project:</b>"))
        self.projects = QComboBox()
        self.projects.currentIndexChanged.connect(self._project_chosen)
        bar.addWidget(self.projects, 1)
        self.new_button = self._button(bar, "New", self.on_new)
        self.load_button = self._button(bar, "Load", self.on_load)
        self.load_over_button = self._button(bar, "Load over", self.on_load_over)
        self.save_button = self._button(bar, "Save file", self.on_save)
        self.copy_button = self._button(bar, "Copy", self.copy_project)
        self.delete_button = self._button(bar, "Delete", self.delete_project)
        head.addLayout(bar)
        self.remarks_panel = RemarksPanel()
        head.addWidget(self.remarks_panel)
        lay.addLayout(head)

        self.tabs = OfferTabs()
        self.tabs.setDocumentMode(True)
        self.dictionary = DictionaryPage()
        self.norm = NormPage()
        self.comparison = ComparisonPage()
        self.tabs.addTab(self.dictionary, "Dictionary")
        self.tabs.addTab(self.norm, "Normalization && variants")
        self.tabs.addTab(self.comparison, "Comparison")
        self.chains = ChainsPage()
        self.tabs.addTab(self.chains, "Step chains")
        self.tabs.setCurrentWidget(self.comparison)
        self._build_offer()
        self.tabs.currentChanged.connect(self._tab_changed)
        lay.addWidget(self.tabs, 1)
        self.setCentralWidget(body)
        self.norm.number_edited.connect(self.edit_number)
        self.chains.edit_requested.connect(self.edit_chain)
        self.dictionary.word_edited.connect(lambda what, old, name: self.edit_word("rename", what, old, name))
        self.dictionary.word_removed.connect(lambda what, old: self.edit_word("delete", what, old))
        self.comparison.export_md.clicked.connect(lambda: self.on_export(".md"))
        self.comparison.export_csv.clicked.connect(lambda: self.on_export(".csv"))

        last = settings.value(LAST) if settings is not None else None
        self.refresh(int(last) if last is not None else None)

    def _build_offer(self) -> None:
        strip = self.tabs.strip
        strip.setObjectName("offer")
        row = QHBoxLayout(strip)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(16)
        self._offer_label = QLabel()
        self._offer_label.setWordWrap(True)
        self._offer_label.setTextFormat(Qt.TextFormat.RichText)
        row.addWidget(self._offer_label, 1)
        self.offer_show_button = QPushButton("Show step chains")
        self.offer_show_button.setProperty("primary", True)
        self.offer_later_button = QPushButton("Not now")
        self.offer_show_button.clicked.connect(self._offer_show)
        self.offer_later_button.clicked.connect(lambda: self._set_offer(False))
        row.addWidget(self.offer_show_button)
        row.addWidget(self.offer_later_button)

    def _set_offer(self, shown: bool) -> None:
        self.tabs.strip.setVisible(shown)
        self.tabs.place()

    def _set_dot(self, shown: bool) -> None:
        self.tabs.setTabIcon(3, _dot_icon() if shown else QIcon())
        self.tabs.place()

    def offer_visible(self) -> bool:
        """Whether the offer bar is shown."""
        return not self.tabs.strip.isHidden()

    def offer_text(self) -> str:
        """The text of the offer bar, without markup."""
        doc = QTextDocumentFragment.fromHtml(self._offer_label.text())
        return doc.toPlainText()

    def chains_dot(self) -> bool:
        """Whether the Step chains tab carries the dot."""
        return not self.tabs.tabIcon(3).isNull()

    def _tab_changed(self, index: int) -> None:
        if index == 3 and self.chains_dot():
            self._set_dot(False)

    def _offer_show(self) -> None:
        codes = self.chains.codes()
        project = self.store.get(self.current_id) if self.current_id is not None else None
        target = next((c for c in codes if project and empty_steps(project, c)), None)
        if target is None and codes:
            target = codes[0]
        if target is not None:
            self.chains.select_path(target)
        self._set_offer(False)
        self.tabs.setCurrentWidget(self.chains)

    def _offer(self, project: Project) -> None:
        n = len(project.model.variants)
        k = project_empty_steps(project)
        text = (f"<b>{html.escape(self.projects.currentText())} loaded: {_plural(n, 'path', 'paths')}.</b> "
                "Check how your steps were split into transitions before you compare.")
        if k:
            verb = "has" if k == 1 else "have"
            text += f" {_plural(k, 'step', 'steps')} {verb} no transitions."
        self._offer_label.setText(text)
        self._set_offer(True)
        if self.tabs.currentIndex() != 3:
            self._set_dot(True)

    @staticmethod
    def _button(bar: QHBoxLayout, text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.clicked.connect(lambda: slot())
        bar.addWidget(b)
        return b

    # --- project list

    def refresh(self, select: int | None = None) -> None:
        """Reread the project list and select a project (the first one if ``select`` is absent)."""
        infos = self.store.list()
        ids = [i.id for i in infos]
        if select not in ids:
            select = ids[0] if ids else None
        self.projects.blockSignals(True)
        self.projects.clear()
        for i in infos:
            self.projects.addItem(i.name, i.id)
        self.projects.setCurrentIndex(ids.index(select) if select is not None else -1)
        self.projects.blockSignals(False)
        self._open(select)

    def project_names(self) -> list[str]:
        """Names in the project list."""
        return [self.projects.itemText(i) for i in range(self.projects.count())]

    def _project_chosen(self, index: int) -> None:
        self._open(self.projects.itemData(index) if index >= 0 else None)

    def _open(self, pid: int | None) -> None:
        self.current_id = pid
        self._set_offer(False)
        self._set_dot(False)
        project = self.store.get(pid) if pid is not None else None
        for page in (self.dictionary, self.norm, self.comparison, self.chains):
            page.show_project(project)
        for b in (self.load_over_button, self.save_button, self.copy_button, self.delete_button):
            b.setEnabled(pid is not None)
        if self.settings is not None and pid is not None:
            self.settings.setValue(LAST, pid)
            self.settings.sync()

    # --- edits

    def edit_number(self, table: str, key: str | tuple[str, str], text: str) -> bool:
        """Set, change or clear a normalization number of the selected project.

        Accepted: written to the database at once, every tab recalculated with its view kept.
        Refused: nothing is written, the cell keeps its number, a red line under its table says why.

        :param table: ``kind_costs``, ``executor_coefficients``, ``scope_coefficients`` or
            ``axis_skip_prices``.
        :param key: the name, or ``(entity, axis)`` for a skip price.
        :param text: the typed number, comma or point; empty clears it.
        :return: whether the edit was accepted.
        :rtype: bool
        """
        if self.current_id is None:
            return False
        data, remarks = set_number(self.store.get(self.current_id).data, table, key, text)
        if data is None:
            own = f"normalization, {table}"
            self.norm.show_refusal(table, "; ".join(r.text if r.where == own else str(r) for r in remarks))
            return False
        self._save_edit(data)
        return True

    def edit_chain(self, op: str, args: tuple) -> bool:
        """Move, remove or add a transition of a variant, from the Step chains tab.

        Accepted: written at once, every tab recalculated with its view kept. Refused: nothing is
        written, a red line under the chain says why.

        :param op: ``move`` with ``(code, number, ±1)``, ``remove`` with ``(code, number)``, ``add``
            with ``(code, after, [kind, executor, instrument, scope], step)``; numbers from 1. Also
            ``copy`` and ``delete`` with ``(code,)`` and ``rename`` with ``(code, new code, title)``.
            Delete asks ``confirm`` first; a copy is chosen, after a delete the neighbour is chosen.
        :return: whether the edit was accepted.
        :rtype: bool
        """
        if self.current_id is None:
            return False
        if op == "delete" and not self.confirm(f"Delete {args[0]}?"):
            return False
        fn = {"move": move_call, "remove": remove_call, "add": add_call, "copy": copy_variant,
              "delete": delete_variant, "rename": rename_variant}[op]
        data, remarks = fn(self.store.get(self.current_id).data, *args)
        if data is None:
            own = f"variant {args[0]}"
            self.chains.show_refusal("; ".join(r.text if r.where == own else str(r) for r in remarks))
            return False
        if op == "copy":
            self.chains.choose_next(copy_code(args[0]))
        elif op == "rename":
            self.chains.choose_next(args[1].strip())
        elif op == "delete":
            codes = self.chains.codes()
            rest = [c for c in codes if c != args[0]]
            at = codes.index(args[0]) if args[0] in codes else 0
            self.chains.choose_next(rest[min(at, len(rest) - 1)] if rest else None)
        self._save_edit(data)
        return True

    def edit_word(self, op: str, what: str, old: str | tuple[str, ...], name: str = "") -> bool:
        """Rename or delete a dictionary word of the selected project, from the Dictionary tab.

        Accepted: written at once, every tab recalculated with its view kept. Refused: nothing is
        written, a red line under the word's table says why; a used word is not deleted, and the
        places where it is used are listed. A word is deleted without a question.

        :param op: ``rename`` or ``delete``.
        :param what: one of ``edit.WORDS``.
        :param old: the name; ``(entity, axis)`` for an axis, ``(entity, axis, value)`` for a value.
        :param name: the new name, for ``rename``.
        :return: whether the edit was accepted.
        :rtype: bool
        """
        if self.current_id is None:
            return False
        data = self.store.get(self.current_id).data
        if op == "rename":
            new, remarks = edit.rename(data, what, old, name)
        else:
            new, remarks = edit.delete(data, what, old)
        if new is None:
            short = old[-1] if isinstance(old, tuple) else old
            own = f"{what.replace('_', ' ')} {'/'.join(old) if isinstance(old, tuple) else old}"
            text = "; ".join(r.text if r.where == own else str(r) for r in remarks)
            line, _, places = text.partition("\n")
            if op == "rename" and remarks[0].where == own:
                line = f"{short}: {line}"
            self.dictionary.show_refusal(what, line, places.split("\n") if places else [])
            return False
        self._save_edit(new)
        return True

    def _save_edit(self, data: dict) -> None:
        """Write an accepted edit and refill every tab, keeping its view."""
        self.store.save(self.current_id, data)
        project = self.store.get(self.current_id)
        for page in (self.dictionary, self.norm, self.comparison, self.chains):
            page.show_project(project, keep=True)

    # --- actions without dialogs (driven by tests)

    def load_path(self, path: Path) -> bool:
        """Load a file as a new project; on remarks show them and store nothing."""
        project, remarks = load_file(Path(path))
        if project is None:
            self.remarks_panel.show_remarks(path, remarks)
            return False
        self.remarks_panel.hide()
        self.refresh(self.store.add(project))
        self._offer(project)
        self.statusBar().showMessage(f"Loaded {Path(path).name}")
        return True

    def load_over_path(self, path: Path) -> bool:
        """Replace the selected project from a file; on remarks keep it as it is."""
        if self.current_id is None:
            return False
        project, remarks = load_file(Path(path))
        if project is None:
            self.remarks_panel.show_remarks(path, remarks)
            return False
        self.remarks_panel.hide()
        pid = self.current_id
        self.store.replace(pid, project)
        self.refresh(pid)
        self._offer(project)
        self.statusBar().showMessage(f"Loaded {Path(path).name} over the project")
        return True

    def new_project(self, name: str) -> bool:
        """Create an empty project, select it and open the Dictionary tab.

        An empty name stores nothing and shows the remark.

        :param name: the project name.
        :return: whether the project was created.
        :rtype: bool
        """
        data, remarks = edit.empty_project(name)
        if data is None:
            self.remarks_panel.show_name_remarks(remarks)
            return False
        project, remarks = read_project(data, strict=False)
        if project is None:
            self.remarks_panel.show_name_remarks(remarks)
            return False
        self.remarks_panel.hide()
        self.refresh(self.store.add(project))
        self.tabs.setCurrentWidget(self.dictionary)
        self.statusBar().showMessage(f"Created {project.name}")
        return True

    def save_path(self, path: Path) -> None:
        """Write the selected project's file."""
        Path(path).write_text(self.store.text(self.current_id), encoding="utf-8")
        self.statusBar().showMessage(f"Saved {Path(path).name}")

    def copy_project(self) -> None:
        """Copy the selected project and select the copy."""
        if self.current_id is not None:
            self.refresh(self.store.copy(self.current_id))

    def delete_project(self) -> None:
        """Delete the selected project after confirmation."""
        if self.current_id is None:
            return
        if not self.confirm(f"Delete the project “{self.projects.currentText()}”? This cannot be undone."):
            return
        self.store.delete(self.current_id)
        self.refresh()

    def confirm(self, text: str) -> bool:
        """Ask yes or no."""
        answer = QMessageBox.question(self, "procnorm", text)
        return answer == QMessageBox.StandardButton.Yes

    def warn(self, text: str) -> None:
        """Show a problem."""
        QMessageBox.warning(self, "procnorm", text)

    def ask_name(self, text: str) -> str | None:
        """Ask the name of a new project; ``None`` when cancelled."""
        name, ok = QInputDialog.getText(self, "Project name", "Project name:", text=text)
        return name if ok else None

    # --- actions with file dialogs

    def on_new(self) -> None:
        name = self.ask_name(NEW_NAME)
        if name is not None:
            self.new_project(name)

    def on_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load project file", "", JSON_FILTER)
        if path:
            self.load_path(Path(path))

    def on_load_over(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load over the selected project", "", JSON_FILTER)
        if path:
            self.load_over_path(Path(path))

    def on_save(self) -> None:
        name = f"{self.projects.currentText() or 'project'}.json"
        path, _ = QFileDialog.getSaveFileName(self, "Save project file", name, JSON_FILTER)
        if path:
            try:
                self.save_path(Path(path))
            except OSError as exc:
                self.warn(f"Cannot write the file: {exc}")

    def on_export(self, suffix: str) -> None:
        what = "Markdown (*.md)" if suffix == ".md" else "CSV (*.csv)"
        name = f"{self.projects.currentText() or 'comparison'}{suffix}"
        path, _ = QFileDialog.getSaveFileName(self, "Export comparison", name, what)
        if not path:
            return
        p = Path(path)
        if p.suffix.lower() != suffix:
            p = p.with_name(p.name + suffix)
        try:
            self.comparison.export_path(p)
            self.statusBar().showMessage(f"Exported {p.name}")
        except OSError as exc:
            self.warn(f"Cannot write the file: {exc}")


def main() -> int:
    """Run the window over the default store."""
    app = QApplication.instance() or QApplication(sys.argv)
    store = Store(default_path())
    window = MainWindow(store, QSettings("procnorm", "procnorm"))
    window.show()
    try:
        return app.exec()
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
