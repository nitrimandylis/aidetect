# corpora/

## What is in here

| folder | what | n |
|---|---|---|
| `human/` | body paragraphs from pre-2020 IB Extended Essays, humanities and social sciences | 93, from 31 essays |
| `human-tech/` | the same, from maths, sciences, ITGS and computer science | 51, from 17 essays |
| `ai/`, `ai-tech/` | one clean-room LLM paragraph per human paragraph, on the same topic and from the same position in the essay | 93 and 51, matched 1:1 |

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
can be certified.

A `peer/` folder of IB Computer Science IA paragraphs used to sit here for genre
comparison. It was deleted: nine of its twelve samples were unattributed student
coursework with `provenance: "unverified"` and no source URL, which is exactly
the claim the rest of this file cannot make good on. The genre question it
existed to answer is answered better by `human-tech`, which is certified and has
its own fitted threshold.

## Rebuilding the human corpora from scratch

Everything below runs from the repo, no manual steps:

```bash
tools/fetch_exemplars.sh scans          # 48 IBO exemplars from the Wayback Machine
tools/ocr_all.sh scans                  # 200 dpi render + Vision OCR -> scans/tsv
python3 tools/build_corpus.py --tsv-dir scans/tsv --out-dir corpora/human \
    --prefix h --subjects English History Geography Philosophy Politics \
                          Psychology Social Visual World Music
python3 tools/build_corpus.py --tsv-dir scans/tsv --out-dir corpora/human-tech \
    --prefix th --subjects Biology Chemistry Physics Mathmatics ITGS
```

`tools/ocr` is compiled from `ocr.swift` on first use and is not committed.
Keep `scans/` outside the repo: it is about 300 MB of PDFs.

Two of the 48 have no usable Wayback capture (Economics_1, English_7) and three
more yield no paragraph that passes the filters, so the collection route gives
44 essays. Four more come from outside the collection, one economics and three
computer science, each recorded in a folder's `sources-extra.json` with its own
date evidence. That is 48 essays in all: 31 humanities and 17 technical.

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
