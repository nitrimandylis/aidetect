"""
Calibrate the Binoculars threshold for our Qwen pair, then run the check.

Binoculars outputs a raw score, not a probability, and the AI/human boundary
is specific to the model pair. This scores our labelled calibration set
(calibration/human = real pre-2020 IB essays, calibration/ai = LLM-written on
the same topics), finds the cutoff that best separates them, saves it, and
then scores a real draft with that cutoff.

    python calibrate.py                 # calibrate + check EE-clean.txt
    python calibrate.py path/to/IA.txt  # calibrate + check that file too
    python calibrate.py --pair big      # use the 1.5B pair
"""

import argparse
import glob
import json
import os

from binoculars import add_backend_args, load_backend, report, score_text, PAIRS, MLX_PAIRS
from detect import read_paragraphs

HERE = os.path.dirname(os.path.abspath(__file__))
CAL_DIR = os.path.join(HERE, "calibration")


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


def main():
    ap = argparse.ArgumentParser(description="Calibrate Binoculars threshold, then check a draft.")
    ap.add_argument("path", nargs="?", default=os.path.join(HERE, "EE-clean.txt"),
                    help="draft to check after calibrating (default EE-clean.txt)")
    add_backend_args(ap)
    args = ap.parse_args()

    pair_key, backend, device, tokenizer, observer, performer = load_backend(args)

    # --- score the labelled set ---
    human = score_folder(os.path.join(CAL_DIR, "human"), tokenizer, observer, performer, device, backend)
    ai = score_folder(os.path.join(CAL_DIR, "ai"), tokenizer, observer, performer, device, backend)
    human_scores = [s for _, s in human]
    ai_scores = [s for _, s in ai]

    print("\n=== calibration scores (higher = more human) ===")
    print(f"{'HUMAN (real EEs)':<22}{'AI (LLM-written)':<22}")
    for i in range(max(len(human), len(ai))):
        h = f"{human[i][0]} {human[i][1]:.3f}" if i < len(human) else ""
        a = f"{ai[i][0]} {ai[i][1]:.3f}" if i < len(ai) else ""
        print(f"{h:<22}{a:<22}")
    print(f"\nhuman: min {min(human_scores):.3f}  mean {sum(human_scores)/len(human_scores):.3f}  max {max(human_scores):.3f}")
    print(f"ai   : min {min(ai_scores):.3f}  mean {sum(ai_scores)/len(ai_scores):.3f}  max {max(ai_scores):.3f}")

    cutoff, acc = pick_threshold(human_scores, ai_scores)
    print(f"\n>>> calibrated threshold: {cutoff:.3f}  (separates {acc*100:.0f}% of the {len(human)+len(ai)} samples)")
    print("    flag as AI-ish when score < threshold")

    # save for reuse / future recalibration
    active_pairs = MLX_PAIRS if backend == "mlx" else PAIRS
    out = {
        "pair": active_pairs[pair_key],
        "backend": backend,
        "threshold": round(cutoff, 4),
        "accuracy": round(acc, 4),
        "n_human": len(human),
        "n_ai": len(ai),
        "human_mean": round(sum(human_scores)/len(human_scores), 4),
        "ai_mean": round(sum(ai_scores)/len(ai_scores), 4),
    }
    tag = f"{pair_key}-mlx" if backend == "mlx" else pair_key
    thr_path = os.path.join(CAL_DIR, f"threshold-{tag}.json")
    json.dump(out, open(thr_path, "w"), indent=2)
    print(f"    saved -> {os.path.relpath(thr_path, HERE)}")

    # --- run the calibrated check on the draft ---
    print(f"\n=== checking {os.path.relpath(args.path, HERE)} with threshold {cutoff:.3f} ===")
    report(read_paragraphs(args.path), cutoff, tokenizer, observer, performer, device, backend)


if __name__ == "__main__":
    main()
