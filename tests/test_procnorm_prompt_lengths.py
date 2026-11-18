"""Length limits of the six AI chat prompts in docs/ai_prompts_en.md.

A chat cut a long prompt at about 8,140 characters, so each prompt, with the text
the program fills in, is kept within 6,000 characters.
"""

import re
from pathlib import Path

PROMPTS_FILE = Path(__file__).resolve().parent.parent / "docs" / "ai_prompts_en.md"

PROMPT_LIMIT = 6000
FILE_PROMPT_LIMIT = 5000
TASK_FIELD_CAP = 1000
REMARKS_ROOM = 3000

PROMPT_PATTERN = re.compile(
    r"^## Prompt (\d+)\. [^\n]*\n.*?^```text\n(.*?)^```$",
    re.MULTILINE | re.DOTALL,
)


def read_prompts():
    text = PROMPTS_FILE.read_text(encoding="utf-8")
    prompts = {}
    for match in PROMPT_PATTERN.finditer(text):
        prompts[int(match.group(1))] = match.group(2)
    return prompts


def test_six_prompts():
    assert sorted(read_prompts()) == [1, 2, 3, 4, 5, 6]


def test_each_prompt_within_limit():
    for number, block in read_prompts().items():
        assert len(block) <= PROMPT_LIMIT, (number, len(block))


def test_file_prompt_within_limit():
    block = read_prompts()[5]
    assert len(block) <= FILE_PROMPT_LIMIT, len(block)


def test_task_prompt_with_full_task_within_limit():
    block = read_prompts()[1]
    assert "{task}" in block
    filled = block.replace("{task}", "x" * TASK_FIELD_CAP)
    assert len(filled) <= PROMPT_LIMIT, len(filled)


def test_remarks_prompt_leaves_room():
    block = read_prompts()[6]
    assert "{remarks}" in block
    room = PROMPT_LIMIT - len(block.replace("{remarks}", ""))
    assert room >= REMARKS_ROOM, room
