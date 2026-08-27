"""
Local AI-writing detector for my drafts.

Scores each paragraph of a .docx (or a .txt / --text string) with the
desklib DeBERTa detector. Everything runs on my Mac, offline after the
first model download. The score is a rough, directional read, NOT Turnitin:
high just means "this paragraph reads AI-ish, maybe reword it".

Usage:
    aidetect score path/to/draft.docx
    aidetect score notes.txt
    aidetect score --text "some sentence to score"
"""

import argparse
import os

import torch
import torch.nn as nn
from transformers import AutoTokenizer, AutoConfig, AutoModel, PreTrainedModel

from .segments import (AMBER_FALLBACK, RED_DEFAULT, build_windows, classify,
                       document_sentences, print_report, sentence_scores)
from .text import MIN_WORDS, bar, read_paragraphs

MODEL_ID = "desklib/ai-text-detector-v1.01"
MAX_LEN = 768          # model's token window; longer paragraphs get truncated


# --- the model class, copied verbatim from the desklib model card ---
# It's a normal transformer with mean-pooling + a 1-unit classifier head.
class DesklibAIDetectionModel(PreTrainedModel):
    config_class = AutoConfig
    # transformers 5.x reads this during from_pretrained; the model has no tied
    # weights (encoder + linear head), so an empty mapping is correct. Without it,
    # loading raises AttributeError on 5.x. ponytail: needed once mlx pulled 5.x in.
    all_tied_weights_keys = {}

    def __init__(self, config):
        super().__init__(config)
        self.model = AutoModel.from_config(config)
        self.classifier = nn.Linear(config.hidden_size, 1)
        self.init_weights()

    def forward(self, input_ids, attention_mask=None, labels=None):
        outputs = self.model(input_ids, attention_mask=attention_mask)
        last_hidden_state = outputs[0]
        # mean-pool the token vectors, ignoring padding
        mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
        summed = torch.sum(last_hidden_state * mask, dim=1)
        counts = torch.clamp(mask.sum(dim=1), min=1e-9)
        pooled = summed / counts
        logits = self.classifier(pooled)
        return {"logits": logits}


def pick_device():
    if torch.backends.mps.is_available():
        return torch.device("mps")   # Apple Silicon GPU
    return torch.device("cpu")


def load_model(device):
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = DesklibAIDetectionModel.from_pretrained(MODEL_ID)
    model.to(device)
    model.eval()
    return tokenizer, model


def score_text(text, tokenizer, model, device):
    """Return P(AI-generated) in [0, 1] for one chunk of text."""
    encoded = tokenizer(
        text,
        padding="max_length",
        truncation=True,
        max_length=MAX_LEN,
        return_tensors="pt",
    )
    input_ids = encoded["input_ids"].to(device)
    attention_mask = encoded["attention_mask"].to(device)
    with torch.no_grad():
        logits = model(input_ids=input_ids, attention_mask=attention_mask)["logits"]
        return torch.sigmoid(logits).item()


def load_desklib_band():
    """The red/amber boundaries for segment scoring.

    red is the model's own 0.5. amber comes from threshold-desklib.json, which
    `aidetect calibrate` fits from the human corpus (see fit_desklib_amber);
    until that has run, a fixed 0.35 stands in. Returns (red, amber, fitted)."""
    import json
    from .paths import threshold_path, user_threshold_path
    for path in (user_threshold_path("desklib"), threshold_path("desklib")):
        if path and os.path.exists(path):
            data = json.load(open(path))
            return (data.get("threshold", RED_DEFAULT),
                    data.get("amber", AMBER_FALLBACK), True)
    return RED_DEFAULT, AMBER_FALLBACK, False


def score_windows(paragraphs, tokenizer, model, device):
    """Segment pass: overlapping sentence windows through the model.
    Returns (sentences, per-sentence worst window scores)."""
    sentences = document_sentences(paragraphs)
    windows = build_windows(len(sentences))
    window_scores = []
    for start, end in windows:
        chunk = " ".join(sentence for _number, sentence in sentences[start:end])
        window_scores.append(score_text(chunk, tokenizer, model, device))
    return sentences, sentence_scores(len(sentences), windows, window_scores)


def band_note(red, amber, fitted):
    """One line saying where the amber band stands, so its absence in the
    report reads as a finding, not a bug."""
    if not fitted:
        print(f"amber band at fixed {amber} (run `aidetect calibrate` to fit it on your corpus)")
    elif amber >= red:
        print("amber band empty: over 10% of your human calibration windows score in "
              "desklib's red zone, so no edge below red is meaningful")


def segment_report(paragraphs, tokenizer, model, device):
    if not paragraphs:
        print("No prose found.")
        return
    red, amber, fitted = load_desklib_band()
    band_note(red, amber, fitted)
    sentences, scores = score_windows(paragraphs, tokenizer, model, device)
    statuses = [classify(score, red, amber) for score in scores]
    print_report(sentences, scores, statuses)
    print("reminder: directional only, not a Turnitin score.")


def report(paragraphs, tokenizer, model, device):
    if not paragraphs:
        print("No paragraphs with >= %d words found." % MIN_WORDS)
        return
    scores = []
    for i, para in enumerate(paragraphs, 1):
        prob = score_text(para, tokenizer, model, device)
        scores.append(prob)
        flag = "  <-- AI-ish" if prob >= 0.5 else ""
        preview = para[:70].replace("\n", " ")
        print(f"P{i:>3}  {prob:5.2f}  [{bar(prob)}]{flag}")
        print(f"      {preview}...")
    avg = sum(scores) / len(scores)
    high = sum(1 for s in scores if s >= 0.5)
    print("-" * 60)
    print(f"average AI score: {avg:.2f}   |   {high}/{len(scores)} paragraphs flagged")
    print("reminder: directional only, not a Turnitin score.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="aidetect score",
                                 description="Local AI-writing detector (desklib).")
    ap.add_argument("path", nargs="?", help=".docx or .txt file to score")
    ap.add_argument("--text", help="score a single string instead of a file")
    ap.add_argument("--segments", action="store_true",
                    help="score overlapping sentence windows (Turnitin-shaped) instead of paragraphs")
    args = ap.parse_args(argv)

    if not args.path and not args.text:
        ap.error("give a file path or --text")

    device = pick_device()
    print(f"loading {MODEL_ID} on {device}... (first run downloads ~1.5GB)")
    tokenizer, model = load_model(device)

    if args.segments:
        # min_words=0: short paragraphs are the point of segment mode, they
        # ride inside windows instead of being skipped as noise
        paragraphs = [args.text] if args.text else read_paragraphs(args.path, min_words=0)
        segment_report(paragraphs, tokenizer, model, device)
    elif args.text:
        prob = score_text(args.text, tokenizer, model, device)
        print(f"AI score: {prob:.2f}  [{bar(prob)}]")
    else:
        report(read_paragraphs(args.path), tokenizer, model, device)
