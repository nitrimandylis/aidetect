"""
Build the human half of the calibration set from scanned IB Extended Essays.

The IBO "50 Excellent Extended Essays" PDFs are page images: pdftotext gets the
running header and nothing else. So the pipeline is render -> OCR -> rebuild
paragraphs from geometry -> pick the cleanest three per essay.

    pdftoppm -r 200 -gray -png essay.pdf page
    ./ocr page-*.png > essay.tsv
    python3 build_corpus.py --tsv-dir scans/tsv --out-dir ../corpora/human --prefix h

Three paragraphs per essay, not one, because the desklib amber band is fitted on
the 90th percentile of human window scores and twelve windows cannot support a
percentile. Three, not more, because ~8% of a 4000-word essay is a defensible
excerpt and more is not. They are drawn one per third of the body so the class
carries the same register spread a real essay does.

Nothing here edits prose. It selects, and it strips one specific OCR artifact
(see FOOTNOTE_MARKERS). Letting a model tidy the text would put model-shaped
writing into the human class, which is the same poisoning generate.py refuses
for the AI class, mirrored and worse.
"""

import argparse
import hashlib
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from aidetect.text import END_HEADINGS  # noqa: E402  same rule the counter uses

PAGEBREAK = "---PAGEBREAK---"

# Vision returns lines. In a justified academic scan the only reliable paragraph
# signal is the vertical gap: measured on English_1, body lines step 0.029 of
# page height and a paragraph break 0.061. Indentation is not usable (0.1622 vs
# 0.1643 is noise). 1.5x the median step sits comfortably between the two.
PARAGRAPH_GAP = 1.5
# A line ending well short of the measure is the last line of a paragraph.
SHORT_LINE = 0.85
# Same-line runs: Vision splits a line into several observations when a
# superscript interrupts it, so runs within this fraction of page height are
# one line.
SAME_LINE = 0.008
# Running headers and footers live in these margins.
HEADER_Y, FOOTER_Y = 0.93, 0.07

# Footnote superscripts fuse to the preceding word when OCR'd. Measured forms
# on English_1 page 8: 'family" 4', 'love"s', 'summer°', 'anticipation"|?',
# 'walnuts"|8' — footnotes 4 to 8. Every rule here is anchored to a closing
# quote or a word end so scientific notation (H2O, 3n+1, 25°C) survives.
# THESE MUST BE A NO-OP ON THE 24 EXISTING SAMPLES — see verify_noop().
FOOTNOTE_MARKERS = [
    # After a closing quote: a run of digits and the glyphs OCR turns
    # superscripts into. 'I' and 'l' are deliberately NOT in the class: they
    # would eat the pronoun in `she said "no" I left`.
    re.compile(r"([\"\u201d])\s*['|\u2019`]*\s*[\d?*s\u00b0]{1,3}(?=[\s.,;:?!]|$)"),
    # The marker OCR'd as apostrophes only: `Highbury"''`
    re.compile(r"([\"\u201d])['\u2019`|]{1,3}(?=[\s.,;:?!]|$)"),
    # The closing quote itself was lost: `summer\u00b0,`
    re.compile(r"(?<=[a-z])[\u00b0\u00ba](?=[\s.,;:?!]|$)"),
    re.compile(r"[\u2070-\u209f]+"),
]

# OCR junk a writer never types. Used to RANK candidates, never to reject:
# a hard threshold false-positived on 5 of the 24 known-clean samples.
STRAY_GLYPHS = re.compile(r"[|¬~¦°]")
FUSED_DIGIT = re.compile(r"[A-Za-z]\d|\d[A-Za-z]")
SHREDDED = re.compile(r"(?:\b\w\b[ .]){3,}")

MIN_WORDS, MAX_WORDS = 60, 160

# The subject comes from the PDF's filename, and the IBO collection misspells
# one of them ("Mathmatics_1.pdf"). The corpus should record the subject, not
# the archive's typo.
SUBJECT_SPELLINGS = {"Mathmatics": "Mathematics"}


def strip_markers(text):
    """Remove OCR'd footnote superscripts. Keeps the quote, drops the marker."""
    for pattern in FOOTNOTE_MARKERS:
        text = pattern.sub(lambda m: m.group(1) if m.groups() else "", text)
    text = re.sub(r"\s+([.,;:?!])", r"\1", text)   # marker sat between word and stop
    return re.sub(r"\s+", " ", text).strip()


def read_tsv(path):
    """Parse an ocr.swift TSV into pages of (text, x, y, width, confidence)."""
    pages, current = [], []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line == PAGEBREAK:
            pages.append(current)
            current = []
            continue
        parts = line.split("\t")
        if len(parts) != 5:
            continue
        text, x, y, w, conf = parts
        current.append((text, float(x), float(y), float(w), float(conf)))
    if current:
        pages.append(current)
    return pages


def merge_lines(runs):
    """Group text runs into lines by y, ordered top to bottom, left to right.

    Vision emits a superscript as its own run, which splits the line it sits in
    into three observations. Merging by y puts them back together.
    """
    lines = []
    for text, x, y, w, _conf in sorted(runs, key=lambda r: (-r[2], r[1])):
        if lines and abs(lines[-1]["y"] - y) < SAME_LINE:
            lines[-1]["parts"].append((x, text))
            lines[-1]["right"] = max(lines[-1]["right"], x + w)
            lines[-1]["left"] = min(lines[-1]["left"], x)
        else:
            lines.append({"y": y, "left": x, "right": x + w, "parts": [(x, text)]})
    for line in lines:
        line["text"] = " ".join(t for _x, t in sorted(line["parts"]))
        line["width"] = line["right"] - line["left"]
    return lines


def find_running_text(pages_lines):
    """Lines that repeat across most pages: the header, title and copyright.

    Returned as a set of normalised strings. The essay title is in here too,
    which is how the manifest gets a topic without anyone typing one.
    """
    counts = {}
    for lines in pages_lines:
        for line in lines:
            if line["y"] > HEADER_Y or line["y"] < FOOTER_Y:
                key = re.sub(r"\s+", " ", line["text"]).strip().lower()
                if len(key) > 8:
                    counts[key] = counts.get(key, 0) + 1
    threshold = max(2, len(pages_lines) // 3)
    return {k for k, n in counts.items() if n >= threshold}


def essay_title(running, pages_lines):
    """The repeated header line that is not the series name or the copyright."""
    skip = ("50 excellent extended essays", "international baccalaureate", "©")
    candidates = [r for r in running if not any(s in r for s in skip)]
    if not candidates:
        return None
    # the longest repeated header line is the essay's own title
    best = max(candidates, key=len)
    for lines in pages_lines:
        for line in lines:
            if re.sub(r"\s+", " ", line["text"]).strip().lower() == best:
                return re.sub(r"\s+", " ", line["text"]).strip()
    return best


def page_paragraphs(lines, running):
    """Body lines of one page, grouped into paragraphs.

    Returns (paragraphs, last_line_is_full_width). The flag tells the caller
    whether the final paragraph runs on to the next page.
    """
    body = []
    for line in lines:
        if line["y"] > HEADER_Y or line["y"] < FOOTER_Y:
            continue                       # header, footer, page number
        key = re.sub(r"\s+", " ", line["text"]).strip().lower()
        if key in running:
            continue
        body.append(line)
    if not body:
        return [], False

    steps = [abs(a["y"] - b["y"]) for a, b in zip(body, body[1:])]
    step = statistics.median(steps) if steps else 0.03
    measure = statistics.median([line["width"] for line in body])

    paragraphs, current = [], [body[0]]
    for previous, line in zip(body, body[1:]):
        gap = abs(previous["y"] - line["y"])
        short = previous["width"] < SHORT_LINE * measure
        if gap > PARAGRAPH_GAP * step or short:
            paragraphs.append(current)
            current = [line]
        else:
            current.append(line)
    paragraphs.append(current)

    tail_full = body[-1]["width"] >= SHORT_LINE * measure
    return [join_lines(p) for p in paragraphs], tail_full


def join_lines(lines):
    """One paragraph's lines into a string, undoing end-of-line hyphenation."""
    out = ""
    for line in lines:
        text = line["text"].strip()
        if out.endswith("-"):
            out = out[:-1] + text          # hyphen was a line break, not a word
        elif out:
            out += " " + text
        else:
            out = text
    return re.sub(r"\s+", " ", out).strip()


def document_paragraphs(pages_lines, running):
    """Every body paragraph of the essay, joined across page breaks."""
    paragraphs = []
    carry = False
    for lines in pages_lines:
        page, tail_full = page_paragraphs(lines, running)
        if not page:
            continue
        if carry and paragraphs:
            paragraphs[-1] = join_lines([{"text": paragraphs[-1]}, {"text": page[0]}])
            page = page[1:]
        paragraphs.extend(page)
        carry = tail_full
    return paragraphs


def is_heading_line(text, keywords):
    """True if this line is a real section heading, not a contents entry.

    A contents page lists the same words: `Introduction ....... 3` and
    `References .......... 20`. Matching those collapsed Psychology_1 to a
    single paragraph, because the start was set on one contents line and the
    end on another two lines below it. A real heading is short and carries no
    page number or dot leader.
    """
    stripped = text.strip()
    if len(stripped.split()) > 5:
        return False
    if "..." in stripped or re.search(r"\d\s*$", stripped):
        return False
    lowered = stripped.lower()
    for keyword in keywords:
        if lowered.startswith(keyword):
            return True
    return False


def body_slice(paragraphs):
    """Drop the front matter and everything from the bibliography on.

    Front matter is the cover page, abstract and contents. The abstract is real
    student prose but it is a summary, a different register from body prose and
    not what `generate.py` is asked to imitate, so it stays out.
    """
    start = None
    for index, paragraph in enumerate(paragraphs[:40]):
        if is_heading_line(paragraph, ["introduction"]):
            start = index + 1        # keep scanning: the contents page lists it
    if start is None:                # no heading found, skip front matter by position
        start = min(6, len(paragraphs) // 6)

    end = len(paragraphs)
    for index in range(start, len(paragraphs)):
        if is_heading_line(paragraphs[index], END_HEADINGS):
            end = index
            break

    # A body of almost nothing means the slice went wrong, not that the essay
    # is empty. Better to keep too much and let the damage ranking sort it out.
    if end - start < 5:
        return paragraphs[start:]
    return paragraphs[start:end]


def damage(text):
    """How much this paragraph looks like an OCR accident. Lower is better.

    A ranking, not a test. A hard threshold on these signals rejected 5 of the
    24 known-clean samples, because 'H2O' and 'kbps' look exactly like damage.
    With 25-plus body paragraphs per essay and three wanted, ranking beats
    thresholding: the junk sorts to the bottom and never gets picked.
    """
    score = 3 * len(STRAY_GLYPHS.findall(text))
    score += len(FUSED_DIGIT.findall(text))
    score += 2 * len(SHREDDED.findall(text))
    score += text.count('"') % 2                        # unbalanced quote
    if not re.search(r"[.!?][\"”)]?$", text):
        score += 5                                      # truncated end
    if not re.match(r"^[\"“A-Z]", text):
        score += 5                                      # truncated start
    return score


def pick(paragraphs, per_essay=3):
    """The cleanest paragraph from each third of the body.

    One per third so the class carries the register spread a real essay has:
    a framing paragraph, an analytical one, a closing one. generate.py is given
    the same three positions so the AI class is not uniformly mid-essay.
    """
    usable = [(i, p) for i, p in enumerate(paragraphs)
              if MIN_WORDS <= len(p.split()) <= MAX_WORDS
              and re.match(r'^["\u201cA-Z]', p)          # not a page-break fragment
              and re.search(r'[.!?]["\u201d)]?$', p)]
    if not usable:
        return []
    positions = ["introduction", "analysis", "conclusion"]
    chosen, size = [], len(usable) / per_essay
    for slot in range(per_essay):
        third = usable[int(slot * size):int((slot + 1) * size)] or usable
        best = min(third, key=lambda ip: (damage(ip[1]), -len(ip[1].split())))
        if best[0] not in [c[0] for c in chosen]:
            chosen.append((best[0], best[1], positions[slot]))
    return chosen


def verify_noop(folder):
    """The strip rules must not touch text already known to be clean.

    The 24 existing samples were hand-picked and carry no OCR damage, so any
    edit to them means a rule is too greedy. This is the only check the strip
    regexes get, and it is the one that matters.
    """
    import glob
    changed = []
    for path in sorted(glob.glob(os.path.join(folder, "*.txt"))):
        original = re.sub(r"\s+", " ", open(path, encoding="utf-8").read()).strip()
        if strip_markers(original) != original:
            changed.append(path)
    return changed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--tsv-dir", required=True, help="folder of <essay>.tsv from ocr.swift")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--prefix", default="h")
    ap.add_argument("--subjects", nargs="*", default=None,
                    help="only essays whose filename starts with one of these")
    ap.add_argument("--per-essay", type=int, default=3)
    ap.add_argument("--known-clean",
                    default=os.path.join(os.path.dirname(__file__), "..", "tests",
                                         "fixtures", "known_clean"),
                    help="samples proven free of OCR damage; the strip rules must not "
                         "touch them. Kept outside corpora/ so rebuilding the corpus "
                         "cannot quietly erase this guarantee.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    changed = verify_noop(args.known_clean)
    if changed:
        raise SystemExit("strip rules edit known-clean samples, they are too greedy:\n  " +
                         "\n  ".join(changed))
    print(f"strip rules verified as a no-op on the existing samples")

    import glob
    tsvs = sorted(glob.glob(os.path.join(args.tsv_dir, "*.tsv")))
    if args.subjects:
        tsvs = [t for t in tsvs
                if any(os.path.basename(t).startswith(s) for s in args.subjects)]
    if not tsvs:
        raise SystemExit(f"no .tsv files in {args.tsv_dir}")

    os.makedirs(args.out_dir, exist_ok=True)
    manifest, number = [], 0
    for tsv in tsvs:
        name = os.path.splitext(os.path.basename(tsv))[0]
        pages = read_tsv(tsv)
        pages_lines = [merge_lines(p) for p in pages if p]
        running = find_running_text(pages_lines)
        title = essay_title(running, pages_lines)
        paragraphs = body_slice(document_paragraphs(pages_lines, running))
        picked = pick([strip_markers(p) for p in paragraphs], args.per_essay)
        if len(picked) < args.per_essay:
            print(f"  {name}: only {len(picked)} usable paragraphs of {len(paragraphs)}, skipped")
            continue
        number += 1
        subject = re.sub(r"_\d+$", "", name).replace("_", " ")
        subject = SUBJECT_SPELLINGS.get(subject, subject)
        for letter, (index, text, position) in zip("abc", picked):
            sample_id = f"{args.prefix}{number:02d}{letter}"
            if not args.dry_run:
                with open(os.path.join(args.out_dir, f"{sample_id}.txt"), "w",
                          encoding="utf-8") as f:
                    f.write(text + "\n")
            manifest.append({
                "id": sample_id,
                "source_essay": name,
                "position": position,
                "paragraph_index": index,
                "subject": subject,
                "topic": title or subject,
                "source_url": f"https://web.archive.org/web/2018id_/https://www.easthartford.org/uploaded/ciba/{name}.pdf",
                "date_evidence": ("IBO '50 Excellent Extended Essays'; "
                                  "'(c) International Baccalaureate Organization 2008' printed on every "
                                  "page and PDF CreationDate 2008; Wayback captures predate 2020."),
                "extraction": ("scanned PDF, 200 dpi, transcribed with macOS Vision OCR, paragraphs "
                               "rebuilt from line geometry, footnote superscripts stripped, "
                               "selected by lowest OCR-damage score within its third of the body"),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "words": len(text.split()),
            })
        print(f"  {name}: {len(paragraphs)} body paragraphs -> {args.per_essay} samples  [{title}]")

    if not args.dry_run:
        with open(os.path.join(args.out_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
    print(f"\n{len(manifest)} samples from {number} essays -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
