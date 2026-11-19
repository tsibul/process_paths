# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Languages of the window: the stored choice, building and loading `.qm`, the direction.

The sources of translations are ``measure_twice/i18n/measure_twice_<lang>.ts``; the `.qm` files
are built from them into a temporary folder and never kept in the repository.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import (QCoreApplication, QLibraryInfo, QLocale, QProcess, QSettings,
                            QTranslator)

from measure_twice.message import Message, Number

KEY = "language"
SOURCE = "en"  # the language of the strings in the code
# Code and the name of the language in itself, in the order of the switch.
LANGUAGES = {
    "en": "English",
    "ru": "Русский",
    "el": "Ελληνικά",
}
SOURCES = Path(__file__).parent / "i18n"
BUILD = Path(tempfile.gettempdir()) / "measure_twice_qm"

_current = SOURCE
_translators: list[QTranslator] = []


def read_language(settings: QSettings | None, system: str | None = None) -> str:
    """The language of the window.

    :param settings: application settings; ``None`` keeps nothing.
    :param system: the system locale name such as ``ru_RU``; the real one when absent.
    :return: the stored language; without one, the system language if it is known, else English.
    :rtype: str
    """
    stored = settings.value(KEY) if settings is not None else None
    if stored is not None:
        return stored if stored in LANGUAGES else SOURCE
    if system is None:
        system = QLocale.system().name()
    lang = system.split("_")[0]
    return lang if lang in LANGUAGES else SOURCE


def write_language(settings: QSettings, lang: str) -> None:
    """Keep the chosen language for the next start."""
    settings.setValue(KEY, lang)


def _lrelease() -> str | None:
    """The `lrelease` of PySide6: next to the interpreter, else on the path."""
    near = Path(sys.executable).parent / "pyside6-lrelease"
    if near.exists():
        return str(near)
    return shutil.which("pyside6-lrelease")


def build_qm(sources: Path = SOURCES, out: Path = BUILD) -> list[Path]:
    """Build the `.qm` files from the `.ts` sources.

    :param sources: the folder with ``measure_twice_<lang>.ts``.
    :param out: the folder for the `.qm` files; made when absent.
    :return: the built files; none without sources or without `lrelease`.
    :rtype: list[Path]
    """
    ts_files = sorted(sources.glob("measure_twice_*.ts")) if sources.is_dir() else []
    tool = _lrelease()
    if not ts_files or tool is None:
        return []
    out.mkdir(parents=True, exist_ok=True)
    built = []
    for ts in ts_files:
        qm = out / (ts.stem + ".qm")
        done = subprocess.run(
            [tool, "-silent", str(ts), "-qm", str(qm)],
            capture_output=True,
            timeout=60,
        )
        if done.returncode == 0 and qm.exists():
            built.append(qm)
    return built


def apply_language(app: QCoreApplication, lang: str, qm_dir: Path = BUILD) -> None:
    """Make ``lang`` the language of the application: translations, locale, direction.

    The only place where the direction of the window is set. A language without its `.qm`
    shows the English strings of the code.

    :param app: the application.
    :param lang: the language code.
    :param qm_dir: the folder with ``measure_twice_<lang>.qm``.
    """
    global _current
    for old in _translators:
        app.removeTranslator(old)
    _translators.clear()
    if lang != SOURCE:
        qt_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        for name, folder in (("qtbase_" + lang, qt_dir), ("measure_twice_" + lang, str(qm_dir))):
            translator = QTranslator(app)
            if translator.load(name, folder):
                app.installTranslator(translator)
                _translators.append(translator)
    _current = lang
    locale = QLocale(lang)
    QLocale.setDefault(locale)
    app.setLayoutDirection(locale.textDirection())


def current() -> str:
    """The language the window runs in."""
    return _current


def locale() -> QLocale:
    """The locale of the window language, for dates and numbers; numbers without group separators,
    as the core writes them."""
    out = QLocale(_current)
    out.setNumberOptions(QLocale.NumberOption.OmitGroupSeparator)
    return out


def number(text: str) -> str:
    """A number of the core as the window shows it: the decimal separator of the window language.

    :param text: the number written with the point, as :func:`measure_twice.calc.fmt` gives it.
    :return: the text to show.
    :rtype: str
    """
    return str(text).replace(".", locale().decimalPoint())


def shown(text: object) -> str:
    """A text of the core in the language of the window.

    A :class:`~measure_twice.message.Message` has its template translated and its substitutions
    filled in, each translated in turn; a :class:`~measure_twice.message.Number` gets the decimal
    separator of the window language; any other text is shown as it is. A translation that
    lost a substitution shows the English text.

    :param text: a message, a plain text or ``None`` (an empty text).
    :return: the text to show.
    :rtype: str
    """
    if text is None:
        return ""
    if isinstance(text, Number):
        return number(text)
    if not isinstance(text, Message):
        return str(text)
    template = text.template
    if text.context is not None:
        if text.n is None:
            template = QCoreApplication.translate(text.context, template)
        else:
            template = QCoreApplication.translate(text.context, template, "", text.n)
    elif text.n is not None:
        template = template.replace("%n", str(text.n))
    if not text.args:
        return template
    try:
        return template.format_map({k: shown(v) for k, v in text.args.items()})
    except (KeyError, IndexError, ValueError):
        return str(text)


def remark(r) -> str:
    """One remark of the core as a line in the language of the window: ``place: text``."""
    where = shown(r.where)
    text = shown(r.text)
    return f"{where}: {text}" if where else text


def restart() -> None:
    """Start the program again with the same command line and quit this one."""
    QProcess.startDetached(sys.executable, sys.orig_argv[1:], os.getcwd())
    QCoreApplication.quit()
