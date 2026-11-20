"""Shared test setup: the windows of a test are deleted after it.

A closed window is only hidden, so the windows, dialogs and menus of every test stayed alive till
the end of the run. Qt then deleted them all at the exit, which took longer the more there were:
over two minutes after the summary of the full run. Deleted test by test, they cost little.
"""

import pytest


@pytest.fixture(autouse=True)
def _delete_windows():
    """Delete every top-level widget left after a test, when a ``QApplication`` runs.

    Deleted, not closed: a close could run the window's own close handling.
    """
    yield
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    for widget in app.topLevelWidgets():
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
