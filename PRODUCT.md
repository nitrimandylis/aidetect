# ai-detect

Local, offline AI-writing detector for my own drafts (EE, IA, etc). Checks
whether my prose reads as AI-generated *before* a teacher runs Turnitin.

## What it is
- `detect.py` — CLI around the **desklib/ai-text-detector-v1.01** model
  (DeBERTa, #1 on the RAID benchmark). Reads a `.docx` or `.txt` and prints an
  AI score (0–1) per paragraph, flagging anything >= 0.5.
- `fast-ai-detector/` — a second, lighter tool ([Ejhfast/fast-ai-detector])
  to cross-check. Its own CLI: `fast-ai-detector --text "..."`.
- `binoculars.py` — a third, training-free scorer (base + instruct LM pair,
  perplexity ÷ cross-perplexity). `calibrate.py` finds the threshold from the
  labelled set in `calibration/`. **Verdict: doesn't work at this scale.**
  Measured on 12 real pre-2020 EEs vs 12 LLM-written paragraphs, the Qwen
  0.5B pair separates only 62%, the 1.5B pair 67% — barely above chance (50%).
  Binoculars needs the 7B pair it was designed for; sub-2B models don't have a
  sharp enough perplexity gap. Kept as a documented negative result, not a
  detector you should trust. desklib stays primary.

## How to run
```bash
conda activate ai-detect
python detect.py "path/to/draft.docx"
python detect.py --text "one sentence"
fast-ai-detector --text "one sentence"   # the second opinion
python binoculars.py "path/to/draft.docx" # training-free third opinion
```

## Honest limits
- Runs on 18GB Mac (Apple Silicon MPS). Binoculars' *default* Falcon-7B pair
  (~28GB) won't fit, so we run a small Qwen2.5 pair instead. Fast-DetectGPT skipped.
- Directional only. A high score means "reword this," not "you'll get caught."
  It is not, and cannot be, the Turnitin number a teacher sees.

[Ejhfast/fast-ai-detector]: https://github.com/Ejhfast/fast-ai-detector
