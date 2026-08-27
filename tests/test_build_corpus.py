"""The strip rules are the only place the corpus builder edits prose, so they
are the only thing here that needs a test.

Two guarantees, and the second matters more than the first:
  1. the five OCR'd footnote forms measured on English_1 are removed
  2. nothing else is touched, proven against the 24 hand-picked samples that
     are known to carry no OCR damage at all
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import build_corpus  # noqa: E402

KNOWN_CLEAN = os.path.join(os.path.dirname(__file__), "fixtures", "known_clean")

DAMAGED = [
    ('visit to a "poor sick family" 4 on a charitable endeavour',
     'visit to a "poor sick family" on a charitable endeavour'),
    ('a great increase of love"s. She then tries',
     'a great increase of love". She then tries'),
    ('on "a warm day in summer°, hoping to awaken',
     'on "a warm day in summer, hoping to awaken'),
    ('a "groundwork of anticipation"|? foreshadowing',
     'a "groundwork of anticipation" foreshadowing'),
    ('some walnuts"|8. One could infer',
     'some walnuts". One could infer'),
    ('the society of Highbury"\'\', Emma is not alone',
     'the society of Highbury", Emma is not alone'),
    ('her "absolutely insufferable" . She shares',
     'her "absolutely insufferable". She shares'),
    ('"it was summer again"?. It seems unlike Austen',
     '"it was summer again". It seems unlike Austen'),
]

# Prose the rules must not touch. Every one of these looks like damage to a
# rule that is even slightly too greedy.
UNTOUCHED = [
    'She said "no" I left the room.',          # the pronoun is not a footnote
    'He replied "yes" so we continued.',       # nor is a word starting with s
    'the reaction of H2O at 25°C produced 3n+1 results',
    'Austen calls her an "imaginist" throughout the novel.',
    'Emma\'s "lawn and shrubberies", and her occasional walks into Highbury.',
]


def test_strips_measured_damage():
    for damaged, expected in DAMAGED:
        assert build_corpus.strip_markers(damaged) == expected, damaged


def test_leaves_clean_prose_alone():
    for text in UNTOUCHED:
        assert build_corpus.strip_markers(text) == text, text


def test_noop_on_every_existing_sample():
    """The 24 hand-picked samples carry no OCR damage of any kind, so any
    edit to them means a rule reaches too far. They live in tests/fixtures so
    this stays true after corpora/ is rebuilt from the pipeline."""
    changed = build_corpus.verify_noop(KNOWN_CLEAN)
    assert not changed, f"strip rules edited known-clean samples: {changed}"


if __name__ == "__main__":
    test_strips_measured_damage()
    test_leaves_clean_prose_alone()
    test_noop_on_every_existing_sample()
    print("ok")
