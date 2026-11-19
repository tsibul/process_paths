# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Main window of Measure Twice, version 1: stored projects, remarks, four read-only tabs."""

from __future__ import annotations

import html
import sys
from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP, QSettings, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap, QTextDocumentFragment
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout,
                               QInputDialog, QLabel, QMainWindow, QMenu, QMessageBox,
                               QPushButton, QStackedWidget, QTabWidget, QVBoxLayout, QWidget,
                               QWidgetAction)

from measure_twice.calc import empty_steps, project_empty_steps
from measure_twice import edit, i18n, report
from measure_twice.ai import extract_json
from measure_twice.example import EXAMPLE_NAME, add_example, first_run
from measure_twice.edit import (
    add_call,
    copy_code,
    copy_variant,
    delete_variant,
    move_call,
    remove_call,
    rename_variant,
    set_number,
)
from measure_twice.project import Project, load_file, parse_text, read_project
from measure_twice.store import Store, default_path
from measure_twice.ui.ai_scenario import AiScenarioDialog
from measure_twice.ui.chains import NO_EXECUTOR_HINT, ChainsPage, new_is_off
from measure_twice.ui.comparison import ComparisonPage
from measure_twice.ui.pages import DictionaryPage, NormPage
from measure_twice.ui.paste import PasteDialog
from measure_twice.ui.remarks import RemarksPanel
from measure_twice.ui.report_dialog import ReportDialog
from measure_twice.ui.style import ACCENT, STYLE
from measure_twice.ui.tables import (
    NOTE_ROLE,
    NoteDelegate,
    label,
    plural,
    project_note,
    translate,
)

LAST = "last_project"
NEW_NAME = "New project"
NEW_TITLE = "New variant"  # title of a variant added on Step chains
JSON_FILTER = QT_TRANSLATE_NOOP("MainWindow", "Project files (*.json);;All files (*)")
NO_JSON = QT_TRANSLATE_NOOP("MainWindow", "No JSON object found in the text.")
EXPORT_HINT = QT_TRANSLATE_NOOP(
    "MainWindow",
    "The program keeps your projects by itself. This makes a file to send or archive.",
)


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
        self._amber: list[str] = []  # variants that got errors after a dictionary edit
        self._scenario: AiScenarioDialog | None = None  # kept between openings until a load
        self.setWindowTitle("Measure Twice")
        self.setStyleSheet(STYLE)
        self.resize(1100, 780)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        head = QVBoxLayout()
        head.setContentsMargins(16, 14, 16, 12)
        head.addWidget(label("Measure Twice", "title"))
        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(label(self.tr("<b>Comparing:</b>")))
        self.projects = QComboBox()
        self.projects.setItemDelegate(NoteDelegate(self.projects))
        self.projects.currentIndexChanged.connect(self._project_chosen)
        bar.addWidget(self.projects, 1)
        self._build_menus(bar)
        self._build_language(bar)
        self.panel_bar = bar
        head.addLayout(bar)
        head.addWidget(self._build_restart())
        self.remarks_panel = RemarksPanel()
        head.addWidget(self.remarks_panel)
        lay.addLayout(head)

        self.tabs = OfferTabs()
        self.tabs.setDocumentMode(True)
        self.dictionary = DictionaryPage()
        self.norm = NormPage()
        self.comparison = ComparisonPage()
        self.tabs.addTab(self.dictionary, self.tr("Dictionary"))
        self.tabs.addTab(self.norm, self.tr("Normalization && variants"))
        self.tabs.addTab(self.comparison, self.tr("Comparison"))
        self.chains = ChainsPage()
        self.tabs.addTab(self.chains, self.tr("Step chains"))
        self.tabs.setCurrentWidget(self.comparison)
        self._build_offer()
        self.tabs.currentChanged.connect(self._tab_changed)
        lay.addWidget(self.tabs, 1)
        self.setCentralWidget(body)
        self.norm.number_edited.connect(self.edit_number)
        self.chains.edit_requested.connect(self.edit_chain)
        self.dictionary.word_edited.connect(lambda what, old, name: self.edit_word("rename", what, old, name))
        self.dictionary.word_removed.connect(lambda what, old: self.edit_word("delete", what, old))
        self.dictionary.word_added.connect(self.add_word)
        self.dictionary.word_moved.connect(self.move_word)
        self.dictionary.existence_set.connect(self.set_existence)
        self.dictionary.batch_set.connect(self.set_batch_scope)
        self.dictionary.kind_added.connect(self.add_kind)
        self.dictionary.kind_set.connect(self.set_kind)
        self.dictionary.slice_added.connect(self.add_slice)
        self.dictionary.slice_set.connect(self.set_slice)
        self.comparison.export_md.clicked.connect(lambda: self.on_export(".md"))
        self.comparison.export_csv.clicked.connect(lambda: self.on_export(".csv"))
        self.comparison.report_button.clicked.connect(self.on_report)
        self.comparison.copied.connect(self.statusBar().showMessage)

        last = settings.value(LAST) if settings is not None else None
        self.refresh(int(last) if last is not None else None)
        # Wide enough for the whole button row.
        self.resize(max(1100, self.minimumSizeHint().width()), 780)

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
        self.offer_show_button = QPushButton(self.tr("Show step chains"))
        self.offer_show_button.setProperty("primary", True)
        self.offer_later_button = QPushButton(self.tr("Not now"))
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
        text = plural(
            self.tr(
                "<b>{name} loaded: %n path.</b> "
                "Check how your steps were split into transitions before you compare.",
                "",
                n,
            ),
            "<b>{name} loaded: %n path.</b> "
            "Check how your steps were split into transitions before you compare.",
            "<b>{name} loaded: %n paths.</b> "
            "Check how your steps were split into transitions before you compare.",
            n,
        )
        text = text.format(name=html.escape(self.projects.currentText()))
        if k:
            text += " " + plural(
                self.tr("%n step has no transitions.", "", k),
                "%n step has no transitions.",
                "%n steps have no transitions.",
                k,
            )
        self._offer_label.setText(text)
        self._set_offer(True)
        if self.tabs.currentIndex() != 3:
            self._set_dot(True)

    def _build_menus(self, bar: QHBoxLayout) -> None:
        """The `+ New ▾` menu (making a project) and the `More ▾` menu (the open one)."""
        self.new_menu = QMenu(self)
        self.ai_action = self._item(self.new_menu, self.tr("With AI…"), self.on_ai)
        self.paste_action = self._item(self.new_menu, self.tr("Paste AI answer…"), self.on_paste)
        self.load_action = self._item(self.new_menu, self.tr("From file…"), self.on_load)
        self.new_action = self._item(self.new_menu, self.tr("Empty"), self.on_new)
        self.example_action = self._item(self.new_menu, self.tr("Example"), self.show_example)
        tip = self.tr("Add the {name} example").format(name=EXAMPLE_NAME)
        self.example_action.setToolTip(tip)
        self.new_menu_button = self._menu_button(bar, self.tr("+ New ▾"), self.new_menu)
        self.new_menu_button.setProperty("primary", True)

        self.more_menu = QMenu(self)
        self.save_action = self._item(self.more_menu, self.tr("Export to file…"), self.on_save)
        hint = QLabel(translate("MainWindow", EXPORT_HINT))
        hint.setObjectName("menuHint")
        self.export_hint = QWidgetAction(self.more_menu)
        self.export_hint.setDefaultWidget(hint)
        self.export_hint.setEnabled(False)
        self.more_menu.addAction(self.export_hint)
        self.copy_action = self._item(self.more_menu, self.tr("Duplicate"), self.copy_project)
        self.load_over_action = self._item(
            self.more_menu, self.tr("Replace from file…"), self.on_load_over
        )
        self.delete_action = self._item(self.more_menu, self.tr("Delete…"), self.delete_project)
        self.more_menu_button = self._menu_button(bar, self.tr("More ▾"), self.more_menu)

    def _build_language(self, bar: QHBoxLayout) -> None:
        """The language switch at the end of the panel row: the code on view, names in the list."""
        self.running_language = i18n.current()
        chosen = i18n.read_language(self.settings) if self.settings is not None else None
        self.language_menu = QMenu(self)
        for code, name in i18n.LANGUAGES.items():
            action = self.language_menu.addAction(f"{code.upper()} {name}")
            action.setCheckable(True)
            action.setData(code)
            action.triggered.connect(lambda _=False, c=code: self.choose_language(c))
        self.language_button = self._menu_button(bar, "", self.language_menu)
        self._show_language(chosen or self.running_language)

    def _build_restart(self) -> QFrame:
        """The line shown after a language is chosen: it applies from the next start."""
        self.restart_row = QFrame()
        row = QHBoxLayout(self.restart_row)
        row.setContentsMargins(0, 8, 0, 0)
        row.setSpacing(8)
        self.restart_note = label(self.tr("The language changes at the next start."), "note")
        row.addWidget(self.restart_note, 1)
        self.restart_button = QPushButton(self.tr("Restart now"))
        self.restart_button.clicked.connect(lambda: i18n.restart())
        row.addWidget(self.restart_button)
        self.restart_row.hide()
        return self.restart_row

    def _show_language(self, code: str) -> None:
        self.language_button.setText(f"{code.upper()} ▾")
        for action in self.language_menu.actions():
            action.setChecked(action.data() == code)

    def choose_language(self, code: str) -> None:
        """Keep the chosen language; the window keeps its language until the next start."""
        if self.settings is not None:
            i18n.write_language(self.settings, code)
        self._show_language(code)
        self.restart_row.setVisible(code != self.running_language)

    @staticmethod
    def _item(menu: QMenu, text: str, slot) -> QAction:
        action = menu.addAction(text)
        action.triggered.connect(lambda: slot())
        return action

    @staticmethod
    def _menu_button(bar: QHBoxLayout, text: str, menu: QMenu) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("menuButton")
        b.setMenu(menu)
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
            self.projects.setItemData(self.projects.count() - 1, project_note(i.ways, i.updated),
                                      NOTE_ROLE)
        self.projects.setCurrentIndex(ids.index(select) if select is not None else -1)
        self.projects.blockSignals(False)
        self._open(select)

    def _update_note(self) -> None:
        """Refresh the grey column of the open project's row after a write."""
        index = self.projects.findData(self.current_id)
        for i in self.store.list():
            if i.id == self.current_id and index >= 0:
                self.projects.setItemData(index, project_note(i.ways, i.updated), NOTE_ROLE)

    def project_names(self) -> list[str]:
        """Names in the project list."""
        return [self.projects.itemText(i) for i in range(self.projects.count())]

    def _project_chosen(self, index: int) -> None:
        self._open(self.projects.itemData(index) if index >= 0 else None)

    def _open(self, pid: int | None) -> None:
        self.current_id = pid
        self._amber = []
        self.dictionary.show_amber([])
        self._set_offer(False)
        self._set_dot(False)
        project = self.store.get(pid) if pid is not None else None
        for page in (self.dictionary, self.norm, self.comparison, self.chains):
            page.show_project(project)
        for a in (self.save_action, self.copy_action, self.load_over_action, self.delete_action):
            a.setEnabled(pid is not None)
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
            ``variant`` with ``(code, {field: value})`` changes several fields at once.
            ``header`` with ``(code, field, value)`` changes one field of
            :func:`measure_twice.edit.set_variant`; ``new`` with ``()`` adds a variant ``New N``
            and chooses it.
        :return: whether the edit was accepted.
        :rtype: bool
        """
        if self.current_id is None:
            return False
        if op == "new":
            return self._new_variant()
        if op == "delete" and not self.confirm(f"Delete {args[0]}?"):
            return False
        if op == "header":
            code, field_, value = args
            args = (code,)
            fields = {field_: value}
        elif op == "variant":
            code, fields = args
            args = (code,)
        else:
            fields = {}
        fn = {"move": move_call, "remove": remove_call, "add": add_call, "copy": copy_variant,
              "delete": delete_variant, "rename": rename_variant, "header": edit.set_variant,
              "variant": edit.set_variant}[op]
        data, remarks = fn(self.store.get(self.current_id).data, *args, **fields)
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

    def _new_variant(self) -> bool:
        """Add the variant ``New N`` with the first free ``N`` and choose it."""
        if new_is_off(self.store.get(self.current_id)):
            self.chains.show_refusal(translate("ChainsPage", NO_EXECUTOR_HINT))
            return False
        data = self.store.get(self.current_id).data
        taken = set()
        for v in data.get("variants", []):
            taken.add(v.get("code"))
        n = 1
        while f"New {n}" in taken:
            n += 1
        code = f"New {n}"
        new, remarks = edit.add_variant(data, code, NEW_TITLE)
        if new is None:
            texts = []
            for r in remarks:
                if r.where == "add variant":
                    texts.append(r.text)
                else:
                    texts.append(str(r))
            self.chains.show_refusal("; ".join(texts))
            return False
        self.chains.choose_next(code)
        self._save_edit(new)
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
        self._save_edit(new, dictionary=True)
        return True

    def add_word(self, what: str, name: str | tuple[str, ...], first_value: str | None = None,
                 executor: str | None = None) -> bool:
        """Add a dictionary word to the selected project, from an add row of the Dictionary tab.

        Accepted: written at once, every tab recalculated with its view kept; the input closes.
        Refused: nothing is written, a red line under the word's table says why and the input
        stays open with the typed text.

        :param what: one of ``edit.ADDED_WORDS``.
        :param name: the name; ``(entity, axis)`` for an axis, ``(entity, axis, value)`` for a
            value.
        :param first_value: the first value of a new axis.
        :param executor: the executor every variant takes for a new variant parameter.
        :return: whether the word was added.
        :rtype: bool
        """
        if self.current_id is None:
            return False
        data = self.store.get(self.current_id).data
        new, remarks = edit.add_word(data, what, name, first_value=first_value, executor=executor)
        if new is None:
            self._refuse_word(what, remarks, f"add {what.replace('_', ' ')}")
            return False
        self._save_edit(new, dictionary=True)
        return True

    def move_word(self, what: str, old: str | tuple[str, ...], delta: int) -> bool:
        """Move a dictionary word one place up (-1) or down (+1) in its own list.

        :param what: one of ``edit.WORDS``.
        :param old: the name; ``(entity, axis)`` for an axis, ``(entity, axis, value)`` for a value.
        :param delta: -1 or +1.
        :return: whether the word was moved.
        :rtype: bool
        """
        if self.current_id is None:
            return False
        data = self.store.get(self.current_id).data
        new, remarks = edit.move_word(data, what, old, delta)
        if new is None:
            shown = old
            if isinstance(old, tuple):
                shown = "/".join(old)
            self._refuse_word(what, remarks, f"{what.replace('_', ' ')} {shown}")
            return False
        self._save_edit(new, dictionary=True)
        return True

    def set_existence(self, name: str, absent: str) -> bool:
        """Set the existence axis and its absent value, from the row above the Dictionary tables.

        :return: whether the change was accepted.
        :rtype: bool
        """
        if self.current_id is None:
            return False
        data = self.store.get(self.current_id).data
        new, remarks = edit.set_existence_axis(data, name, absent)
        if new is None:
            self._refuse_word("existence_axis", remarks, "existence axis")
            return False
        self._save_edit(new, dictionary=True)
        return True

    def set_batch_scope(self, scope: str) -> bool:
        """Choose the batch scope, from the row above the Dictionary tables.

        :return: whether the change was accepted.
        :rtype: bool
        """
        if self.current_id is None:
            return False
        data = self.store.get(self.current_id).data
        new, remarks = edit.set_batch_scope(data, scope)
        if new is None:
            self._refuse_word("batch_scope", remarks, "batch scope")
            return False
        self._save_edit(new, dictionary=True)
        return True

    def add_kind(self, name: str, structure: dict) -> bool:
        """Add a transition kind, from the kind form of the Dictionary tab.

        Accepted: written at once, every tab recalculated with its view kept; the form closes.
        Refused: nothing is written, a red line under the kinds says why and the form stays open
        with what was chosen.

        :param name: the typed name.
        :param structure: see ``edit.add_kind``.
        :return: whether the kind was added.
        :rtype: bool
        """
        return self._put_kind(edit.add_kind, "add kind", name, structure)

    def set_kind(self, name: str, structure: dict) -> bool:
        """Change a transition kind, from the kind form of the Dictionary tab; as
        :meth:`add_kind`.

        :param name: the kind.
        :param structure: see ``edit.set_kind``.
        :return: whether the kind was changed.
        :rtype: bool
        """
        return self._put_kind(edit.set_kind, "set kind", name, structure)

    def _put_kind(self, fn, own: str, name: str, structure: dict) -> bool:
        if self.current_id is None:
            return False
        data = self.store.get(self.current_id).data
        new, remarks = fn(data, name, structure)
        if new is None:
            self._refuse_word("kind", remarks, (own, f"kind {name.strip()}"))
            return False
        self._save_edit(new, dictionary=True)
        return True

    def add_slice(self, name: str, groups: list) -> bool:
        """Add a named slice, from the slice form of the Dictionary tab; as :meth:`add_kind`.

        :param name: the typed name.
        :param groups: see ``edit.add_slice``.
        :return: whether the slice was added.
        :rtype: bool
        """
        return self._put_slice(edit.add_slice, "add slice", name, groups)

    def set_slice(self, name: str, groups: list) -> bool:
        """Change the groups of a named slice, from the slice form of the Dictionary tab; as
        :meth:`add_kind`.

        :param name: the named slice.
        :param groups: see ``edit.set_slice``.
        :return: whether the slice was changed.
        :rtype: bool
        """
        return self._put_slice(edit.set_slice, "set slice", name, groups)

    def _put_slice(self, fn, own: str, name: str, groups: list) -> bool:
        if self.current_id is None:
            return False
        data = self.store.get(self.current_id).data
        new, remarks = fn(data, name, groups)
        if new is None:
            self._refuse_word("named_slice", remarks, (own, f"named slice {name.strip()}"))
            return False
        self._save_edit(new, dictionary=True)
        return True

    def _refuse_word(self, what: str, remarks: list, own: str | tuple[str, ...]) -> None:
        """Show a refused dictionary edit under its table: remarks of the edited word itself
        without their place, the others with it.

        :param own: the place of the edited word's own remarks, or several such places.
        """
        owns = own
        if isinstance(own, str):
            owns = (own,)
        texts = []
        for r in remarks:
            if r.where in owns:
                texts.append(r.text)
            else:
                texts.append(str(r))
        line, _, places = "; ".join(texts).partition("\n")
        rest = []
        if places:
            rest = places.split("\n")
        self.dictionary.show_refusal(what, line, rest)

    def _save_edit(self, data: dict, dictionary: bool = False) -> None:
        """Write an accepted edit and refill every tab, keeping its view.

        The amber line of the Dictionary tab names the variants that got errors after a
        dictionary edit; a variant leaves it when an edit of any kind removes its error.

        :param dictionary: whether the edit came from the Dictionary tab.
        """
        before = set(self.store.get(self.current_id).errors)
        self.store.save(self.current_id, data)
        self._update_note()
        project = self.store.get(self.current_id)
        for page in (self.dictionary, self.norm, self.comparison, self.chains):
            page.show_project(project, keep=True)
        amber = []
        for code in project.errors:
            fresh = dictionary and code not in before
            if fresh or code in self._amber:
                amber.append(code)
        self._amber = amber
        self.dictionary.show_amber(amber)

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
        self.statusBar().showMessage(self.tr("Loaded {name}").format(name=Path(path).name))
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
        self.statusBar().showMessage(
            self.tr("Loaded {name} over the project").format(name=Path(path).name)
        )
        return True

    def load_text(self, text: str) -> tuple[bool, str | list[str]]:
        """Load a project from an AI answer as a new project, like a loaded file.

        :param text: the pasted answer; its JSON object is taken out of it.
        :return: ``(True, status message)``, ``(False, message)`` when no JSON is found,
            or ``(False, remark lines)``.
        :rtype: tuple[bool, str | list[str]]
        """
        found = extract_json(text)
        if found is None:
            return False, translate("MainWindow", NO_JSON)
        project, remarks = parse_text(found)
        if project is None:
            return False, [str(r) for r in remarks]
        self.remarks_panel.hide()
        self.refresh(self.store.add(project))
        self._offer(project)
        message = self.tr("Loaded {name}").format(name=project.name)
        self.statusBar().showMessage(message)
        return True, message

    def show_example(self) -> None:
        """Add the example unless it is in the list, select it and open the Comparison tab."""
        present = next((i.id for i in self.store.list() if i.name == EXAMPLE_NAME), None)
        if present is None:
            self.refresh(add_example(self.store))
            message = self.tr("Added {name}").format(name=EXAMPLE_NAME)
        else:
            self.refresh(present)
            message = self.tr("Example is already in the list")
        self.tabs.setCurrentWidget(self.comparison)
        self.statusBar().showMessage(message)

    def ai_scenario(self) -> AiScenarioDialog:
        """The AI scenario screen, not yet shown: the same one until an answer loads."""
        if self._scenario is None:
            self._scenario = AiScenarioDialog(self.load_text, self)
            self._scenario.accepted.connect(self._scenario_done)
        return self._scenario

    def _scenario_done(self) -> None:
        self._scenario = None

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
        self.statusBar().showMessage(self.tr("Created {name}").format(name=project.name))
        return True

    def save_path(self, path: Path) -> None:
        """Write the selected project's file."""
        Path(path).write_text(self.store.text(self.current_id), encoding="utf-8")
        self.statusBar().showMessage(self.tr("Saved {name}").format(name=Path(path).name))

    def copy_project(self) -> None:
        """Copy the selected project and select the copy."""
        if self.current_id is not None:
            self.refresh(self.store.copy(self.current_id))

    def delete_project(self) -> None:
        """Delete the selected project after confirmation."""
        if self.current_id is None:
            return
        question = self.tr("Delete the project “{name}”? This cannot be undone.")
        if not self.confirm(question.format(name=self.projects.currentText())):
            return
        self.store.delete(self.current_id)
        self.refresh()

    def confirm(self, text: str) -> bool:
        """Ask yes or no."""
        answer = QMessageBox.question(self, "Measure Twice", text)
        return answer == QMessageBox.StandardButton.Yes

    def warn(self, text: str) -> None:
        """Show a problem."""
        QMessageBox.warning(self, "Measure Twice", text)

    def ask_name(self, text: str) -> str | None:
        """Ask the name of a new project; ``None`` when cancelled."""
        name, ok = QInputDialog.getText(
            self, self.tr("Project name"), self.tr("Project name:"), text=text
        )
        return name if ok else None

    # --- actions with file dialogs

    def on_new(self) -> None:
        name = self.ask_name(NEW_NAME)
        if name is not None:
            self.new_project(name)

    def on_ai(self) -> None:
        dialog = self.ai_scenario()
        if dialog.exec() == AiScenarioDialog.DialogCode.Accepted:
            dialog.deleteLater()

    def on_paste(self) -> None:
        dialog = PasteDialog(self.load_text, self)
        dialog.exec()
        dialog.deleteLater()

    def on_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Load project file"), "", translate("MainWindow", JSON_FILTER)
        )
        if path:
            self.load_path(Path(path))

    def on_load_over(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Load over the selected project"),
            "",
            translate("MainWindow", JSON_FILTER),
        )
        if path:
            self.load_over_path(Path(path))

    def on_save(self) -> None:
        name = f"{self.projects.currentText() or 'project'}.json"
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Save project file"), name, translate("MainWindow", JSON_FILTER)
        )
        if path:
            try:
                self.save_path(Path(path))
            except OSError as exc:
                self.warn(self.tr("Cannot write the file: {error}").format(error=exc))

    def on_export(self, suffix: str) -> None:
        what = self.tr("Markdown (*.md)") if suffix == ".md" else self.tr("CSV (*.csv)")
        name = f"{self.projects.currentText() or 'comparison'}{suffix}"
        path, _ = QFileDialog.getSaveFileName(self, self.tr("Export comparison"), name, what)
        if not path:
            return
        p = Path(path)
        if p.suffix.lower() != suffix:
            p = p.with_name(p.name + suffix)
        try:
            self.comparison.export_path(p)
            self.statusBar().showMessage(self.tr("Exported {name}").format(name=p.name))
        except OSError as exc:
            self.warn(self.tr("Cannot write the file: {error}").format(error=exc))

    def on_report(self) -> None:
        project = self.comparison._project
        if project is None:
            return
        dialog = ReportDialog(project, lambda pages, ways: self.save_report(pages, ways), self)
        dialog.exec()
        dialog.deleteLater()

    def save_report(self, pages: list[str], ways: list[str]) -> bool:
        """Ask for the PDF file and write the report of the chosen pages and ways.

        :return: ``True`` when the file is written.
        """
        name = f"{self.projects.currentText() or 'report'}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Save PDF report"), name, self.tr("PDF (*.pdf)")
        )
        if not path:
            return False
        p = Path(path)
        if p.suffix.lower() != ".pdf":
            p = p.with_name(p.name + ".pdf")
        try:
            report.write(self.comparison._project, p, chosen=pages, ways=ways)
        except (OSError, ValueError) as exc:
            self.warn(self.tr("Cannot write the report: {error}").format(error=exc))
            return False
        self.statusBar().showMessage(self.tr("Saved {name}").format(name=p.name))
        return True


def build_window(store: Store, settings: QSettings, select: int | None = None) -> MainWindow:
    """Build the window, opening a given project on the Comparison tab.

    :param store: the project store.
    :param settings: application settings.
    :param select: id of the project to open, or ``None`` for the last used one.
    :return: the window.
    :rtype: MainWindow
    """
    if select is not None:
        settings.setValue(LAST, select)
    return MainWindow(store, settings)


def carry_settings(new: QSettings, old: QSettings) -> None:
    """Copy the settings of the old program name once; the old ones stay in place.

    :param new: the settings of Measure Twice; copied into only when they have no keys.
    :param old: the settings of the old program name.
    """
    if new.allKeys():
        return
    for key in old.allKeys():
        new.setValue(key, old.value(key))
    new.sync()


def main() -> int:
    """Run the window over the default store."""
    app = QApplication.instance() or QApplication(sys.argv)
    store = Store(default_path())
    settings = QSettings("measure_twice", "measure_twice")
    carry_settings(settings, QSettings("procnorm", "procnorm"))
    lang = i18n.read_language(settings)
    i18n.write_language(settings, lang)  # the first start keeps the language it chose
    i18n.build_qm()
    i18n.apply_language(app, lang)
    window = build_window(store, settings, first_run(store, settings))
    window.show()
    try:
        return app.exec()
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
