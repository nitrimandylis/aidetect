---
name: aidetect-cli
description: Drive the aidetect CLI — counts a draft the way the IB counts it (by section, against a word limit) and scores prose offline for how AI-generated it reads. Use whenever the user asks how long a draft is, whether an EE or IA is over its word limit, which section is bloated, whether their writing reads as AI-written, how it would look to Turnitin, or mentions aidetect, Binoculars or the desklib detector.
---

# aidetect

One command, five subcommands, all safe to run unattended. Two are instant; two
download gigabytes on their first run. Knowing which is which is most of what
this skill is for.

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
| `aidetect count <file.docx> [--limit N] [--json]` | instant, no model | the IB word count, by section |
| `aidetect extract <in.docx> <out.txt>` | instant, no model | strips a draft down to finished prose |
| `aidetect score <file>` | **~1.5 GB download on first run**, then seconds | desklib DeBERTa, higher = more AI-ish, flags >= 0.5 |
| `aidetect bino <file> --mlx --pair gemma` | **~6 GB download + a local quantization on first run** | Binoculars, **lower** = more AI-ish |
| `aidetect calibrate --human-dir D --ai-dir D` | as `bino`, times the sample count | refits a threshold; needs data that does not ship |

**Default to `count`.** It answers the question the user usually has, costs
nothing, and needs no network. Only reach for `score` or `bino` when the user
actually asks about AI-detection, and say the download is coming before you
start one.

## Reading the count from a tool call

`count` takes `--json` and emits exactly one object on stdout. Use it rather than
parsing the table.

```json
{"sections": [{"title": "Introduction", "words": 812}], "total": 3940, "limit": 4000, "over": -60}
```

`over` is positive when the draft is over the limit, negative when it has room,
and `null` together with `limit` when no `--limit` was passed. An empty
`sections` list with `total: 0` is a real answer, not a failure. Errors exit
non-zero with a sentence on stderr, so branch on the exit code.

No other subcommand has `--json` yet; `score` and `bino` still print for humans.

## Things that will bite you

- **`score` and `bino` disagree by direction.** `score` is a probability where
  **high means AI-ish**. `bino` is a ratio where **low means AI-ish**. Reporting
  a Binoculars score as if high were bad inverts the verdict.
- **`bino`'s default pair is near-chance and must not be used.** `--pair small`
  separates the calibration set at 62%, `big` at 67%. Only `--mlx --pair gemma`
  (95.8%) is worth reporting. On this Mac always pass both flags.
- **`count` takes a `.docx` only.** It errors on `.txt`, because a text file has
  no headings or styles to find sections and quotes with. `score` and `extract`
  do accept `.txt`.
- **The scorers skip paragraphs under 25 words**, so a short or bullet-heavy
  draft can legitimately report "no paragraphs found". That is not a failure.
  `count` has no such floor and counts everything.
- **`count` strips a parenthetical only if it holds a 4-digit year, `ibid` or
  `et al`.** A citation style using none of those is counted as prose, which
  inflates the total. Say so if the draft's citations look unusual.
- **`calibrate` has no default data set.** `--human-dir` and `--ai-dir` are
  required, and the corpora deliberately do not ship in the package. From an
  install there is nothing to point them at; it needs a clone of the repo.
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
- It never touches the network after a model is cached.
