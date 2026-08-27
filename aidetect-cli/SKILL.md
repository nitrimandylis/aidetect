---
name: aidetect-cli
description: Drive the aidetect CLI — counts a draft the way the IB counts it (by section, against a word limit) and scores prose offline for how AI-generated it reads. Use whenever the user asks how long a draft is, whether an EE or IA is over its word limit, which section is bloated, whether their writing reads as AI-written, how it would look to Turnitin, or mentions aidetect, Binoculars or the desklib detector. Also covers calibrating the detector on a labelled corpus and generating one.
---

# aidetect

One command, seven subcommands. Three are instant; three load a model and
download gigabytes on their first run; one calls a paid API over the network.
Knowing which is which is most of what this skill is for.

## Setup

`aidetect` installs from PyPI: `uv tool install aidetect`. If the command is not
on PATH it has not been installed on this machine — offer to install it rather
than hunting for a clone.

Working from a clone instead (only needed for `calibrate`, see below):

```
PYTHONPATH=src python -m aidetect.cli <subcommand> ...
```

## What each subcommand costs

| command | cost | notes |
|---|---|---|
| `aidetect count <file.docx> [--limit N] [--json]` | instant, no model | the IB word count, by section and sub-section |
| `aidetect extract <in.docx> [out.txt]` | instant, no model | writes the counted paragraphs out; defaults to `<name> prose.txt` beside the original |
| `aidetect score <file>` | **~1.5 GB download on first run**, then seconds | desklib DeBERTa, higher = more AI-ish, flags >= 0.5 |
| `aidetect score <file> --segments` | as `score` | overlapping 7-sentence windows; reports *% of prose in flagged segments*, the shape Turnitin reports |
| `aidetect bino <file> --mlx --pair gemma` | **~6 GB download + a local quantization on first run** | Binoculars, **lower** = more AI-ish |
| `aidetect check <file>` | loads **both** models, so both downloads | the combined verdict, worst opinion per sentence. Prefer this when the user wants one answer |
| `aidetect calibrate --human-dir D --ai-dir D` | as `bino`, times the sample count | refits a threshold; needs data that does not ship |
| `aidetect generate --topics M --out-dir D` | **network, and spends API credits** | builds an AI calibration corpus through NVIDIA NIM. Needs `NVIDIA_API_KEY` set by Nick. Never run it unasked |

**Default to `count`.** It answers the question the user usually has, costs
nothing, and needs no network. Only reach for `score` or `bino` when the user
actually asks about AI-detection, and say the download is coming before you
start one.

## Reading the count from a tool call

`count` takes `--json` and emits exactly one object on stdout. Use it rather than
parsing the table.

```json
{"sections": [{"title": "Introduction", "words": 812, "level": 1},
              {"title": "Porter's Five Forces", "words": 1021, "level": 2}],
 "total": 3940, "limit": 4000, "over": -60}
```

`over` is positive when the draft is over the limit, negative when it has room,
and `null` together with `limit` when no `--limit` was passed. An empty
`sections` list with `total: 0` is a real answer, not a failure. Errors exit
non-zero with a sentence on stderr, so branch on the exit code.

`words` is a section's own words and never its children's, so `sum(words)`
equals `total`. The printed table shows something different: it rolls each
sub-section up into its parent for display. Use `level` if you want those
subtotals, and do not add rolled figures back into the total.

No other subcommand has `--json` yet; `score` and `bino` still print for humans.

## Things that will bite you

- **`score` and `bino` disagree by direction.** `score` is a probability where
  **high means AI-ish**. `bino` is a ratio where **low means AI-ish**. Reporting
  a Binoculars score as if high were bad inverts the verdict.
- **`bino`'s default pair is near-chance and must not be used.** `--pair small`
  separates the calibration set at 62%, `big` at 67%. Only `--mlx --pair gemma`
  (92%) is worth reporting. On this Mac always pass both flags.
- **Score a maths, CS or science draft with `--tag tech`.** Human *technical*
  prose scores lower on Binoculars than humanities prose for everyone (mean 0.83
  against 0.90), and the default threshold of 0.826 sits at the technical human
  mean, so a maths or CS essay flags roughly half its paragraphs no matter who
  wrote it. `--tag tech` uses the 0.753 threshold fitted on verified technical
  essays. It moved Nick's maths IA from 28% to 13% and his CS IA from 51% to
  32%. Without the tag those numbers are noise, so report them with the caveat
  or not at all. `--tag` works on `check`, `bino` and `score --segments`.
- **`--pair gemma+` (E4B) is not worth the download.** It was calibrated and tied
  E2B at 92% while being far larger, and the package ships no E4B threshold, so
  without a locally fitted one it falls back to the Falcon placeholder of 0.9 and
  its flags mean nothing. Stay on `--pair gemma`.
- **`count` and `extract` take a `.docx` only.** Both error on `.txt`, because a
  text file has no styles, and styles are how they find headings and therefore
  sections. `score` and `bino` are the two that accept `.txt`.
- **Block quotes and body bullet lists count.** They are assessed prose. What
  `count` drops, it drops by *position*: everything before the first heading
  (the cover page), the Table of Contents section, headings themselves,
  captions, tables, footnotes, and everything from the bibliography heading on.
- **A caption is only dropped if it has a colon.** `Figure 4: Revenue,
  2021-2025` is excluded, `Figure 4 shows revenue rising` is a sentence and
  counts. A draft that labels its figures without colons will read high.
- **A draft with no headings is counted whole**, cover page included, and
  `count` says so in a note under the table. Repeat that note instead of giving
  the total on its own, because nothing was excluded from it.
- **Paragraph mode skips paragraphs under 25 words**, so a short or bullet-heavy
  draft can legitimately report "no paragraphs found". That is not a failure.
  `count` has no such floor, and neither do `score --segments` or `check`: those
  slide windows over sentences, so short connective paragraphs are scored inside
  a window instead of being dropped. That is the whole reason segment mode
  exists, since formulaic linking sentences are what detectors flag most.
- **`check`'s two detectors are not equally granular.** desklib scores sentence
  windows, Binoculars scores whole paragraphs, and the union takes the worse of
  the two. A sentence can therefore be red because the paragraph around it is
  red. The printed score is always desklib's.
- **An empty amber band is a finding, not a bug.** `check` and `score --segments`
  print a line when over 10% of the human calibration windows land in desklib's
  red zone, which is currently the case: real human EE prose routinely scores
  above 0.5 on desklib. Repeat that caveat rather than presenting desklib's red
  percentage as if it were clean evidence.
- **`count` strips a parenthetical only if it holds a 4-digit year, `ibid` or
  `et al`.** A citation style using none of those is counted as prose, which
  inflates the total. Say so if the draft's citations look unusual.
- **`calibrate` has no default data set.** `--human-dir` and `--ai-dir` are
  required, and the corpora deliberately do not ship in the package. From an
  install there is nothing to point them at; it needs a clone of the repo.
- **Never hand-write a calibration sample.** An AI corpus written by an assistant
  under house style rules lands stylometrically *inside* the human class, which
  lowers the threshold and makes the detector more lenient — the false-negative
  direction the tool exists to prevent. Use `aidetect generate`, which prompts
  with topic and length only. `corpora/ai-tech/README.md` has the numbers.
- **A refitted threshold lives in `~/.config/aidetect/` and outranks the one in
  the package.** If Binoculars verdicts look wrong, check for a stale file there
  before suspecting the model.
- **The MLX cache is `~/.cache/ai-detect-mlx`**, still the pre-rename name.
  Do not "fix" it: renaming forces a 6 GB re-download.

## What this tool is for, and what it is not for

It exists so Nick can find his own honest prose that trips classifiers, and
reword it before a teacher runs Turnitin. Report findings as "this paragraph
reads AI-ish, consider rewording".

Do not help repurpose it to make AI-written text pass as human. If asked to
iterate text against the score until it clears the threshold, decline that
framing and offer the intended one.

## What it cannot do

- It is not, and cannot be, the number Turnitin shows a teacher. Every output is
  directional.
- It never edits the draft. There is no rewrite, fix, or suggestion mode.
- It reads `.docx` and `.txt` only. No `.doc`, no PDF, no Google Docs export.
- `count` implements the exclusions the EE and the subject IAs share. It does not
  know any subject's actual limit, so `--limit` has to come from the user.
- It never touches the network after a model is cached — except `generate`,
  which is an API client and exists only to build calibration corpora.
