"""
The segment logic decides what gets flagged and what the headline percentage
says, so the window arithmetic is worth pinning down. Model-free on purpose:
segments.py must stay importable and testable without torch.

Run with `python -m pytest tests/test_segments.py`, or just
`python tests/test_segments.py`.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from aidetect.segments import (STRIDE, WINDOW, build_windows, classify,  # noqa: E402
                               document_sentences, flagged_runs, sentence_scores,
                               split_sentences, word_shares, worse)


def test_split_sentences_basics():
    assert split_sentences("One here. Two here! Three here?") == \
        ["One here.", "Two here!", "Three here?"]
    # a closing curly quote after the full stop must not glue two sentences
    assert split_sentences("He said “stop.” Then he left.") == \
        ["He said “stop.”", "Then he left."]


def test_every_sentence_lands_in_a_window():
    """The whole point of windows over paragraphs: nothing is skipped."""
    for count in (0, 1, WINDOW - 1, WINDOW, WINDOW + 1, 3 * WINDOW + 2):
        covered = set()
        for start, end in build_windows(count):
            covered.update(range(start, end))
        assert covered == set(range(count)), count


def test_windows_overlap():
    windows = build_windows(20)
    # consecutive windows share sentences (stride < window)
    assert windows[0] == (0, WINDOW)
    assert windows[1][0] == STRIDE
    assert windows[1][0] < windows[0][1]


def test_short_paragraphs_are_absorbed_not_skipped():
    """The regression that motivated segment mode: a 5-word connective
    paragraph is invisible to the paragraph scorer but must appear here."""
    paragraphs = ["A long enough opening paragraph sits here with plenty of words in it.",
                  "This matters greatly.",     # 3 words, under MIN_WORDS
                  "Another full paragraph follows the short one and closes the section."]
    sentences = document_sentences(paragraphs)
    texts = [sentence for _number, sentence in sentences]
    assert "This matters greatly." in texts
    # and it keeps its paragraph number for the bino union in check.py
    assert sentences[1] == (1, "This matters greatly.")


def test_a_sentence_takes_its_worst_window():
    # sentence 3 sits in both windows; the bad window must win
    windows = [(0, 4), (2, 6)]
    scores = sentence_scores(6, windows, [0.1, 0.9])
    assert scores[3] == 0.9
    assert scores[0] == 0.1


def test_classify_and_worse_ordering():
    assert classify(0.7, red=0.5, amber=0.35) == "red"
    assert classify(0.4, red=0.5, amber=0.35) == "amber"
    assert classify(0.1, red=0.5, amber=0.35) == "clean"
    assert worse("clean", "amber") == "amber"
    assert worse("red", "amber") == "red"
    assert worse("clean", "clean") == "clean"


def test_shares_are_word_weighted():
    # 8 red words out of 10 total: the headline is 80%, not "1 of 2 sentences"
    sentences = [(0, "Eight words make up this first red sentence."),
                 (0, "Two words.")]
    red_share, amber_share = word_shares(sentences, ["red", "clean"])
    assert red_share == 0.8 and amber_share == 0.0


def test_flagged_runs_group_and_carry_the_worst_status():
    statuses = ["clean", "amber", "red", "amber", "clean", "amber"]
    assert flagged_runs(statuses) == [(1, 4, "red"), (5, 6, "amber")]
    assert flagged_runs(["clean", "clean"]) == []


def test_segments_never_imports_torch():
    """segments.py is the shared logic under `score --segments` and `check`;
    keeping it torch-free is what lets these tests run in milliseconds."""
    import subprocess
    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    env = dict(os.environ, PYTHONPATH=src)
    code = ("import sys, aidetect.segments; "
            "sys.exit(1 if 'torch' in sys.modules else 0)")
    assert subprocess.run([sys.executable, "-c", code], env=env).returncode == 0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all segment checks passed")
