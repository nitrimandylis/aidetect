"""
Measure what OCR does to a Binoculars score, on the same prose both ways.

The human class is transcribed from scans; the AI class arrives as clean UTF-8
from an API. If OCR noise shifts scores at all, the fitted threshold is partly
detecting "was this text scanned", which generalises to nothing when the tool is
pointed at a typed draft. That is the one failure mode that would make the whole
corpus worthless while making the accuracy number look better, so it gets
measured rather than assumed.

Comparing OCR'd essays against different born-digital essays would confound the
transcription route with the author. This does the paired version instead: take
a born-digital PDF, read its text layer (ground truth), then render the SAME
pages to images and OCR them, and match paragraph to paragraph. Any difference
is the transcription and nothing else.

    python3 ocr_bias.py --pdf b02.pdf b05.pdf --out pairs.json
    python3 ocr_bias.py --score pairs.json --mlx --pair gemma

Only two IB exemplars in the corpus turned out to be born-digital, so this is
tens of paired paragraphs, not hundreds. Enough for a paired comparison of
means, not enough to claim a precise effect size.
"""

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import build_corpus  # noqa: E402

MIN_SIMILARITY = 0.80   # below this the two are not the same paragraph
MIN_WORDS = 40


def clean_paragraphs(pdf_path):
    """Paragraphs from the PDF's own text layer. No OCR involved."""
    with tempfile.TemporaryDirectory() as work:
        txt_path = os.path.join(work, "clean.txt")
        subprocess.run(["pdftotext", pdf_path, txt_path], check=True,
                       capture_output=True)
        raw = open(txt_path, encoding="utf-8", errors="replace").read()

    paragraphs = []
    for block in re.split(r"\n\s*\n", raw):
        text = re.sub(r"\s+", " ", block).strip()
        if len(text.split()) >= MIN_WORDS:
            paragraphs.append(text)
    return paragraphs


def ocr_paragraphs(pdf_path):
    """Paragraphs from OCR of the same pages, through the corpus pipeline."""
    tools = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as work:
        subprocess.run(["pdftoppm", "-r", "200", "-gray", "-png", pdf_path,
                        os.path.join(work, "pg")], check=True, capture_output=True)
        pages = sorted(f for f in os.listdir(work) if f.endswith(".png"))
        tsv_path = os.path.join(work, "out.tsv")
        with open(tsv_path, "w", encoding="utf-8") as tsv:
            subprocess.run([os.path.join(tools, "ocr")] +
                           [os.path.join(work, page) for page in pages],
                           check=True, stdout=tsv)
        pages_of_runs = build_corpus.read_tsv(tsv_path)

    pages_lines = []
    for runs in pages_of_runs:
        if runs:
            pages_lines.append(build_corpus.merge_lines(runs))
    running = build_corpus.find_running_text(pages_lines)

    paragraphs = []
    for text in build_corpus.document_paragraphs(pages_lines, running):
        stripped = build_corpus.strip_markers(text)
        if len(stripped.split()) >= MIN_WORDS:
            paragraphs.append(stripped)
    return paragraphs


def pair_up(clean, scanned):
    """Match each OCR'd paragraph to the clean paragraph it came from.

    Greedy nearest match on difflib ratio. A paragraph the pipeline split or
    joined differently from pdftotext simply fails to match and is dropped:
    a bad pairing would be measured as OCR damage when it is really a layout
    disagreement.
    """
    pairs = []
    used = set()
    for scanned_text in scanned:
        best_index = None
        best_ratio = 0.0
        for index, clean_text in enumerate(clean):
            if index in used:
                continue
            ratio = difflib.SequenceMatcher(None, clean_text, scanned_text).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_index = index
        if best_index is not None and best_ratio >= MIN_SIMILARITY:
            used.add(best_index)
            pairs.append({
                "clean": clean[best_index],
                "ocr": scanned_text,
                "similarity": round(best_ratio, 4),
            })
    return pairs


def character_error_rate(pair):
    """Share of characters the OCR route got wrong, against the text layer."""
    matcher = difflib.SequenceMatcher(None, pair["clean"], pair["ocr"])
    return 1.0 - matcher.ratio()


def build(pdf_paths, out_path):
    everything = []
    for pdf_path in pdf_paths:
        clean = clean_paragraphs(pdf_path)
        scanned = ocr_paragraphs(pdf_path)
        pairs = pair_up(clean, scanned)
        for pair in pairs:
            pair["source"] = os.path.basename(pdf_path)
        print(f"{os.path.basename(pdf_path)}: {len(clean)} clean, "
              f"{len(scanned)} OCR, {len(pairs)} matched")
        everything.extend(pairs)

    if everything:
        rates = []
        for pair in everything:
            rates.append(character_error_rate(pair))
        rates.sort()
        median = rates[len(rates) // 2]
        print(f"\n{len(everything)} paired paragraphs")
        print(f"median character error rate: {median * 100:.2f}%")
        print(f"worst: {max(rates) * 100:.2f}%")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(everything, f, indent=2)
    print(f"saved -> {out_path}")


def score_pairs(pairs_path, args):
    """Score both versions of every pair with Binoculars and compare."""
    from aidetect.binoculars import load_backend, score_text

    pairs = json.load(open(pairs_path, encoding="utf-8"))
    _pair_key, backend, device, tokenizer, observer, performer = load_backend(args)

    clean_scores = []
    ocr_scores = []
    deltas = []
    for index, pair in enumerate(pairs, 1):
        clean_score = score_text(pair["clean"], tokenizer, observer, performer,
                                 device, backend)
        ocr_score = score_text(pair["ocr"], tokenizer, observer, performer,
                               device, backend)
        clean_scores.append(clean_score)
        ocr_scores.append(ocr_score)
        deltas.append(ocr_score - clean_score)
        print(f"  {index:3}/{len(pairs)}  clean {clean_score:.4f}  "
              f"ocr {ocr_score:.4f}  delta {ocr_score - clean_score:+.4f}")

    clean_mean = sum(clean_scores) / len(clean_scores)
    ocr_mean = sum(ocr_scores) / len(ocr_scores)
    mean_delta = sum(deltas) / len(deltas)
    moved_up = 0
    for delta in deltas:
        if delta > 0:
            moved_up += 1

    print(f"\n=== OCR bias on {len(pairs)} paired paragraphs ===")
    print(f"clean mean : {clean_mean:.4f}")
    print(f"OCR mean   : {ocr_mean:.4f}")
    print(f"mean delta : {mean_delta:+.4f}   (positive = OCR reads as MORE human)")
    print(f"OCR scored higher on {moved_up} of {len(pairs)}")

    summary = {
        "n_pairs": len(pairs),
        "clean_mean": round(clean_mean, 4),
        "ocr_mean": round(ocr_mean, 4),
        "mean_delta": round(mean_delta, 4),
        "ocr_higher": moved_up,
    }
    print(json.dumps(summary))
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--pdf", nargs="*", default=None,
                    help="born-digital PDFs to build pairs from")
    ap.add_argument("--out", default="ocr_pairs.json")
    ap.add_argument("--score", default=None, help="score an existing pairs file")
    from aidetect.binoculars import add_backend_args
    add_backend_args(ap)
    args = ap.parse_args(argv)

    if args.score:
        score_pairs(args.score, args)
    elif args.pdf:
        build(args.pdf, args.out)
    else:
        ap.error("pass --pdf to build pairs, or --score to score them")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
