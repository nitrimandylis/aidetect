# aidetect

Local, offline AI-writing checks and IB word counts for my own drafts (EE, IA,
etc). Tells me whether my prose reads as AI-generated *before* a teacher runs
Turnitin, and whether the draft is over its word limit before I hand it in.

Packaged for PyPI as `aidetect` so it installs rather than being cloned. The
0.1.0 wheel is built and verified against a clean venv; the upload itself has
not happened yet.

```bash
uv tool install aidetect
```

## What it is

One command, five subcommands. Subcommand modules import lazily, so the two
that need no model stay instant.

- `aidetect count` — the IB word count. Excludes headings, block quotes,
  bullets, tables, footnotes, in-text citations and everything from the
  bibliography on, then reports the total **by section** against `--limit`.
  Word's own count is wrong for IB and does not say which section is bloated.
  `--json` emits the whole thing as one object for scripts and agents.
- `aidetect score` — the **desklib/ai-text-detector-v1.01** model (DeBERTa, #1
  on the RAID benchmark). Prints an AI score (0–1) per paragraph, flagging
  anything >= 0.5.
- `aidetect bino` — training-free third scorer (base + instruct LM pair,
  perplexity ÷ cross-perplexity). Shelved with the Qwen pairs (62–67% on the
  labelled set, near chance) but **revived by Gemma 4**: the E2B pair separates
  the same set at 96%. Gemma 4 is a multimodal checkpoint, so `--mlx` loads it
  4-bit via mlx-vlm and runs it text-only, fitting an 18GB Mac in ~6GB. desklib
  stays primary; Binoculars is a usable second opinion rather than a dead end.
- `aidetect extract` — strips a `.docx` down to finished prose for the scorers.
- `aidetect calibrate` — refits a Binoculars threshold on a labelled set you
  name via `--human-dir`/`--ai-dir`, and writes it to `~/.config/aidetect`.
- `fast-ai-detector/` — a separate, lighter tool ([Ejhfast/fast-ai-detector])
  to cross-check. Not vendored, gitignored, its own CLI.

## Decisions worth remembering

- **Thresholds are two-tier.** The wheel ships the fitted ones; anything you
  refit lands in `~/.config/aidetect` and wins. Calibration output never writes
  into site-packages, which is replaced on upgrade.
- **`corpora/` does not ship.** It is 12 real students' Extended Essays plus
  matched LLM imitations. Fine in a repo, not something to push through PyPI on
  every install. `calibrate` therefore requires explicit folder arguments.
- **`text.py` is torch-free on purpose.** `count` must not pay a ~2s model
  import to count words, and the split is enforced by a check in `tests/`.
- **The MLX cache stays at `~/.cache/ai-detect-mlx`** despite the rename.
  Moving it would force a 6GB re-download and re-quantization for nothing.

## Honest limits

- Runs on an 18GB Mac (Apple Silicon MPS). Binoculars' *default* Falcon-7B pair
  (~28GB) won't fit; the Qwen pairs fit but barely separate, and the Gemma 4
  MLX pair is the one that actually works. Fast-DetectGPT skipped.
- Directional only. A high score means "reword this," not "you'll get caught."
  It is not, and cannot be, the Turnitin number a teacher sees.
- `count` implements the exclusions the EE and the subject IAs share. Per-subject
  quirks are not encoded; check your own subject guide for the limit itself.
- Citation stripping keys on a year, `ibid` or `et al` inside parentheses. A
  citation style that uses none of those is not detected and will be counted.

[Ejhfast/fast-ai-detector]: https://github.com/Ejhfast/fast-ai-detector
