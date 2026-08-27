"""List items are not prose.

Segment mode drops the 25-word floor so short connective sentences get scored
inside a window rather than skipped. The cost was that an IA's success-criteria
table and its numbered design breakdown reached the detector as prose and drove
16% of that draft into the flagged bucket, which measures formatting rather
than writing.

The risk in the other direction is worse than the bug: dropping a real paragraph
because it opens with an initial would hide prose the author needs to see. So
the lookalike cases below matter as much as the list cases.
"""

import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from aidetect.text import is_list_item, is_prose  # noqa: E402

REPO = os.path.join(os.path.dirname(__file__), "..")

LIST_ITEMS = [
    "SC12\tHighlight the active filter or sort option in the UI",
    "SC16\tDisplay photo count and total library size in the gallery header",
    "FR3  The system shall validate uploads",
    "1. A storage layer that defines the database tables and opens connections.",
    "2)  A data-access layer that reads and writes photos.",
    "2.",
    "• the interface renders the gallery, the detail screen and the upload page",
    "- a routing layer that ties the components together",
]

# Prose that a slightly greedier rule would eat.
NOT_LIST_ITEMS = [
    "T. S. Eliot wrote that April is the cruellest month, a claim the poem earns.",
    "V. Nabokov's Lolita opens with a narrator already condemned by his own telling.",
    "2008 saw the release of the paper this essay builds on.",
    "H2O was the solvent used throughout the experiment.",
    "The minimum is 13, achieved by pairing C with G along C-D-H-G.",
    "iPhone sales fell that quarter, which the annual report attributes to supply.",
]


def test_catches_the_items_that_inflated_the_cs_ia():
    for text in LIST_ITEMS:
        assert is_list_item(text), text


def test_leaves_prose_that_merely_looks_like_a_list():
    for text in NOT_LIST_ITEMS:
        assert not is_list_item(text), text


def test_a_list_item_is_never_prose():
    """is_prose is the gate both `check` and `score --segments` go through."""
    for text in LIST_ITEMS:
        assert not is_prose(text, min_words=0), text


def test_the_calibration_corpus_is_untouched():
    """Every human and AI sample must still count as prose. If this fails the
    rule is too greedy and the threshold would be fitted on a filtered set."""
    wrongly_dropped = []
    for pattern in ("corpora/human/*.txt", "corpora/human-tech/*.txt",
                    "corpora/ai/*.txt", "corpora/ai-tech/*.txt",
                    "tests/fixtures/known_clean/*.txt"):
        for path in glob.glob(os.path.join(REPO, pattern)):
            text = open(path, encoding="utf-8").read().strip()
            if is_list_item(text):
                wrongly_dropped.append(os.path.basename(path))
    assert not wrongly_dropped, wrongly_dropped


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all list-item checks passed")
