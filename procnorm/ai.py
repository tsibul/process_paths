# Copyright (C) 2026 Ilia Tsigelnitskii
# SPDX-License-Identifier: GPL-3.0-or-later

"""The texts for an AI chat: the request, the six prompts; the JSON object taken out of its answer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

INSTRUCTIONS_FILE = Path(__file__).parent / "data" / "ai_instructions_en.md"
PROMPTS_FILE = Path(__file__).parent / "data" / "ai_prompts_en.md"
# No prompt the program hands out is longer, the filled-in text counted.
PROMPT_LIMIT = 6000
TASK = "{task}"
REMARKS = "{remarks}"

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


# A prompt: its heading, the note under it, then its ``text`` block.
_PROMPT = re.compile(
    r"^## Prompt (\d+)\. (.+?)[ \t]*\r?\n(.*?)^```text[ \t]*\r?\n(.*?)^```",
    re.DOTALL | re.MULTILINE,
)


@dataclass(frozen=True)
class Prompt:
    """One step of the AI scenario.

    :param number: the step number.
    :param name: the step name from the heading.
    :param note: when to use the prompt.
    :param text: the prompt to copy into the AI chat.
    """

    number: int
    name: str
    note: str
    text: str


def parse_prompts(text: str) -> list[Prompt]:
    """The prompts of a prompts file.

    :param text: the file text: headings ``## Prompt N. <name>``, a note, a ``text`` block.
    :return: the prompts in file order.
    :rtype: list[Prompt]
    """
    found = []
    for match in _PROMPT.finditer(text):
        note = " ".join(match.group(3).split())
        body = match.group(4).rstrip("\r\n")
        found.append(Prompt(int(match.group(1)), match.group(2), note, body))
    return found


def prompts() -> list[Prompt]:
    """The six prompts of the packaged prompts file.

    :return: the prompts in step order.
    :rtype: list[Prompt]
    """
    return parse_prompts(PROMPTS_FILE.read_text(encoding="utf-8"))


def task_limit() -> int:
    """How long the task may be for prompt 1 to stay within ``PROMPT_LIMIT``.

    :return: the number of characters.
    :rtype: int
    """
    return PROMPT_LIMIT - (len(prompts()[0].text) - len(TASK))


def task_prompt(task: str) -> str:
    """Prompt 1 with the person's task.

    :param task: one or two sentences about the task.
    :return: the prompt text with ``{task}`` replaced.
    :rtype: str
    """
    return prompts()[0].text.replace(TASK, task)


def fit_remarks(remarks: list[str], room: int) -> list[str]:
    """Whole remarks in order, as many as fit, and ``and N more`` for the rest.

    :param remarks: the remark lines.
    :param room: the characters there are for the lines joined by line breaks.
    :return: the lines to write.
    :rtype: list[str]
    """
    if len("\n".join(remarks)) <= room:
        return list(remarks)
    used = 0
    kept = 0
    for line in remarks:
        tail = f"and {len(remarks) - kept - 1} more"
        if used + len(line) + 1 + len(tail) > room:
            break
        used += len(line) + 1
        kept += 1
    return remarks[:kept] + [f"and {len(remarks) - kept} more"]


def remarks_prompt(remarks: list[str]) -> str:
    """Prompt 6 with the load remarks, within ``PROMPT_LIMIT``.

    :param remarks: the remark lines.
    :return: the prompt text with ``{remarks}`` replaced, one remark per line.
    :rtype: str
    """
    text = prompts()[5].text
    room = PROMPT_LIMIT - (len(text) - len(REMARKS))
    return text.replace(REMARKS, "\n".join(fit_remarks(remarks, room)))


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
