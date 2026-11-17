# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Main window of procnorm, version 1: stored projects, remarks, four read-only tabs."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QHBoxLayout, QMainWindow, QMessageBox,
                               QPushButton, QTabWidget, QVBoxLayout, QWidget)

from procnorm.project import load_file
from procnorm.store import Store, default_path
from procnorm.ui.chains import ChainsPage
from procnorm.ui.comparison import ComparisonPage
from procnorm.ui.pages import DictionaryPage, NormPage
from procnorm.ui.remarks import RemarksPanel
from procnorm.ui.style import STYLE
from procnorm.ui.tables import label

LAST = "last_project"
JSON_FILTER = "Project files (*.json);;All files (*)"


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
        self.load_button = self._button(bar, "Load", self.on_load)
        self.load_over_button = self._button(bar, "Load over", self.on_load_over)
        self.save_button = self._button(bar, "Save file", self.on_save)
        self.copy_button = self._button(bar, "Copy", self.copy_project)
        self.delete_button = self._button(bar, "Delete", self.delete_project)
        head.addLayout(bar)
        self.remarks_panel = RemarksPanel()
        head.addWidget(self.remarks_panel)
        lay.addLayout(head)

        self.tabs = QTabWidget()
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
        lay.addWidget(self.tabs, 1)
        self.setCentralWidget(body)
        self.comparison.export_md.clicked.connect(lambda: self.on_export(".md"))
        self.comparison.export_csv.clicked.connect(lambda: self.on_export(".csv"))

        last = settings.value(LAST) if settings is not None else None
        self.refresh(int(last) if last is not None else None)

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
        project = self.store.get(pid) if pid is not None else None
        for page in (self.dictionary, self.norm, self.comparison, self.chains):
            page.show_project(project)
        for b in (self.load_over_button, self.save_button, self.copy_button, self.delete_button):
            b.setEnabled(pid is not None)
        if self.settings is not None and pid is not None:
            self.settings.setValue(LAST, pid)
            self.settings.sync()

    # --- actions without dialogs (driven by tests)

    def load_path(self, path: Path) -> bool:
        """Load a file as a new project; on remarks show them and store nothing."""
        project, remarks = load_file(Path(path))
        if project is None:
            self.remarks_panel.show_remarks(path, remarks)
            return False
        self.remarks_panel.hide()
        self.refresh(self.store.add(project))
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
        self.statusBar().showMessage(f"Loaded {Path(path).name} over the project")
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

    # --- actions with file dialogs

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
