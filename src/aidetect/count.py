"""
IB word count for a draft.

Word's own count is wrong for IB: it counts the cover page, the contents page,
headings, figure captions, tables and footnotes, none of which are assessed.
This counts what the IB counts, and splits the total by section so an over-long
draft says WHERE.

Excluded, per the IB rules common to the EE and the subject IAs:
  - the cover page             (everything before the first heading)
  - the contents page          (the Table of Contents section)
  - headings                   (skipped by style)
  - figure and table captions  ("Figure 3: ..." — the colon is required)
  - tables and footnotes       (python-docx never puts them in doc.paragraphs)
  - the bibliography onward    (stop at the Bibliography/Works Cited heading)
  - in-text citations          (parentheticals containing a year / ibid / et al)

Block quotes and bullet lists in the body DO count: they are assessed prose.

    aidetect count draft.docx
    aidetect count draft.docx --limit 4000
    aidetect count draft.docx --limit 4000 --json
"""

import argparse
import json
import re

from .text import has_headings, walk

# A parenthetical is a citation if it carries a 4-digit year, "ibid" or "et al".
# ponytail: narrow on purpose. "(the second of these)" is prose and stays counted;
# widening this to every parenthetical would silently eat hundreds of real words.
CITATION = re.compile(
    r"\((?:[^()]*(?:\b(?:1[6-9]|20)\d{2}\b|\bibid\b|\bet al\b)[^()]*)\)",
    re.IGNORECASE,
)


def count_words(text):
    """Words in one paragraph, with in-text citations removed.

    Tokens with no letter or digit are dropped: removing "(Smith, 2024)" from
    "...sharply (Smith, 2024)." strands the full stop as its own token, and a
    lone "." is not a word.
    """
    stripped = CITATION.sub(" ", text)
    return sum(1 for token in stripped.split() if any(c.isalnum() for c in token))


def count_docx(path):
    """Return (sections, total).

    sections is a list of (level, title, words), in document order. `words` is
    that heading's OWN words, never its children's, so sum(words) == total and
    nothing double-counts. The rollup is a display concern, see rolled_up().
    """
    sections = []
    for level, title, text in walk(path):
        if text is None:
            sections.append((level, title, 0))   # a heading announcing itself
            continue
        if not sections:
            # Only reachable for a headingless draft, which the walker counts
            # whole and gives a single stand-in title.
            sections.append((level, title, 0))
        open_level, open_title, words = sections[-1]
        sections[-1] = (open_level, open_title, words + count_words(text))

    total = sum(words for _level, _title, words in sections)
    rolled = rolled_up(sections)
    # A section with no words of its own AND no children said nothing. A parent
    # with children keeps its row so the children have something to hang under.
    sections = [s for s, r in zip(sections, rolled) if r > 0]
    return sections, total


def rolled_up(sections):
    """Each section's words including every section nested under it.

    A section owns the ones that follow it until a heading at its own level or
    higher shows up: Heading 1 'Analysis' owns the Heading 2s and Heading 3s
    after it, and stops at the next Heading 1.
    """
    totals = []
    for i, (level, _title, words) in enumerate(sections):
        running = words
        for deeper_level, _t, deeper_words in sections[i + 1:]:
            if deeper_level <= level:
                break
            running += deeper_words
        totals.append(running)
    return totals


def report(sections, total, limit, whole_document=False):
    rolled = rolled_up(sections)
    labels = ["  " * (level - 1) + title for level, title, _w in sections]
    width = max((len(label) for label in labels), default=10)
    width = max(width, len("TOTAL"))
    for label, words in zip(labels, rolled):
        share = words / total if total else 0
        print(f"  {label:<{width}}  {words:>5}  {'#' * round(share * 30)}")
    print("-" * (width + 40))
    if limit:
        over = total - limit
        verdict = f"{over:+d} over" if over > 0 else f"{-over} to spare"
        print(f"  {'TOTAL':<{width}}  {total:>5}  / {limit} limit, {verdict}")
    else:
        print(f"  {'TOTAL':<{width}}  {total:>5}")
    print("excludes the cover page, contents, headings, captions, tables, "
          "footnotes, citations and everything from the bibliography on.")
    print("indented rows are counted inside the section above them, not on top of it.")
    if whole_document:
        print("note: this draft has no headings, so nothing could be excluded "
              "as a cover page.")


def as_json(sections, total, limit):
    """The machine interface. Every key is always present; `null` means the
    question does not apply, not that it could not be answered. A draft with no
    prose is an empty list and exit 0, because parsing succeeded and the honest
    answer is zero.

    `words` is own-words-only, so sum(words) == total. Roll up yourself with
    `level` if you want subtotals; adding them here would double-count.
    """
    return {
        "sections": [{"title": t, "words": w, "level": lv} for lv, t, w in sections],
        "total": total,
        "limit": limit,
        "over": None if limit is None else total - limit,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(prog="aidetect count",
                                 description="IB-rules word count for a draft.")
    ap.add_argument("path", help=".docx file to count")
    ap.add_argument("--limit", type=int, default=None,
                    help="word limit to measure against (e.g. 4000 for the EE)")
    ap.add_argument("--json", action="store_true",
                    help="emit one JSON object on stdout instead of the table")
    args = ap.parse_args(argv)

    if not args.path.lower().endswith(".docx"):
        ap.error("count needs a .docx (styles are how it finds headings); "
                 "re-save the file as .docx first")

    sections, total = count_docx(args.path)

    if args.json:
        print(json.dumps(as_json(sections, total, args.limit)))
        return
    if not sections:
        print("No prose found. Check the file is a draft and not an outline.")
        return
    report(sections, total, args.limit, whole_document=not has_headings(args.path))
