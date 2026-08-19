"""
Reading prose out of .docx and .txt files. No torch in here on purpose:
`aidetect count` uses this module and should not pay a model import to count words.
"""

MIN_WORDS = 25   # ponytail: skip fragments; short text scores as noise

# Lines that begin with any of these are note-scaffolding, not prose.
NOTE_STARTS = (
    "NOTES", "Verdict", "Analysis:", "Criticism", "Mini-conclusion",
    "Tool definition", "Why chosen", "Overall synthesis", "Force =",
    "POINTS", "Safest", "Moderate", "Research Question", "Word count",
    "Table of Contents",
)
# ponytail: prefix heuristic, not a parser. If a real sentence ever starts
# with one of these words it gets dropped too — check the output if a section vanishes.

# Headings that mean "the prose is over, the rest is citations".
END_HEADINGS = ("bibliography", "works cited", "references")


def is_heading(p):
    return p.style.name.startswith("Heading")


def is_end_heading(p):
    return is_heading(p) and p.text.strip().lower() in END_HEADINGS


def is_prose(p, min_words=MIN_WORDS):
    """True if this python-docx paragraph is finished prose, not scaffolding.

    Tables and footnotes need no handling here: doc.paragraphs excludes table
    cells, and python-docx never exposes footnotes at all. IB excludes both.
    """
    text = p.text.strip()
    if len(text.split()) < min_words:
        return False
    if is_heading(p):
        return False
    if text[0] in "•-*“\"[»":               # bullet, quoted snippet, or [SCAFFOLD]/» note marker
        return False
    if text.startswith(NOTE_STARTS):
        return False
    return True


def read_paragraphs(path, min_words=MIN_WORDS):
    """Pull prose paragraphs out of a .docx or .txt file."""
    if path.lower().endswith(".docx"):
        import docx  # python-docx, only needed for Word files
        doc = docx.Document(path)
        chunks = [p.text for p in doc.paragraphs]
    else:
        with open(path, encoding="utf-8") as f:
            # blank line separates paragraphs in a plain-text file
            chunks = f.read().split("\n\n")
    # keep only real paragraphs, not headings/blanks/fragments
    return [c.strip() for c in chunks if len(c.split()) >= min_words]


def bar(prob, width=20):
    filled = round(prob * width)
    return "#" * filled + "-" * (width - filled)
