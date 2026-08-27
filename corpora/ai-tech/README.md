# ai-tech is QUARANTINED — do not calibrate on it

These 12 paragraphs were written by Claude inside a session whose system prompt
carried Nick's global writing rules (no em dashes, active voice, no filler
adjectives, concrete over abstract). That makes them a **weaker adversary than
untuned LLM output**, and stylometry confirms it:

| corpus | mean sentence length | commas per sentence |
|---|---|---|
| `ai/` (original AI class) | 35.1 | 1.90 |
| `human/` (its human class) | 25.3 | 1.57 |
| **`ai-tech/` (this folder)** | **25.8** | **1.16** |
| `human-tech/` (its human class) | 24.5 | 1.12 |

The original AI class is clearly separated from its human class. This one is
nearly identical to its human class. The human side barely moved between the
two corpora (25.3 → 24.5), so the shift is not a genre effect: it is the author.

A too-human AI class pulls the two clusters together, lowers the fitted
threshold, and makes the detector **more lenient** — the false-negative
direction, which is the error this tool exists to avoid.

The 79% separation measured on this pair is therefore not a clean genre finding.
It confounds two effects: the real technical-prose gap, and this contamination.

Regenerating it needs a generator that is NOT carrying house style rules.
`human-tech/` is unaffected: those are transcriptions of pre-2013 published
essays and remain usable.
