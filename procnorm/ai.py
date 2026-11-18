# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""The request text for an AI chat and the JSON object taken out of its answer."""

from __future__ import annotations

import re
from pathlib import Path

INSTRUCTIONS_FILE = Path(__file__).parent / "data" / "ai_instructions_en.md"

# A fenced block: an optional language word on the opening line, the content, the closing fence.
_FENCE = re.compile(r"```([A-Za-z]*)[ \t]*\r?\n(.*?)```", re.DOTALL)


def instructions() -> str:
    """The instructions for the AI chat: the input format description.

    :return: the text of the packaged instructions file.
    :rtype: str
    """
    return INSTRUCTIONS_FILE.read_text(encoding="utf-8")


def request_text(description: str) -> str:
    """The full text to paste into an AI chat.

    :param description: the user's description of the process.
    :return: the instructions, a blank line, the line ``My process:`` and the description.
    :rtype: str
    """
    head = instructions().rstrip("\n")
    return f"{head}\n\nMy process:\n{description}"


def _fenced(text: str) -> str | None:
    """The content of the first ``json`` block, or of a plain block that starts with ``{``."""
    for match in _FENCE.finditer(text):
        language = match.group(1).lower()
        content = match.group(2).strip()
        if language == "json":
            return content
        if language == "" and content.startswith("{"):
            return content
    return None


def _first_object(text: str) -> str | None:
    """The first ``{`` up to its matching ``}``, braces inside JSON strings not counted."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        char = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def extract_json(text: str) -> str | None:
    """Take the JSON object out of an AI chat answer.

    :param text: the pasted answer.
    :return: the JSON text, or ``None`` when nothing is found.
    :rtype: str | None
    """
    fenced = _fenced(text)
    if fenced is not None:
        return fenced
    return _first_object(text)
