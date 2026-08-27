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

from aidetect.generate import PROMPT_TEMPLATE, build_prompt, clean  # noqa: E402


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
