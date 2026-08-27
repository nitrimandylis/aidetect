"""
The generator decides what the AI half of a calibration set looks like, and a
weak adversary silently makes the whole tool more lenient. These checks pin down
the two things that matter and need no network: the prompt carries no style
guidance, and nothing runs without a key.

Run with `python -m pytest tests/test_generate.py`, or `python tests/test_generate.py`.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from aidetect.generate import (POPULAR_MODELS, PROMPT_TEMPLATE, build_prompt,  # noqa: E402
                               clean, pick_models, vendor_of)


def test_prompt_carries_topic_and_length_only():
    prompt = build_prompt("Alhazen's billiard problem", 110)
    assert "Alhazen's billiard problem" in prompt
    assert "110" in prompt


def test_prompt_has_no_style_guidance():
    """The contamination that quarantined corpora/ai-tech came from style rules
    leaking into the AI class. Any of these words in the template means the
    adversary is being steered, which biases the threshold toward leniency."""
    banned = ("style", "tone", "voice", "concise", "formal", "academic voice",
              "avoid", "do not use", "em dash", "active voice", "like a student",
              "human", "natural")
    lowered = PROMPT_TEMPLATE.lower()
    for word in banned:
        assert word not in lowered, f"prompt template steers style: {word!r}"


def test_clean_strips_wrapper_but_not_prose():
    raw = 'Here is the paragraph:\n\n"The law of reflection states that the angle is equal."\n'
    assert clean(raw) == "The law of reflection states that the angle is equal."
    # a normal paragraph passes through untouched
    body = "Cellular automata are large groups of interacting finite state machines."
    assert clean(body) == body


def test_picks_spread_across_vendors_before_repeating_one():
    """Variety is the point: twelve paragraphs from one vendor would make the
    AI class that vendor's habits instead of machine writing in general."""
    pool = ["a/one", "a/two", "a/three", "b/one", "b/two", "c/one"]
    chosen = pick_models(pool, 3, seed=1)
    assert len({vendor_of(m) for m in chosen}) == 3, chosen
    # taking every model uses each exactly once
    everything = pick_models(pool, len(pool), seed=1)
    assert sorted(everything) == sorted(pool)


def test_more_topics_than_models_cycles_instead_of_stopping():
    pool = ["a/one", "b/one"]
    chosen = pick_models(pool, 5, seed=3)
    assert len(chosen) == 5
    assert set(chosen) == set(pool)


def test_picking_is_repeatable_with_a_seed():
    """A calibration corpus has to be reproducible, so the same seed must give
    the same assignment; without one the run is deliberately fresh."""
    assert pick_models(POPULAR_MODELS, 12, seed=42) == pick_models(POPULAR_MODELS, 12, seed=42)


def test_the_detector_family_is_never_sampled():
    """Generating with Gemma and scoring with the Gemma Binoculars pair would
    flatter the detector: its own family's output is unusually unsurprising."""
    assert not [m for m in POPULAR_MODELS if "gemma" in m.lower()]


def test_no_key_is_an_error_not_a_silent_skip():
    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    env = {k: v for k, v in os.environ.items() if k != "NVIDIA_API_KEY"}
    env["PYTHONPATH"] = src
    result = subprocess.run(
        [sys.executable, "-c", "import sys; from aidetect.cli import main; sys.exit(main() or 0)",
         "generate", "--topics", "x.json", "--out-dir", "/tmp/aidetect-gen-test"],
        env=env, capture_output=True, text=True)
    assert result.returncode != 0, "missing API key exited 0"
    assert "NVIDIA_API_KEY" in result.stderr, result.stderr


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all generate checks passed")
