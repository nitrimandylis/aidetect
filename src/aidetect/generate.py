"""
Generate the AI half of a calibration set with a clean-room model.

Why this exists: the AI class has to be a FAIR ADVERSARY. If the AI samples are
written by an assistant carrying house style rules (write tightly, no em dashes,
active voice), they come out more human-like than untuned model output. That
pulls the two clusters together, lowers the fitted threshold, and makes the
detector more lenient — a false negative is the one error this tool exists to
prevent. It happened once already, which is why corpora/ai-tech was quarantined.

So the generator calls a hosted model over NVIDIA NIM with NO system prompt and
NO style guidance in the user prompt: only the topic and a word count. Prefer
models from a different family than the detector's own pair, so the adversary is
not drawn from the distribution the detector knows best. Pass --model more than
once and it rotates across topics, which stops the class becoming one model's
quirks.

    export NVIDIA_API_KEY=nvapi-...        # you set this, aidetect never writes it
    aidetect generate --topics corpora/human-tech/manifest.json \
                      --out-dir corpora/ai-tech --prefix ta

Get a key (and free credits) at https://build.nvidia.com. NIM is OpenAI-
compatible, so this needs no SDK: urllib posts the JSON itself.

The output manifest records the model, the exact prompt template and the
temperature, so a calibration fitted on this set can be audited or reproduced.
"""

import argparse
import json
import os
import urllib.error
import urllib.request

NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# Different family from the detector's Gemma pair, on purpose.
DEFAULT_MODELS = ["meta/llama-3.3-70b-instruct"]

# The whole point: topic and length, nothing about tone, register or style.
# Do NOT add "write like a student" or any style hint here. Any styling makes
# the adversary weaker and the threshold more lenient.
PROMPT_TEMPLATE = (
    "Write a single paragraph of about {words} words from an IB Extended Essay "
    "on the following topic:\n\n{topic}\n\n"
    "Return only the paragraph itself, with no title, heading or commentary."
)

TEMPERATURE = 1.0   # the model's own default register; low temp writes flatter prose


def build_prompt(topic, words):
    return PROMPT_TEMPLATE.format(topic=topic, words=words)


def call_nim(prompt, model, api_key, timeout=120):
    """POST one chat completion to NIM and return the text.

    No system message is sent at all: an empty-string system prompt still steers
    some models, and the whole point is an untuned voice.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": TEMPERATURE,
        "max_tokens": 1024,
    }
    request = urllib.request.Request(
        NIM_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.load(response)
    return body["choices"][0]["message"]["content"].strip()


def clean(text):
    """Strip the wrapper a chat model sometimes adds around the paragraph.

    Only leading/trailing junk is removed. The prose itself is never edited:
    editing it would put my own style back into the adversary.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    # drop a leading markdown heading or a "Here is..." lead-in
    while lines and (lines[0].startswith("#") or lines[0].rstrip().endswith(":")):
        lines.pop(0)
    return " ".join(line.strip() for line in lines).strip().strip('"')


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="aidetect generate",
        description="Generate the AI half of a calibration set with a clean-room model (NVIDIA NIM).")
    ap.add_argument("--topics", required=True,
                    help="manifest.json of the human set: each entry needs 'id' and 'topic'")
    ap.add_argument("--out-dir", required=True, help="folder to write the .txt files into")
    ap.add_argument("--prefix", default="a",
                    help="filename prefix for generated samples (default %(default)s)")
    ap.add_argument("--model", action="append", default=None,
                    help="NIM model id; repeat to rotate models across topics "
                         f"(default {DEFAULT_MODELS[0]})")
    ap.add_argument("--words", type=int, default=110,
                    help="target words per paragraph (default %(default)s)")
    args = ap.parse_args(argv)

    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        ap.error("NVIDIA_API_KEY is not set. Get a key at https://build.nvidia.com and "
                 "export it yourself; aidetect never stores it.")

    models = args.model or DEFAULT_MODELS
    with open(args.topics, encoding="utf-8") as f:
        topics = json.load(f)
    os.makedirs(args.out_dir, exist_ok=True)

    written = []
    for index, entry in enumerate(topics):
        human_id = entry["id"]
        # th01 -> ta01: keep the number, swap the prefix, so the pairing is obvious
        number = "".join(c for c in human_id if c.isdigit())
        out_id = f"{args.prefix}{number}"
        model = models[index % len(models)]
        prompt = build_prompt(entry["topic"], args.words)

        print(f"{out_id}  {model}  {entry['topic'][:50]}...")
        try:
            text = clean(call_nim(prompt, model, api_key))
        except urllib.error.HTTPError as error:
            # the body usually says which model id is wrong or which limit was hit
            detail = error.read().decode("utf-8", "replace")[:300]
            raise SystemExit(f"NIM returned {error.code} for model {model!r}: {detail}")
        except urllib.error.URLError as error:
            raise SystemExit(f"could not reach NIM: {error.reason}")
        if not text:
            raise SystemExit(f"{out_id}: model returned nothing; corpus left incomplete")

        path = os.path.join(args.out_dir, f"{out_id}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        written.append({
            "id": out_id,
            "matches": human_id,
            "subject": entry.get("subject"),
            "topic": entry["topic"],
            "generated_by": model,
            "temperature": TEMPERATURE,
            "prompt_template": PROMPT_TEMPLATE,
            "words_requested": args.words,
        })

    manifest_path = os.path.join(args.out_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(written, f, indent=2)
    print(f"\nwrote {len(written)} samples + manifest -> {args.out_dir}")
    print("check a couple by eye before calibrating: a refusal or a chatty preamble "
          "would poison the class.")
    return 0
