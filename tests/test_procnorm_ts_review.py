"""Tests of the customer review table built from a Qt `.ts` file or from two texts."""

import re

from tools.ts_review import (
    pair_paragraphs,
    parse_ts,
    render_html,
    split_paragraphs,
)

TS = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="ru_RU">
<context>
    <name>First</name>
    <message>
        <location filename="../ui/a.py" line="1"/>
        <source>Open &lt;file&gt; &amp; close</source>
        <translation>Открыть &lt;файл&gt; &amp; закрыть</translation>
    </message>
    <message numerus="yes">
        <location filename="../ui/a.py" line="2"/>
        <source>%n remark</source>
        <translation>
            <numerusform>%n замечание</numerusform>
            <numerusform>%n замечания</numerusform>
            <numerusform>%n замечаний</numerusform>
        </translation>
    </message>
</context>
<context>
    <name>Second</name>
    <message>
        <location filename="../ui/b.py" line="3"/>
        <source>Cancel</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/b.py" line="4"/>
        <source>Run</source>
        <translatorcomment>Button, like "Запуск" in other programs</translatorcomment>
        <translation>Запустить</translation>
    </message>
</context>
</TS>
"""


def cells(html):
    """Return the rows of the main table as lists of unescaped-free cell texts."""
    rows = re.findall(r"<tr>(.*?)</tr>", html, re.S)
    return [re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S) for row in rows]


def test_parse_keeps_order_and_texts():
    rows = parse_ts(TS)
    assert [row["source"] for row in rows] == [
        "Open <file> & close",
        "%n remark",
        "Cancel",
        "Run",
    ]
    assert rows[0]["translation"] == "Открыть <файл> & закрыть"
    assert rows[1]["translation"] == "%n замечание | %n замечания | %n замечаний"
    assert rows[2]["translation"] == ""
    assert rows[3]["comment"] == 'Button, like "Запуск" in other programs'
    assert rows[0]["comment"] == ""


def test_table_numbers_and_escaping():
    body = cells(render_html(parse_ts(TS), "Review"))
    assert [row[0] for row in body[1:]] == ["1", "2", "3", "4"]
    assert body[1][1] == "Open &lt;file&gt; &amp; close"
    assert body[1][2] == "Открыть &lt;файл&gt; &amp; закрыть"
    assert "<file>" not in render_html(parse_ts(TS), "Review")


def test_table_has_utf8_auto_direction_and_phone_viewport():
    html = render_html(parse_ts(TS), "Review")
    assert '<meta charset="utf-8">' in html
    assert 'name="viewport"' in html
    assert 'dir="auto"' in html
    assert "overflow-x" in html


def test_unfinished_is_marked_empty():
    html = render_html(parse_ts(TS), "Review")
    assert html.count('class="empty"') == 1


def test_split_paragraphs_by_blank_lines():
    text = "First line\ncontinues\n\n\n  \nSecond\n\nThird\n"
    assert split_paragraphs(text) == ["First line\ncontinues", "Second", "Third"]


def test_pair_paragraphs_with_comments_and_shortage():
    rows = pair_paragraphs("A\n\nB\n\nC", "Я\n\nБ", "note")
    assert [row["source"] for row in rows] == ["A", "B", "C"]
    assert [row["translation"] for row in rows] == ["Я", "Б", ""]
    assert [row["comment"] for row in rows] == ["note", "", ""]
    rows = pair_paragraphs("A\n\nB", "Я\n\nБ")
    assert [row["comment"] for row in rows] == ["", ""]


def test_paragraph_view_escapes():
    html = render_html(pair_paragraphs("a <b> & c", "x"), "Review")
    assert "a &lt;b&gt; &amp; c" in html
