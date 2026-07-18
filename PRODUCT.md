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
  labelled set in `calibration/`. Shelved with the Qwen pairs (62–67% on the
  labelled set, near chance) but **revived by Gemma 4**: the E2B pair separates
  the same set at 96%. Gemma 4 is a multimodal checkpoint, so `--mlx` loads it
  4-bit via mlx-vlm and runs it text-only, fitting an 18GB Mac in ~6GB. desklib
  stays primary; Binoculars is now a usable second opinion rather than a dead end.

## How to run
```bash
conda activate ai-detect
python detect.py "path/to/draft.docx"
python detect.py --text "one sentence"
fast-ai-detector --text "one sentence"   # the second opinion
python binoculars.py "path/to/draft.docx"       # training-free, Qwen pair
python binoculars.py "path/to/draft.docx" --mlx --pair gemma  # Gemma 4, 96% on the set
```

## Honest limits
- Runs on 18GB Mac (Apple Silicon MPS). Binoculars' *default* Falcon-7B pair
  (~28GB) won't fit; the Qwen pairs fit but barely separate, and the Gemma 4
  MLX pair is the one that actually works. Fast-DetectGPT skipped.
- Directional only. A high score means "reword this," not "you'll get caught."
  It is not, and cannot be, the Turnitin number a teacher sees.

[Ejhfast/fast-ai-detector]: https://github.com/Ejhfast/fast-ai-detector
