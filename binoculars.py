"""
Binoculars AI-text detector — a second-opinion scorer for my drafts.

Binoculars (Hans et al. 2024, https://arxiv.org/abs/2401.12070) needs no
training. It runs the text through TWO causal language models that share a
tokenizer — an "observer" (base) and a "performer" (instruct) — and compares
how surprised each is:

    score = perplexity(performer) / cross_perplexity(observer, performer)

Human text tends to score HIGHER, machine text LOWER. It's the ratio that
matters: LLM text is unsurprising to a model (low perplexity) but the two
models also agree closely on it (low cross-perplexity), and dividing cancels
out the "this topic is just easy/hard" effect that fools plain perplexity.

The paper used a Falcon-7B pair (~28GB, won't fit an 18GB Mac). We use a small
same-family pair instead so it fits. That's the whole reason this was skipped
before — the method fits, the 7B models didn't.

    python binoculars.py path/to/draft.docx
    python binoculars.py notes.txt
    python binoculars.py --text "some sentence to score"
    python binoculars.py notes.txt --big        # bigger, slower, better pair

Threshold caveat: the AI/human boundary is calibrated PER MODEL PAIR. Falcon's
is 0.90; ours is different and un-tuned, so treat the score as directional
(lower = more AI-like) and tune --threshold on text you know is yours.
"""

import argparse
import sys

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForCausalLM

from detect import read_paragraphs, bar, MIN_WORDS

# Small same-tokenizer pairs. base = observer, instruct = performer.
PAIRS = {
    "small": ("Qwen/Qwen2.5-0.5B", "Qwen/Qwen2.5-0.5B-Instruct"),
    "big":   ("Qwen/Qwen2.5-1.5B", "Qwen/Qwen2.5-1.5B-Instruct"),
}
MAX_LEN = 1024        # token window; longer paragraphs get truncated
# ponytail: Falcon's tuned boundary as a placeholder. Wrong for our pair —
# recalibrate on known-human text. Lower score = more AI-like.
DEFAULT_THRESHOLD = 0.90


def pick_device():
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def load_pair(pair_key, device):
    obs_id, perf_id = PAIRS[pair_key]
    tokenizer = AutoTokenizer.from_pretrained(obs_id)
    dtype = torch.float16 if device.type == "mps" else torch.float32
    observer = AutoModelForCausalLM.from_pretrained(obs_id, torch_dtype=dtype).to(device).eval()
    performer = AutoModelForCausalLM.from_pretrained(perf_id, torch_dtype=dtype).to(device).eval()
    return tokenizer, observer, performer


def perplexity(input_ids, logits):
    """Mean next-token cross-entropy: how surprised the performer is by the text."""
    # predict token t+1 from position t, so line the logits up one step ahead
    shift_logits = logits[..., :-1, :]
    shift_labels = input_ids[..., 1:]
    ce = F.cross_entropy(
        shift_logits.reshape(-1, shift_logits.size(-1)),
        shift_labels.reshape(-1),
        reduction="mean",
    )
    return ce.item()


def cross_perplexity(observer_logits, performer_logits):
    """Mean cross-entropy of the performer's predictions against the observer's
    full distribution — how much the two models DISAGREE per token."""
    # observer's probabilities are the soft targets; score the performer against them
    p = F.softmax(observer_logits, dim=-1)
    log_q = F.log_softmax(performer_logits, dim=-1)
    ce = -(p * log_q).sum(dim=-1)      # per-token cross-entropy
    return ce.mean().item()


def score_text(text, tokenizer, observer, performer, device):
    """Return the Binoculars score for one chunk. Lower = more AI-like."""
    enc = tokenizer(text, truncation=True, max_length=MAX_LEN, return_tensors="pt")
    input_ids = enc["input_ids"].to(device)
    attention_mask = enc["attention_mask"].to(device)
    with torch.no_grad():
        obs_logits = observer(input_ids=input_ids, attention_mask=attention_mask).logits.float()
        perf_logits = performer(input_ids=input_ids, attention_mask=attention_mask).logits.float()
    ppl = perplexity(input_ids, perf_logits)
    x_ppl = cross_perplexity(obs_logits, perf_logits)
    return ppl / x_ppl


def report(paragraphs, threshold, tokenizer, observer, performer, device):
    if not paragraphs:
        print("No paragraphs with >= %d words found." % MIN_WORDS)
        return
    scores = []
    for i, para in enumerate(paragraphs, 1):
        s = score_text(para, tokenizer, observer, performer, device)
        scores.append(s)
        flag = "  <-- AI-ish" if s < threshold else ""
        # bar: lower score = more AI, so invert for a "how AI-ish" bar
        aiish = max(0.0, min(1.0, (threshold * 1.3 - s) / (threshold * 1.3)))
        print(f"P{i:>3}  {s:5.2f}  [{bar(aiish)}]{flag}")
        print(f"      {para[:70].strip()}...")
    avg = sum(scores) / len(scores)
    low = sum(1 for s in scores if s < threshold)
    print("-" * 60)
    print(f"average Binoculars score: {avg:.2f}   |   {low}/{len(scores)} paragraphs flagged (< {threshold})")
    print("reminder: directional only. Lower = more AI-like; threshold is un-tuned for this pair.")


def main():
    ap = argparse.ArgumentParser(description="Binoculars AI-text detector (second opinion).")
    ap.add_argument("path", nargs="?", help=".docx or .txt file to score")
    ap.add_argument("--text", help="score a single string instead of a file")
    ap.add_argument("--big", action="store_true", help="use the 1.5B pair (slower, better)")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                    help="flag paragraphs scoring below this (default %(default)s)")
    args = ap.parse_args()

    if not args.path and not args.text:
        ap.error("give a file path or --text")

    pair_key = "big" if args.big else "small"
    device = pick_device()
    print(f"loading {' + '.join(PAIRS[pair_key])} on {device}... (first run downloads the models)")
    tokenizer, observer, performer = load_pair(pair_key, device)

    if args.text:
        s = score_text(args.text, tokenizer, observer, performer, device)
        verdict = "AI-ish" if s < args.threshold else "human-ish"
        print(f"Binoculars score: {s:.2f}  ({verdict}, threshold {args.threshold})")
    else:
        report(read_paragraphs(args.path), args.threshold, tokenizer, observer, performer, device)


if __name__ == "__main__":
    sys.exit(main())
