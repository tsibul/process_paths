# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""Texts of the core that the window translates when it shows them; no Qt here.

A :class:`Message` is the English text itself (a ``str``: the command line prints it, tests and
code compare it as before) that also keeps its template, the context of the translation and the
substitutions. The window translates the template and fills in the substitutions translated in
turn (``measure_twice.i18n.shown``).

The templates are marked with :func:`QT_TRANSLATE_NOOP` and, for a count, :func:`translate`:
`lupdate` reads these names in the source without any import of Qt. A template takes named
substitutions in braces, ``str.format`` style; a count is ``%n``.
"""

from __future__ import annotations


class Message(str):
    """An English text with what it takes to translate it.

    :ivar context: the context of the translation; ``None`` for a template that is not translated
        (only its substitutions are).
    :ivar template: the English template.
    :ivar args: the substitutions, ``{name: text}``; a substitution may be a message itself.
    :ivar n: the count put in for ``%n``, or ``None``.
    """

    context: str | None
    template: str
    args: dict
    n: int | None

    def __new__(cls, value: str, context: str | None = None, template: str | None = None,
                args: dict | None = None, n: int | None = None) -> Message:
        self = super().__new__(cls, value)
        self.context = context
        self.template = value if template is None else template
        self.args = dict(args or {})
        self.n = n
        return self

    def __reduce__(self):
        return Message, (str(self), self.context, self.template, self.args, self.n)

    def format(self, **args) -> Message:
        """The same template with the substitutions: the English text, ready to translate."""
        return _filled(self.context, self.template, args, self.n)


def _english(template: str, args: dict, n: int | None) -> str:
    if n is not None:
        template = template.replace("%n", str(n))
    if not args:
        return template
    return template.format_map({k: str(v) for k, v in args.items()})


def _filled(context: str | None, template: str, args: dict, n: int | None) -> Message:
    return Message(_english(template, args, n), context, template, args, n)


def QT_TRANSLATE_NOOP(context: str, text: str) -> Message:
    """Mark a template for `lupdate`; substitutions are given later by ``.format``."""
    return Message(text, context)


def translate(context: str, text: str, disambiguation: str = "", n: int = -1) -> Message:
    """Mark a template with a count ``%n`` for `lupdate` (a message with plural forms).

    :param context: the context of the translation.
    :param text: the English template with ``%n``.
    :param disambiguation: unused, the place `lupdate` expects it.
    :param n: the count.
    :return: the message; substitutions are given later by ``.format``.
    :rtype: Message
    """
    return _filled(context, text, {}, n)


def fill(template: str, **args) -> Message:
    """A template that is not translated, with substitutions that may be."""
    return _filled(None, template, args, None)


def joined(sep: str, items) -> Message:
    """The items one after another with ``sep`` between; each item may be a message."""
    items = list(items)
    between = sep.replace("{", "{{").replace("}", "}}")
    template = between.join(f"{{i{i}}}" for i in range(len(items)))
    return _filled(None, template, {f"i{i}": item for i, item in enumerate(items)}, None)
