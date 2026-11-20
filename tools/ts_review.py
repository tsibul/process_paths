"""Build a one-file HTML review table for the customer.

Two views, same four columns (number, English, translation, comment):

* a Qt `.ts` file: one row per message in file order, the comment is taken
  from the `translatorcomment` element;
* two text files (English and translated) split into paragraphs by blank
  lines; an optional third file with comments is split the same way and
  its paragraphs are matched to the rows by position.

Standard library only. The page has no external files, wraps long text
and is readable on a phone (width 375).
"""

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from html import escape
from pathlib import Path

STYLE = """
    :root {
      color-scheme: light dark;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      padding: 12px;
      font: 16px/1.4 system-ui, sans-serif;
      overflow-wrap: anywhere;
    }

    h1 {
      font-size: 1.2rem;
      margin: 0 0 12px;
    }

    .box {
      overflow-x: auto;
    }

    table {
      border-collapse: collapse;
      width: 100%;
    }

    th,
    td {
      border: 1px solid #8884;
      padding: 6px 8px;
      text-align: start;
      vertical-align: top;
      white-space: pre-wrap;
    }

    th {
      background: #8882;
    }

    td.num {
      color: #888;
      white-space: nowrap;
    }

    td.empty {
      background: #fc03;
    }

    @media (max-width: 600px) {
      thead {
        display: none;
      }

      table,
      tbody,
      tr,
      td {
        display: block;
        width: 100%;
      }

      tr {
        border: 1px solid #8886;
        border-radius: 6px;
        margin-bottom: 10px;
      }

      td {
        border: 0;
        border-bottom: 1px solid #8884;
      }

      td::before {
        content: attr(data-label);
        display: block;
        font-size: 0.75rem;
        color: #888;
      }

      td.note:empty {
        display: none;
      }
    }
"""

HEADS = ("№", "English", "Translation", "Comment")


def parse_ts(source):
    """Return rows {source, translation, comment} of a `.ts` text in file order."""
    root = ET.fromstring(source.encode("utf-8"))
    rows = []
    for message in root.iter("message"):
        translation = message.find("translation")
        forms = []
        if translation is not None:
            forms = [form.text or "" for form in translation.findall("numerusform")]
            if not forms:
                forms = [translation.text or ""]
        comment = message.find("translatorcomment")
        rows.append(
            {
                "source": message.findtext("source") or "",
                "translation": " | ".join(forms) if any(forms) else "",
                "comment": (comment.text or "") if comment is not None else "",
            }
        )
    return rows


def split_paragraphs(text):
    """Split a text by blank lines; blank-only parts are dropped."""
    parts = re.split(r"\n\s*\n", text.replace("\r\n", "\n"))
    return [part.strip("\n") for part in parts if part.strip()]


def pair_paragraphs(english, translated, comments=""):
    """Match paragraphs of the texts by position; missing ones stay empty."""
    first = split_paragraphs(english)
    second = split_paragraphs(translated)
    notes = split_paragraphs(comments)
    return [
        {
            "source": text,
            "translation": second[index] if index < len(second) else "",
            "comment": notes[index] if index < len(notes) else "",
        }
        for index, text in enumerate(first)
    ]


def render_row(number, row):
    """One table row; the translation cell has `dir="auto"`."""
    empty = "" if row["translation"] else ' class="empty"'
    translation = escape(row["translation"], quote=False)
    comment = escape(row["comment"], quote=False)
    cells = [
        f'<td class="num" data-label="№">{number}</td>',
        f'<td data-label="English">{escape(row["source"], quote=False)}</td>',
        f'<td dir="auto" data-label="Translation"{empty}>{translation}</td>',
        f'<td class="note" dir="auto" data-label="Comment">{comment}</td>',
    ]
    return "<tr>" + "".join(cells) + "</tr>"


def render_html(rows, title):
    """Return the whole page for the rows, numbered from 1."""
    head = "".join(f"<th>{escape(name)}</th>" for name in HEADS)
    body = "\n".join(render_row(number, row) for number, row in enumerate(rows, 1))
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n"
        f"<style>{STYLE}</style>\n"
        "</head>\n"
        "<body>\n"
        f"<h1>{escape(title)}</h1>\n"
        '<div class="box">\n'
        f"<table>\n<thead><tr>{head}</tr></thead>\n<tbody>\n{body}\n</tbody>\n</table>\n"
        "</div>\n"
        "</body>\n"
        "</html>\n"
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description="Build a one-file HTML review table (number, English, translation, comment).",
        epilog=(
            "Messages view: ts_review.py FILE.ts -o review.html. "
            "Paragraph view: ts_review.py --english en.md --translated ru.md "
            "[--comments notes.md] -o review.html; each file is split by blank lines "
            "and paragraphs are matched by position."
        ),
    )
    parser.add_argument("ts", nargs="?", help="Qt .ts file (messages view)")
    parser.add_argument("--english", help="English text file (paragraph view)")
    parser.add_argument("--translated", help="translated text file (paragraph view)")
    parser.add_argument("--comments", help="optional comments file, one paragraph per row")
    parser.add_argument("-o", "--output", required=True, help="HTML file to write")
    parser.add_argument("--title", help="page title (default: input file name)")
    return parser


def read(path):
    return Path(path).read_text(encoding="utf-8")


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.ts:
        rows = parse_ts(read(args.ts))
        title = args.title or Path(args.ts).name
    elif args.english and args.translated:
        comments = read(args.comments) if args.comments else ""
        rows = pair_paragraphs(read(args.english), read(args.translated), comments)
        title = args.title or Path(args.translated).name
    else:
        parser.error("give a .ts file or both --english and --translated")
    Path(args.output).write_text(render_html(rows, title), encoding="utf-8")
    print(f"{len(rows)} rows -> {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
