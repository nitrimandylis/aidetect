# aidetect

Local, offline AI-writing checks and IB word counts for my own drafts (EE, IA,
etc). Tells me whether my prose reads as AI-generated *before* a teacher runs
Turnitin, and whether the draft is over its word limit before I hand it in.

Published to PyPI as `aidetect` (0.3.0, 2026-08-27) so it installs rather than
being cloned. The source carries unreleased work on top of that tag, including
the rebuilt corpora and the thresholds refitted on them. Releases go out from a GitHub release via trusted publishing:
`.github/workflows/publish.yml`, no token anywhere. To ship a version: bump
`version` in pyproject.toml, then draft a release tagged `v<version>`.

```bash
uv tool install aidetect
```

## What it is

One command, seven subcommands. Subcommand modules import lazily, so the three
that need no model stay instant.

- `aidetect count` — the IB word count. Excludes the cover page, the contents
  page, headings, figure captions, tables, footnotes, in-text citations and
  everything from the bibliography on, then reports the total **by section and
  sub-section** against `--limit`. Block quotes and body bullets do count; they
  are assessed prose. Word's own count is wrong for IB and does not say which
  section is bloated. `--json` emits the whole thing as one object for scripts
  and agents.
- `aidetect score` — the **desklib/ai-text-detector-v1.01** model (DeBERTa, #1
  on the RAID benchmark). Prints an AI score (0–1) per paragraph, flagging
  anything >= 0.5. `--segments` switches to overlapping 7-sentence windows and
  reports the share of prose sitting in flagged segments, which is the shape of
  number Turnitin reports; windows also cover the short connective paragraphs
  that paragraph mode skips.
- `aidetect check` — runs the desklib segments and Binoculars over one draft and
  takes the **worst opinion per sentence**. Detectors disagreeing is the signal,
  so nothing is averaged. No ensemble weights: 31 calibration essays cannot
  support fitting any.
- `aidetect bino` — training-free third scorer (base + instruct LM pair,
  perplexity ÷ cross-perplexity). Shelved with the Qwen pairs (62–67% on the
  labelled set, near chance) but **revived by Gemma 4**: the E2B pair separates
  the set at 91.9%, held out an essay at a time. Gemma 4 is a multimodal checkpoint, so `--mlx` loads it
  4-bit via mlx-vlm and runs it text-only, fitting an 18GB Mac in ~6GB. desklib
  stays primary; Binoculars is a usable second opinion rather than a dead end.
- `aidetect extract` — writes the paragraphs `count` counted into a `.txt`
  (`<name> prose.txt` unless you name one), so I can read what got counted. No
  detector filtering happens here; `score` applies its own.
- `aidetect calibrate` — refits a Binoculars threshold on a labelled set you
  name via `--human-dir`/`--ai-dir`, and writes it to `~/.config/aidetect`. It
  also fits the desklib amber band on the same human folder. `--tag` keeps a
  genre calibration beside the default instead of overwriting it. Samples are
  grouped by the essay they came from, so the reported accuracy is
  leave-one-essay-out rather than the training fit, and each threshold file
  records `n_essays` beside `n_human`.
- `aidetect generate` — builds the AI half of a calibration set by calling
  hosted models through NVIDIA NIM with no system prompt and no style guidance.
  Prompts carry the essay position of the human paragraph they match, which is
  structural rather than stylistic. `--workers` runs several completions at once
  and `--timeout` sets how long one may take. Every sample is validated by
  `sample_problem()` before it is written, on the same rules the human selector
  applies, and the model pool is swept up to three times before a sample is
  given up on. The only subcommand that uses the network at run time, and the
  only one needing a key (`NVIDIA_API_KEY`, read from the environment, never
  stored).
- `tools/` — repo-only, not shipped. `build_corpus.py` turns scanned Extended
  Essays into corpus samples through macOS Vision OCR, and `ocr_bias.py`
  measures what that transcription does to a score.
- `fast-ai-detector/` — a separate, lighter tool ([Ejhfast/fast-ai-detector])
  to cross-check. Not vendored, gitignored, its own CLI.

## Decisions worth remembering

- **Thresholds are two-tier.** The wheel ships the fitted ones; anything you
  refit lands in `~/.config/aidetect` and wins. Calibration output never writes
  into site-packages, which is replaced on upgrade.
- **`corpora/` does not ship.** Four labelled sets (`human`/`ai` humanities,
  `human-tech`/`ai-tech` maths, science and ITGS),
  built from other people's Extended Essays and matched LLM writing. Fine in a
  repo, not something to push through PyPI on every install. `calibrate`
  therefore requires explicit folder arguments.
- **The AI class must be a fair adversary.** An AI corpus written by an
  assistant carrying house style rules came out stylometrically inside the human
  class it was meant to oppose, which lowers the threshold and makes the
  detector more lenient — the false-negative direction. That is why `generate`
  exists and why the corpora are never hand-written. The story, with the
  numbers, is in `corpora/ai-tech/README.md`.
- **The boundary is per genre, not just per model pair.** Human technical prose
  means 0.89 on Binoculars where humanities prose means 0.91, and the technical
  AI class also scores higher (0.71 against 0.66), so `--tag tech` sits at 0.802
  where the default sits at 0.784. Fitted on twelve paragraphs a side the genre
  gap looked like 0.07 and the tech threshold sat *below* the default; on the
  full corpora it is 0.026 and sits slightly above. Keep the tag, since it
  cross-validates better (95.1% against 91.9%), but it is a small correction
  rather than the large shift the first fit implied.
- **One walker, two filters.** `walk()` in `text.py` applies the structure
  rules once, and `count`, `extract` and `score` all read the document through
  it. Each job then layers its own filter: `count` strips in-text citations,
  and paragraph-mode scoring adds a 25-word style floor. Segment mode and
  `check` drop that floor on purpose, because short connective sentences are
  exactly where formulaic prose hides; windows give them context to be scored in. Before this, each command filtered
  the document its own way and one file got three different answers.
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
- The human corpora are transcribed from scans, and OCR shifts a Binoculars
  score by about -0.007 against the same prose read from a text layer, roughly
  3.4% of the gap between the class means. Small, but toward leniency.
- The three computer science essays in `human-tech` come from outside the IBO
  collection: two 2009 subject-report exemplars and one 2013 essay, each dated
  from its own PDF metadata rather than from the collection's blanket 2008
  copyright. They are the only certified-human CS prose here, and nine
  paragraphs is thin evidence for judging a CS IA.
- The desklib amber band is empty in both genres. The human 90th percentile is
  0.8415 over 107 humanities windows and 0.7448 over 65 technical ones, both
  above desklib's own 0.5 boundary, so desklib flags well over a tenth of
  provably human 2008 Extended Essay prose whatever the subject. That is a limit
  of the model, not of the corpus. The p90 itself is unstable as the corpus
  grows, so quote the finding rather than the number.

[Ejhfast/fast-ai-detector]: https://github.com/Ejhfast/fast-ai-detector
