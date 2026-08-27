"""
aidetect check — both detectors over one draft, worst opinion wins.

Runs the desklib segment scorer and Binoculars on the same draft and takes the
WORST opinion per sentence: red beats amber beats clean. Averaging would hide
exactly the disagreement worth seeing — a region only one detector dislikes is
a region a third, differently-tuned detector (the one the teacher runs) might
dislike too.

There are no ensemble weights and never will be: the calibration set is 24
documents, which cannot support fitting any. The combination rule stays one
sentence: worst opinion wins.

    aidetect check draft.docx
    aidetect check draft.docx --pair gemma+ --no-mlx

Defaults to the gemma pair via MLX on Apple Silicon, because that is the only
pair that has ever separated the calibration set (~96%); everywhere else it
falls back to the torch backend.
"""

import argparse
import platform
import sys

from .segments import classify, print_report, word_shares, worse
from .text import MIN_WORDS, read_paragraphs


def main(argv=None):
    apple_silicon = sys.platform == "darwin" and platform.machine() == "arm64"

    ap = argparse.ArgumentParser(prog="aidetect check",
                                 description="Run both detectors; worst opinion wins.")
    ap.add_argument("path", help=".docx or .txt draft to check")
    ap.add_argument("--pair", default="gemma",
                    help="Binoculars model pair (default %(default)s, the calibrated one)")
    ap.add_argument("--mlx", action=argparse.BooleanOptionalAction, default=apple_silicon,
                    help="use the 4-bit MLX backend (default: on for Apple Silicon)")
    ap.add_argument("--tag", default=None,
                    help="genre tag, e.g. 'tech': judge against thresholds calibrated with the same --tag")
    args = ap.parse_args(argv)

    # min_words=0: short connective paragraphs are scored too — by the desklib
    # windows. Binoculars skips them below (they score as noise there).
    paragraphs = read_paragraphs(args.path, min_words=0)
    if not paragraphs:
        print("No prose found.")
        return 1

    # --- pass 1: desklib sentence windows ---
    from . import detect
    device = detect.pick_device()
    print(f"[1/2] desklib segments on {device}...")
    tokenizer, model = detect.load_model(device)
    red, amber, fitted = detect.load_desklib_band(args.tag)
    detect.band_note(red, amber, fitted)
    sentences, desklib_scores = detect.score_windows(paragraphs, tokenizer, model, device)
    desklib_statuses = [classify(score, red, amber) for score in desklib_scores]
    del model, tokenizer   # free ~1.5GB before the Binoculars pair loads

    # --- pass 2: Binoculars, per paragraph ---
    from . import binoculars as bino
    print("[2/2] Binoculars...")
    backend_args = argparse.Namespace(pair=args.pair, mlx=args.mlx)
    pair_key, backend, bdevice, btokenizer, observer, performer = bino.load_backend(backend_args)
    saved = bino.load_saved(pair_key, backend, args.tag)
    bino_threshold = saved.get("threshold", bino.DEFAULT_THRESHOLD)
    bino_amber = saved.get("amber")
    if "threshold" not in saved:
        what = f"pair {pair_key!r} with tag {args.tag!r}" if args.tag else f"pair {pair_key!r}"
        print(f"warning: {what} was never calibrated, using placeholder {bino_threshold}")

    paragraph_status = {}
    for number, paragraph in enumerate(paragraphs):
        if len(paragraph.split()) < MIN_WORDS:
            continue   # too short for Binoculars; the desklib windows cover it
        score = bino.score_text(paragraph, btokenizer, observer, performer, bdevice, backend)
        # lower = more AI for Binoculars
        if score < bino_threshold:
            paragraph_status[number] = "red"
        elif bino_amber is not None and score < bino_amber:
            paragraph_status[number] = "amber"
    bino_red = sum(1 for status in paragraph_status.values() if status == "red")
    bino_amber_count = len(paragraph_status) - bino_red

    # --- union: each sentence takes the worse of the two verdicts ---
    combined = []
    for (number, _sentence), desklib_status in zip(sentences, desklib_statuses):
        combined.append(worse(desklib_status, paragraph_status.get(number, "clean")))

    print("\nstatus = worst of desklib segment and Binoculars paragraph; score shown is desklib's")
    print_report(sentences, desklib_scores, combined)
    desklib_red_share, _ = word_shares(sentences, desklib_statuses)
    print(f"desklib alone: {desklib_red_share:.0%} red | "
          f"Binoculars: {bino_red} paragraphs red, {bino_amber_count} borderline")
    print("reminder: directional only, not a Turnitin score.")
    return 0
