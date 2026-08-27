"""Grouping and leave-one-essay-out.

The point of these is that the accuracy number in a threshold file must not be
inflated by paragraphs that share an author. Everything here runs on cached
floats, so no model is loaded.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from aidetect.calibrate import (group_of, leave_one_essay_out,  # noqa: E402
                                percentile, pick_threshold)


def test_group_is_the_essay_not_the_paragraph():
    assert group_of("h07a") == group_of("h07b") == group_of("h07c") == "07"
    assert group_of("th12a") == group_of("ta12a") == "12"      # human pairs with its AI
    assert group_of("h07") != group_of("h08")


def test_old_single_paragraph_ids_are_one_group_each():
    """h01..h12 predate the three-paragraph layout and must be unaffected."""
    assert len({group_of(f"h{i:02d}") for i in range(1, 13)}) == 12


def test_leave_one_essay_out_is_not_flattered_by_clustering():
    """Separable clusters: both numbers should agree and be perfect."""
    human = [(f"h{e:02d}{p}", 0.90 + e * 0.001) for e in range(1, 9) for p in "abc"]
    ai = [(f"a{e:02d}{p}", 0.60 + e * 0.001) for e in range(1, 9) for p in "abc"]
    loo, n_essays = leave_one_essay_out(human, ai)
    assert n_essays == 8, n_essays
    assert loo == 1.0, loo


def test_leave_one_essay_out_punishes_a_cutoff_that_only_fits_one_essay():
    """One essay's paragraphs sit between the two clusters.

    Fitting on everything drags the cutoff down to scoop them up, and then
    credits itself for all three: a perfect in-sample score. Hold that essay
    out and the cutoff goes back where the other seven put it, which gets all
    three of the held-out paragraphs wrong. That gap is the inflation, and it
    is exactly what three-paragraphs-per-essay would have hidden.
    """
    human = []
    for essay in range(1, 8):
        for paragraph in "abc":
            human.append((f"h{essay:02d}{paragraph}", 0.90))
    for paragraph in "abc":
        human.append((f"h08{paragraph}", 0.65))      # unusually machine-like author

    ai = []
    for essay in range(1, 9):
        for paragraph in "abc":
            ai.append((f"a{essay:02d}{paragraph}", 0.60))

    _cutoff, in_sample = pick_threshold([s for _, s in human], [s for _, s in ai])
    leave_out, _essays = leave_one_essay_out(human, ai)

    assert in_sample == 1.0, in_sample
    assert leave_out < in_sample, (leave_out, in_sample)


def test_percentile_does_not_drift_down_with_sample_size():
    """The reason amber stopped being a minimum: draw more samples from the
    same distribution and min() keeps falling, p10 does not."""
    small = [0.80 + i * 0.01 for i in range(10)]
    large = [0.80 + i * 0.001 for i in range(100)]
    assert min(large) <= min(small)
    assert abs(percentile(large, 0.10) - percentile(small, 0.10)) < 0.05


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
