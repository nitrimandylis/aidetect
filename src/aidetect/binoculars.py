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

The paper used a Falcon-7B pair (~28GB, won't fit an 18GB Mac). Small Qwen2.5
pairs fit but barely separate human from AI text (~63%, near chance) — which is
why this was shelved as a negative result. A Gemma 4 pair fixes that: it hits
~96% on the calibration set. Gemma 4 ships as a multimodal checkpoint, so the
--mlx path loads it 4-bit via mlx-vlm and runs it text-only.

    aidetect bino path/to/draft.docx
    aidetect bino notes.txt --text "some sentence to score"
    aidetect bino notes.txt --pair big         # bigger Qwen pair
    aidetect bino notes.txt --mlx --pair gemma # Gemma 4 E2B on a Mac

Threshold: the AI/human boundary is PER MODEL PAIR. If `aidetect calibrate` has saved a
threshold for the active pair it's loaded automatically; otherwise it falls back
to Falcon's 0.90 placeholder. Lower score = more AI-like.
"""

import argparse
import os

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForCausalLM

from .detect import pick_device
from .paths import threshold_path, user_threshold_path
from .text import MIN_WORDS, bar, read_paragraphs

# Same-tokenizer pairs. base = observer, instruct = performer.
# Gemma 4 is Apache-2 (no HF gate). E2B is the smallest but ~5B raw params each,
# so the fp16 pair is ~20GB — over an 18GB Mac. Use these on a CUDA box; on a Mac
# use --mlx (4-bit quantized, fits in ~6GB).
PAIRS = {
    "small":  ("Qwen/Qwen2.5-0.5B", "Qwen/Qwen2.5-0.5B-Instruct"),
    "big":    ("Qwen/Qwen2.5-1.5B", "Qwen/Qwen2.5-1.5B-Instruct"),
    "gemma":  ("google/gemma-4-E2B", "google/gemma-4-E2B-it"),
    "gemma+": ("google/gemma-4-E4B", "google/gemma-4-E4B-it"),
}

# --mlx pairs. observer = google base repo (no pre-quant exists, so we quantize it
# locally on first run); performer = mlx-community's pre-quantized instruct repo.
MLX_PAIRS = {
    "gemma":  ("google/gemma-4-E2B", "mlx-community/gemma-4-e2b-it-qat-OptiQ-4bit"),
    "gemma+": ("google/gemma-4-E4B", "mlx-community/gemma-4-e4b-it-qat-OptiQ-4bit"),
}
MLX_CACHE = os.path.expanduser("~/.cache/ai-detect-mlx")
MAX_LEN = 1024        # token window; longer paragraphs get truncated
# ponytail: Falcon's tuned boundary as a placeholder. Wrong for our pair —
# recalibrate on known-human text. Lower score = more AI-like.
DEFAULT_THRESHOLD = 0.90


def pair_tag(pair_key, backend):
    return f"{pair_key}-mlx" if backend == "mlx" else pair_key


def load_saved_threshold(pair_key, backend):
    """Return the saved threshold for this pair, or None if never calibrated.

    A threshold you fitted yourself (~/.config/aidetect) wins over the one
    shipped in the wheel, so recalibrating survives an upgrade.
    """
    import json
    tag = pair_tag(pair_key, backend)
    for path in (user_threshold_path(tag), threshold_path(tag)):
        if path and os.path.exists(path):
            return json.load(open(path)).get("threshold")
    return None


def load_pair(pair_key, device):
    obs_id, perf_id = PAIRS[pair_key]
    tokenizer = AutoTokenizer.from_pretrained(obs_id)
    dtype = torch.float16 if device.type == "mps" else torch.float32
    observer = AutoModelForCausalLM.from_pretrained(obs_id, torch_dtype=dtype).to(device).eval()
    performer = AutoModelForCausalLM.from_pretrained(perf_id, torch_dtype=dtype).to(device).eval()
    return tokenizer, observer, performer


def _mlx_quantized(repo):
    """Return a local 4-bit MLX copy of an fp16 HF repo, converting once and reusing.
    Gemma 4 ships as a VLM checkpoint, so this goes through mlx-vlm, not mlx-lm."""
    from mlx_vlm import convert
    out = os.path.join(MLX_CACHE, repo.replace("/", "_") + "-4bit")
    if not os.path.isdir(out):
        print(f"converting {repo} to 4-bit MLX (one-time, downloads fp16 weights)...")
        convert(repo, mlx_path=out, quantize=True)
    return out


def load_pair_mlx(pair_key):
    """MLX backend for Macs. observer is quantized locally; performer is pre-quantized.
    Returns (tokenizer, observer, performer) — models are mlx-vlm VLMs run text-only."""
    from mlx_vlm import load
    obs_src, perf_repo = MLX_PAIRS[pair_key]
    observer, processor = load(_mlx_quantized(obs_src))   # base tokenizer drives encoding
    performer, _ = load(perf_repo)
    tokenizer = getattr(processor, "tokenizer", processor)
    return tokenizer, observer, performer


def add_backend_args(ap):
    """The --pair/--mlx flags, shared by binoculars.py and calibrate.py."""
    ap.add_argument("--pair", choices=list(PAIRS), default="small",
                    help="model pair to use (default %(default)s)")
    ap.add_argument("--mlx", action="store_true",
                    help="use the 4-bit MLX gemma pair (Apple Silicon; needs mlx-vlm)")


def load_backend(args):
    """Turn parsed CLI args into a loaded model pair.
    Returns (pair_key, backend, device, tokenizer, observer, performer)."""
    pair_key = args.pair
    if args.mlx:
        if pair_key not in MLX_PAIRS:
            raise SystemExit(f"--mlx only supports {list(MLX_PAIRS)}; pass e.g. --pair gemma")
        print(f"loading MLX pair {' + '.join(MLX_PAIRS[pair_key])}...")
        tokenizer, observer, performer = load_pair_mlx(pair_key)
        return pair_key, "mlx", None, tokenizer, observer, performer
    device = pick_device()
    print(f"loading {' + '.join(PAIRS[pair_key])} on {device}... (first run downloads the models)")
    tokenizer, observer, performer = load_pair(pair_key, device)
    return pair_key, "torch", device, tokenizer, observer, performer


def _mlx_logits(model, ids):
    """Run an mlx-vlm model text-only (no pixel_values) and return logits as torch."""
    import mlx.core as mx
    import numpy as np
    out = model(mx.array([ids]))             # text-only path; returns LanguageModelOutput
    logits = out.logits if hasattr(out, "logits") else out   # (1, seq, vocab)
    logits = logits.astype(mx.float32)       # numpy can't read mlx bfloat16 buffers
    return torch.from_numpy(np.array(logits)).float()


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


def score_text(text, tokenizer, observer, performer, device, backend="torch"):
    """Return the Binoculars score for one chunk. Lower = more AI-like.
    Both backends end up feeding torch logits into the same perplexity math."""
    if backend == "mlx":
        ids = tokenizer.encode(text)[:MAX_LEN]     # base+instruct share this vocab
        obs_logits = _mlx_logits(observer, ids)
        perf_logits = _mlx_logits(performer, ids)
        input_ids = torch.tensor([ids])
    else:
        enc = tokenizer(text, truncation=True, max_length=MAX_LEN, return_tensors="pt")
        input_ids = enc["input_ids"].to(device)
        attention_mask = enc["attention_mask"].to(device)
        with torch.no_grad():
            obs_logits = observer(input_ids=input_ids, attention_mask=attention_mask).logits.float()
            perf_logits = performer(input_ids=input_ids, attention_mask=attention_mask).logits.float()
    ppl = perplexity(input_ids, perf_logits)
    x_ppl = cross_perplexity(obs_logits, perf_logits)
    return ppl / x_ppl


def report(paragraphs, threshold, tokenizer, observer, performer, device, backend="torch"):
    if not paragraphs:
        print("No paragraphs with >= %d words found." % MIN_WORDS)
        return
    scores = []
    for i, para in enumerate(paragraphs, 1):
        s = score_text(para, tokenizer, observer, performer, device, backend)
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
    print("reminder: directional only. Lower = more AI-like. Recalibrate with `aidetect calibrate`.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="aidetect bino",
                                 description="Binoculars AI-text detector (second opinion).")
    ap.add_argument("path", nargs="?", help=".docx or .txt file to score")
    ap.add_argument("--text", help="score a single string instead of a file")
    add_backend_args(ap)
    ap.add_argument("--threshold", type=float, default=None,
                    help="flag paragraphs below this (default: calibrated pair threshold, else %s)"
                         % DEFAULT_THRESHOLD)
    args = ap.parse_args(argv)

    if not args.path and not args.text:
        ap.error("give a file path or --text")

    pair_key, backend, device, tokenizer, observer, performer = load_backend(args)

    # explicit --threshold wins; else use the calibrated one; else Falcon's placeholder
    threshold = args.threshold
    if threshold is None:
        threshold = load_saved_threshold(pair_key, backend)
        if threshold is not None:
            print(f"using calibrated threshold {threshold}")
    if threshold is None:
        threshold = DEFAULT_THRESHOLD

    if args.text:
        s = score_text(args.text, tokenizer, observer, performer, device, backend)
        verdict = "AI-ish" if s < threshold else "human-ish"
        print(f"Binoculars score: {s:.2f}  ({verdict}, threshold {threshold})")
    else:
        report(read_paragraphs(args.path), threshold, tokenizer, observer, performer, device, backend)
