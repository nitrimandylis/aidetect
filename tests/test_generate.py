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

from aidetect.generate import (POPULAR_MODELS, POSITIONED_TEMPLATE,  # noqa: E402
                               sample_id_for,
                               PROMPT_TEMPLATE, build_prompt, clean,
                               looks_like_prose, pick_models, trim_to_words,
                               vendor_of)


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
    # Both templates. The positioned one adds a structural hint (which section
    # of the essay to write), which is allowed for the same reason the word
    # count is: it says what to produce, not how to write it. This test is what
    # keeps that distinction from eroding into style guidance later.
    for template in (PROMPT_TEMPLATE, POSITIONED_TEMPLATE):
        lowered = template.lower()
        for word in banned:
            assert word not in lowered, f"prompt template steers style: {word!r}"


def test_position_is_structural_and_optional():
    """A missing position must generate exactly as it did before positions
    existed, so an older topics file is unaffected."""
    with_position = build_prompt("Alhazen's billiard problem", 110, "conclusion")
    without = build_prompt("Alhazen's billiard problem", 110)
    assert "conclusion section" in with_position
    assert without == PROMPT_TEMPLATE.format(topic="Alhazen's billiard problem", words=110)
    assert "section" not in without


def test_ai_id_mirrors_the_human_id_it_matches():
    """calibrate groups both halves of the set by the digits in the id, so an
    AI sample must keep the essay number and the paragraph letter of the human
    paragraph it was generated against."""
    assert sample_id_for("th07a", "ta") == "ta07a"
    assert sample_id_for("h12c", "a") == "a12c"
    # the pre-three-paragraph ids end in a digit and have no letter
    assert sample_id_for("h01", "a") == "a01"


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


def test_a_reasoning_trace_is_not_prose():
    """A real sample from nemotron-3-nano: the model planned out loud instead of
    writing. Scoring chat scaffolding as 'AI prose' teaches the threshold the
    wrong thing, so it has to be rejected rather than saved."""
    leaked = ("We need to write a single paragraph about 110 words, from an IB "
              "Extended Essay on Wireless in Local Loop. Only the paragraph.")
    assert looks_like_prose(leaked) is False

    # A real one that reached the corpus before this was tightened: a numbered
    # planning trace, matching no marker phrase at all.
    numbered = ("1. **Analyze the Request:** - **Task:** Write a single paragraph "
                "of about 110 words. - **Source/Context:** Introduction section.")
    assert looks_like_prose(numbered) is False
    real = ("Wireless in Local Loop technology has been proposed as a means of "
            "delivering voice and data services to rural India.")
    assert looks_like_prose(real) is True


def test_trim_keeps_whole_sentences_within_budget():
    text = "One two three four five. Six seven eight nine ten. Eleven twelve."
    # stops at the first sentence that reaches the budget, never mid-sentence
    assert trim_to_words(text, 5) == "One two three four five."
    assert trim_to_words(text, 8) == "One two three four five. Six seven eight nine ten."
    # a budget past the end returns everything
    assert trim_to_words(text, 100) == text


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
