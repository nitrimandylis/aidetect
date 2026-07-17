# ai-detect

Local, offline AI-writing detector for my own drafts (EE, IA, etc). Checks
whether my prose reads as AI-generated *before* a teacher runs Turnitin.

## What it is
- `detect.py` — CLI around the **desklib/ai-text-detector-v1.01** model
  (DeBERTa, #1 on the RAID benchmark). Reads a `.docx` or `.txt` and prints an
  AI score (0–1) per paragraph, flagging anything >= 0.5.
- `fast-ai-detector/` — a second, lighter tool ([Ejhfast/fast-ai-detector])
  to cross-check. Its own CLI: `fast-ai-detector --text "..."`.

## How to run
```bash
conda activate ai-detect
python detect.py "path/to/draft.docx"
python detect.py --text "one sentence"
fast-ai-detector --text "one sentence"   # the second opinion
```

## Honest limits
- Runs on 18GB Mac (Apple Silicon MPS). Binoculars/Fast-DetectGPT don't fit — skipped.
- Directional only. A high score means "reword this," not "you'll get caught."
  It is not, and cannot be, the Turnitin number a teacher sees.

[Ejhfast/fast-ai-detector]: https://github.com/Ejhfast/fast-ai-detector
