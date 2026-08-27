# known_clean/

The 24 human samples as they were hand-picked, before `tools/build_corpus.py`
existed. They carry no OCR damage of any kind.

They live here, outside `corpora/`, so the guarantee that the footnote-stripping
rules never touch clean prose survives the corpus being rebuilt. Pointing that
check at `corpora/` would have made it vacuous the moment the corpus was
replaced with pipeline output.

Do not edit these. They are a fixture, not a corpus: `calibrate` must never be
pointed at this folder.
