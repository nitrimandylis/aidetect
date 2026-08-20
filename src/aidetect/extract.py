"""
Dump a .docx's prose into a plain .txt, then do what you like with the file.

Same paragraphs `aidetect count` counts, so `wc -w` on the output reconciles
against the reported total (modulo in-text citations, which count strips and
this does not). Dropped: the cover page, the contents page, headings, figure
captions, tables, footnotes, and everything from the bibliography on.

No detector filtering happens here. Short paragraphs and quoted passages stay
in, because they are words the examiner counts; `aidetect score` applies its
own filter when it reads the file.

    aidetect extract "draft.docx"              -> "draft prose.txt"
    aidetect extract "draft.docx" out.txt
"""

import argparse
import os

from .text import walk


def default_out_path(in_path):
    """draft.docx -> "draft prose.txt", next to the original."""
    stem = os.path.splitext(in_path)[0]
    return f"{stem} prose.txt"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="aidetect extract",
                                 description="Extract a .docx's prose into a .txt.")
    ap.add_argument("in_path", help="source .docx")
    ap.add_argument("out_path", nargs="?",
                    help="destination .txt (default: '<name> prose.txt')")
    args = ap.parse_args(argv)

    if not args.in_path.lower().endswith(".docx"):
        ap.error("extract needs a .docx (styles are how it finds headings); "
                 "re-save the file as .docx first")

    out_path = args.out_path or default_out_path(args.in_path)
    prose = [text for _level, _title, text in walk(args.in_path) if text is not None]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(prose))
    words = sum(len(p.split()) for p in prose)
    print(f"kept {len(prose)} paragraphs, {words} words -> {out_path}")
    print("note: raw word count. `aidetect count` also strips in-text citations, "
          "so its total is a little lower.")
