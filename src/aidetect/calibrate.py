"""
Calibrate the Binoculars threshold for a model pair, then optionally check a draft.

Binoculars outputs a raw score, not a probability, and the AI/human boundary is
specific to the model pair. This scores a labelled set (a folder of known-human
prose against a folder of known-LLM prose on the same topics), finds the cutoff
that best separates them, and saves it to ~/.config/aidetect.

My own calibration set is not shipped with the package: it is 12 real pre-2020 IB
Extended Essays and 12 LLM-written imitations, and it lives in corpora/ in the
repo. Point --human-dir and --ai-dir at your own.

    aidetect calibrate --human-dir corpora/human --ai-dir corpora/ai
    aidetect calibrate --human-dir corpora/human --ai-dir corpora/ai --mlx --pair gemma
    aidetect calibrate --human-dir h --ai-dir a --check draft.docx

The human class has to be provably human or the threshold is meaningless. Do not
point --human-dir at anything written after ChatGPT that you cannot certify.
"""

import argparse
import glob
import json
import os

from .binoculars import (MLX_PAIRS, PAIRS, add_backend_args, load_backend,
                         pair_tag, report, score_text)
from .paths import ensure_user_dir, user_threshold_path
from .text import read_paragraphs


def score_folder(folder, tokenizer, observer, performer, device, backend="torch"):
    """Score every .txt in a folder. Returns list of (id, score)."""
    out = []
    for path in sorted(glob.glob(os.path.join(folder, "*.txt"))):
        text = open(path, encoding="utf-8").read().strip()
        if not text:
            continue
        sid = os.path.splitext(os.path.basename(path))[0]
        out.append((sid, score_text(text, tokenizer, observer, performer, device, backend)))
    return out


def pick_threshold(human_scores, ai_scores):
    """Cutoff that best separates the clusters (predict AI if score < cutoff).
    Human text scores higher, AI lower. Ties broken toward the most centered
    cutoff (largest gap to the nearest sample) so it generalizes better."""
    everything = sorted(set(human_scores + ai_scores))
    candidates = [everything[0] - 0.01]
    for a, b in zip(everything, everything[1:]):
        candidates.append((a + b) / 2)
    candidates.append(everything[-1] + 0.01)

    best = None
    for c in candidates:
        correct = sum(s >= c for s in human_scores) + sum(s < c for s in ai_scores)
        acc = correct / (len(human_scores) + len(ai_scores))
        margin = min(abs(s - c) for s in human_scores + ai_scores)
        key = (acc, margin)
        if best is None or key > best[0]:
            best = (key, c)
    (acc, _margin), cutoff = best
    return cutoff, acc


def fit_desklib_amber(human_dir, tag=None):
    """Fit the amber edge for `aidetect score --segments` on the human corpus.

    Scores every sentence window of every human .txt with desklib and takes the
    90th percentile: 9 in 10 provably-human windows score below this edge. Not
    the maximum, because one weird human paragraph would push the edge up
    against the red 0.5 line and erase the band."""
    import json

    from .detect import load_model, pick_device
    from .detect import score_text as desklib_score
    from .segments import RED_DEFAULT, build_windows, document_sentences
    from .text import is_prose

    print("\nfitting the desklib amber band on the same human corpus...")
    device = pick_device()
    tokenizer, model = load_model(device)

    window_scores = []
    for path in sorted(glob.glob(os.path.join(human_dir, "*.txt"))):
        text = open(path, encoding="utf-8").read()
        # min_words=0: segment mode scores short paragraphs too, so the edge
        # has to be fitted on the same kind of windows it will judge
        paragraphs = [c.strip() for c in text.split("\n\n") if is_prose(c, min_words=0)]
        sentences = document_sentences(paragraphs)
        for start, end in build_windows(len(sentences)):
            chunk = " ".join(sentence for _number, sentence in sentences[start:end])
            window_scores.append(desklib_score(chunk, tokenizer, model, device))

    window_scores.sort()
    p90 = window_scores[int(0.9 * (len(window_scores) - 1))]
    # never past red: if humans routinely score above 0.5 the band is empty,
    # which is the honest answer, not a wider band
    amber = round(min(p90, RED_DEFAULT), 4)
    out = {
        "threshold": RED_DEFAULT,
        "amber": amber,
        "n_windows": len(window_scores),
        "human_p90": round(p90, 4),
    }
    ensure_user_dir()
    path = user_threshold_path(f"desklib-{tag}" if tag else "desklib")
    json.dump(out, open(path, "w"), indent=2)
    print(f"    desklib amber edge: {amber}  ({len(window_scores)} human windows)")
    print(f"    saved -> {path}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="aidetect calibrate",
        description="Fit the Binoculars threshold for a model pair on your own labelled set.")
    ap.add_argument("--human-dir", required=True,
                    help="folder of .txt files you can certify are human-written")
    ap.add_argument("--ai-dir", required=True,
                    help="folder of .txt files you know are LLM-written")
    ap.add_argument("--check", help="optionally score this draft with the new threshold")
    add_backend_args(ap)
    args = ap.parse_args(argv)

    for label, folder in (("--human-dir", args.human_dir), ("--ai-dir", args.ai_dir)):
        if not glob.glob(os.path.join(folder, "*.txt")):
            ap.error(f"{label}: no .txt files in {folder}")

    pair_key, backend, device, tokenizer, observer, performer = load_backend(args)

    # --- score the labelled set ---
    human = score_folder(args.human_dir, tokenizer, observer, performer, device, backend)
    ai = score_folder(args.ai_dir, tokenizer, observer, performer, device, backend)
    human_scores = [s for _, s in human]
    ai_scores = [s for _, s in ai]

    print("\n=== calibration scores (higher = more human) ===")
    print(f"{'HUMAN':<22}{'AI (LLM-written)':<22}")
    for i in range(max(len(human), len(ai))):
        h = f"{human[i][0]} {human[i][1]:.3f}" if i < len(human) else ""
        a = f"{ai[i][0]} {ai[i][1]:.3f}" if i < len(ai) else ""
        print(f"{h:<22}{a:<22}")
    print(f"\nhuman: min {min(human_scores):.3f}  mean {sum(human_scores)/len(human_scores):.3f}  max {max(human_scores):.3f}")
    print(f"ai   : min {min(ai_scores):.3f}  mean {sum(ai_scores)/len(ai_scores):.3f}  max {max(ai_scores):.3f}")

    cutoff, acc = pick_threshold(human_scores, ai_scores)
    print(f"\n>>> calibrated threshold: {cutoff:.3f}  (separates {acc*100:.0f}% of the {len(human)+len(ai)} samples)")
    print("    flag as AI-ish when score < threshold")

    # The amber edge: the worst (lowest) human doc that still passed. Between
    # the cutoff and this score, no provably-human essay ever landed, so a
    # draft scoring there is borderline even though it is not flagged.
    passing_human = [s for s in human_scores if s >= cutoff]
    amber = round(min(passing_human), 4) if passing_human else None
    if amber is not None:
        print(f"    borderline (amber) below {amber}: no human calibration doc scored lower and passed")

    # save for reuse / future recalibration
    active_pairs = MLX_PAIRS if backend == "mlx" else PAIRS
    out = {
        "pair": active_pairs[pair_key],
        "backend": backend,
        "threshold": round(cutoff, 4),
        "amber": amber,
        "accuracy": round(acc, 4),
        "n_human": len(human),
        "n_ai": len(ai),
        "human_mean": round(sum(human_scores)/len(human_scores), 4),
        "ai_mean": round(sum(ai_scores)/len(ai_scores), 4),
    }
    ensure_user_dir()
    thr_path = user_threshold_path(pair_tag(pair_key, backend, args.tag))
    json.dump(out, open(thr_path, "w"), indent=2)
    print(f"    saved -> {thr_path}")

    # --- fit the desklib amber band on the same human folder ---
    # Runs every calibration: it is idempotent, and calibrate is the only
    # command that ever sees the human corpus.
    fit_desklib_amber(args.human_dir, args.tag)

    # --- run the calibrated check on a draft ---
    if args.check:
        print(f"\n=== checking {args.check} with threshold {cutoff:.3f} ===")
        report(read_paragraphs(args.check), cutoff, tokenizer, observer, performer, device, backend,
               amber=amber)
