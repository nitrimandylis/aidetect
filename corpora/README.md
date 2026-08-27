# corpora/

> **`ai/` and `ai-tech/` are STALE as of the human-corpus rebuild.**
>
> The human halves were rebuilt from 44 scanned IB exemplars (132 paragraphs,
> three per essay). The AI halves still hold the previous 12-sample sets, whose
> `matches` ids point at human samples that no longer exist. **Do not fit a
> threshold until they are regenerated**, or the two classes will be scored
> against unrelated topics.
>
> Regeneration was blocked on the NVIDIA NIM free-tier rate limit, not on
> anything in the code. When the quota resets:
>
> ```
> aidetect generate --topics corpora/human/manifest.json \
>     --out-dir corpora/ai --prefix a --seed 7 --workers 2
> aidetect generate --topics corpora/human-tech/manifest.json \
>     --out-dir corpora/ai-tech --prefix ta --seed 7 --workers 2
> ```
>
> The desklib amber bands do NOT depend on the AI half and are already refitted.


The labelled set `aidetect calibrate` fits a threshold on. Not shipped in the
wheel or the sdist (`pyproject.toml` excludes it), and not covered by this
repository's MIT licence. See **Licensing** below.

## What is in here

| folder | what | n |
|---|---|---|
| `human/` | body paragraphs from pre-2020 IB Extended Essays, humanities and social sciences | 3 per essay |
| `human-tech/` | the same, from maths, sciences, ITGS and computer science | 3 per essay |
| `ai/`, `ai-tech/` | one clean-room LLM paragraph per human paragraph, on the same topic and from the same position in the essay | matched 1:1 |
| `peer/` | IB Computer Science IA paragraphs, for comparison only | 6 |

Every folder has a `manifest.json`. Human entries record `source_url`,
`date_evidence`, `extraction`, `source_essay`, `position`, and a `sha256` of the
file. AI entries record the model, vendor, temperature, seed and the exact
prompt template used.

## Where the human text comes from

Almost all of it is the IBO collection *50 Excellent Extended Essays*, retrieved
through the Wayback Machine. Every PDF carries
`© International Baccalaureate Organization 2008` on every page and a 2008
`CreationDate` in its metadata, and every capture predates 2020. A handful of
samples come from other pre-2020 exemplars, each with its own `date_evidence`.

**The provenance is the point.** A threshold is only meaningful if the human
class is provably human, so nothing written after ChatGPT goes in it unless it
can be certified. That is also why `peer/` is quarantined: every sample in it
postdates ChatGPT and none can be certified, so fitting on it would let
AI-assisted text drag the human mean down. If peer samples are ever scored they
are reported as a separate comparison row and never merged into `human`.

## How the paragraphs were extracted

The IBO PDFs are page images. `pdftotext` returns the running header and nothing
else, so `tools/build_corpus.py` renders each page at 200 dpi, OCRs it with
macOS Vision, and rebuilds paragraphs from line geometry. Footnote superscripts
fuse to the preceding word when OCR'd (`walnuts"|8`), and those are stripped by
rules that `tests/test_build_corpus.py` proves are a byte-level no-op on every
sample that was hand-picked before the pipeline existed.

**No model ever rewrites this text.** The pipeline selects and it strips one
documented artifact; it does not edit prose. Letting an LLM tidy OCR damage
would put model-shaped writing into the human class, which is the same
contamination `generate.py` refuses for the AI class, mirrored and worse.

Three paragraphs per essay, one from each third of the body, because:

- the desklib amber band is the 90th percentile of human window scores, and a
  dozen windows cannot support a percentile;
- three paragraphs carry the register spread a real essay has, which is why
  `generate.py` is given the same three positions;
- roughly 8% of a 4000-word essay is a defensible excerpt and more is not, so
  three is a ceiling rather than a starting point.

## What OCR does to a score

The human class is transcribed from scans and the AI class arrives as clean
UTF-8 from an API. If OCR noise moved scores, the threshold would be partly
detecting "was this text scanned", which generalises to nothing when the tool is
pointed at a typed draft. So it was measured rather than assumed.

`tools/ocr_bias.py` does the paired version: take a born-digital exemplar, read
its text layer, render the same pages to images, OCR them, and match paragraph
to paragraph. Any difference is the transcription route and nothing else.
Comparing OCR'd essays against different born-digital essays would have
confounded the route with the author.

Measured on 17 paired paragraphs from the two born-digital exemplars, scored
with the gemma-mlx pair:

| | score |
|---|---|
| clean text layer, mean | 0.9111 |
| OCR of the same pages, mean | 0.9040 |
| **mean delta** | **-0.0071** |
| median character error rate | 2.33% |

OCR moves human prose **down**, that is very slightly toward the machine side,
on 11 of 17 paragraphs. The shift is about 3.4% of the gap between the human and
AI class means, so it is small, but the direction is the unhelpful one: a human
class shifted down drags the fitted cutoff down with it, and a lower cutoff is a
more lenient detector. A false negative is the one error this tool exists to
prevent.

Two caveats. Seventeen pairs from two essays supports a direction, not a precise
effect size. And the match rate was low (17 of 65 clean paragraphs) because
`pdftotext` and the geometry pipeline disagree about where paragraphs split;
unmatched paragraphs were dropped rather than force-paired, which is the
conservative choice.

Paragraphs from one essay share an author and are **not** independent
observations. `calibrate` groups them by essay and reports leave-one-essay-out
accuracy for that reason. `n_essays` in each threshold file is the real sample
size; `n_human` is not.

## Verifying a sample

Each human manifest entry carries the SHA-256 of its file, so the corpus can be
checked without anyone having to hand over the text:

    python3 -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read().strip().decode().encode()).hexdigest())" human/h07a.txt

## Licensing

The repository is MIT. **This directory is not.**

`human/` and `human-tech/` are short excerpts from Extended Essays written by
other students and published by the IB Organization. Copyright rests with those
authors and the IBO. They appear here as brief excerpts, roughly one paragraph
in twelve of each essay, used non-commercially to calibrate a detector, with no
substitution for the originals, which remain freely available at the
`source_url` in each manifest entry.

Nothing in this directory is offered under the MIT licence, and the MIT grant in
`LICENSE` does not extend to it. If you are the author of one of these essays
and want an excerpt removed, open an issue.

`ai/` and `ai-tech/` are model output generated for this repository and carry no
such restriction.
