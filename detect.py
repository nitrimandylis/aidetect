"""
Local AI-writing detector for my drafts.

Scores each paragraph of a .docx (or a .txt / --text string) with the
desklib DeBERTa detector. Everything runs on my Mac, offline after the
first model download. The score is a rough, directional read, NOT Turnitin:
high just means "this paragraph reads AI-ish, maybe reword it".

Usage:
    python detect.py path/to/draft.docx
    python detect.py notes.txt
    python detect.py --text "some sentence to score"
"""

import argparse
import sys

import torch
import torch.nn as nn
from transformers import AutoTokenizer, AutoConfig, AutoModel, PreTrainedModel

MODEL_ID = "desklib/ai-text-detector-v1.01"
MAX_LEN = 768          # model's token window; longer paragraphs get truncated
MIN_WORDS = 25         # ponytail: skip fragments; short text scores as noise


# --- the model class, copied verbatim from the desklib model card ---
# It's a normal transformer with mean-pooling + a 1-unit classifier head.
class DesklibAIDetectionModel(PreTrainedModel):
    config_class = AutoConfig

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


def read_paragraphs(path):
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
    return [c.strip() for c in chunks if len(c.split()) >= MIN_WORDS]


def bar(prob, width=20):
    filled = round(prob * width)
    return "#" * filled + "-" * (width - filled)


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


def main():
    ap = argparse.ArgumentParser(description="Local AI-writing detector (desklib).")
    ap.add_argument("path", nargs="?", help=".docx or .txt file to score")
    ap.add_argument("--text", help="score a single string instead of a file")
    args = ap.parse_args()

    if not args.path and not args.text:
        ap.error("give a file path or --text")

    device = pick_device()
    print(f"loading {MODEL_ID} on {device}... (first run downloads ~1.5GB)")
    tokenizer, model = load_model(device)

    if args.text:
        prob = score_text(args.text, tokenizer, model, device)
        print(f"AI score: {prob:.2f}  [{bar(prob)}]")
    else:
        report(read_paragraphs(args.path), tokenizer, model, device)


if __name__ == "__main__":
    sys.exit(main())
