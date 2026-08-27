"""
Generate the AI half of a calibration set with a clean-room model.

Why this exists: the AI class has to be a FAIR ADVERSARY. If the AI samples are
written by an assistant carrying house style rules (write tightly, no em dashes,
active voice), they come out more human-like than untuned model output. That
pulls the two clusters together, lowers the fitted threshold, and makes the
detector more lenient — a false negative is the one error this tool exists to
prevent. It happened once already, which is why corpora/ai-tech was quarantined.

So the generator calls hosted models over NVIDIA NIM with NO system prompt and
NO style guidance in the user prompt: only the topic and a word count.

By default it samples popular models ACROSS VENDORS, one paragraph each, so the
AI class is machine writing in general rather than one model's habits — different
model, different tokenizer, different training mix. The Gemma family is left out
on purpose: it is the detector's own pair, and scoring Gemma output with a Gemma
observer/performer would flatter the detector.

    export NVIDIA_API_KEY=nvapi-...        # you set this, aidetect never writes it
    aidetect generate --topics corpora/human-tech/manifest.json \
                      --out-dir corpora/ai-tech --prefix ta --seed 7

Pass --seed to make the model assignment repeatable; pass --model (repeatable) to
pin exact models instead of sampling.

Get a key (and free credits) at https://build.nvidia.com. NIM is OpenAI-
compatible, so this needs no SDK: urllib posts the JSON itself.

The output manifest records the model, the exact prompt template and the
temperature, so a calibration fitted on this set can be audited or reproduced.
"""

import argparse
import json
import os
import random
import urllib.error
import urllib.request

NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NIM_CATALOG_URL = "https://integrate.api.nvidia.com/v1/models"

# Popular general-purpose chat models, most-wanted first. NIM's catalog endpoint
# lists what is served but publishes no popularity figure, so this ranking is
# hand-kept; it is INTERSECTED with the live catalog at run time, so an entry
# that disappears is dropped instead of 404-ing mid-corpus.
#
# Deliberately excluded:
#   - google/gemma*  the detector's own family. Generating with Gemma and then
#     scoring with a Gemma observer/performer pair flatters the detector: its
#     own family's output is unusually unsurprising to it.
#   - code, embedding, vision, safety-guard, reward, translate and parse models,
#     which either cannot hold a conversation or write nothing like essay prose.
POPULAR_MODELS = [
    "deepseek-ai/deepseek-v4-pro-0813",
    "moonshotai/kimi-k3",
    "openai/gpt-oss-120b",
    "nvidia/nemotron-3-super-120b-a12b",
    "mistralai/mistral-large-2-instruct",
    "meta/muse-glimmer-30b",
    "minimaxai/minimax-m3",
    "microsoft/phi-3.5-moe-instruct",
    "moonshotai/kimi-k2.6",
    "deepseek-ai/deepseek-v4-flash-0731",
    "openai/gpt-oss-20b",
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "ibm/granite-3.0-8b-instruct",
    "mistralai/mixtral-8x22b-v0.1",
    "01-ai/yi-large",
    "ai21labs/jamba-1.5-large-instruct",
    "stepfun-ai/step-3.7-flash",
    "databricks/dbrx-instruct",
    "writer/palmyra-creative-122b",
    "zyphra/zamba2-7b-instruct",
]

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


def fetch_catalog(timeout=30):
    """Model ids NIM is serving right now. The listing endpoint is public, so
    this needs no key: only generation is billed."""
    request = urllib.request.Request(NIM_CATALOG_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.load(response)
    return {entry["id"] for entry in body.get("data", [])}


def vendor_of(model_id):
    """'mistralai/mistral-large-2-instruct' -> 'mistralai'. The vendor is the
    best cheap proxy for a distinct tokenizer and architecture."""
    return model_id.split("/")[0]


def pick_models(pool, count, seed=None):
    """Choose `count` models from `pool`, spreading across vendors first.

    Variety is the whole point: twelve paragraphs from one model would make the
    AI class that model's habits rather than machine writing in general. Taking
    one model per vendor before taking a second from any vendor maximises the
    spread of tokenizers and architectures. Returns fewer than `count` only if
    the pool itself is smaller, and repeats models (still vendor-spread) when
    there are more topics than models.
    """
    rng = random.Random(seed)
    by_vendor = {}
    for model in pool:
        by_vendor.setdefault(vendor_of(model), []).append(model)
    for models in by_vendor.values():
        rng.shuffle(models)

    vendors = list(by_vendor)
    rng.shuffle(vendors)

    # Order the whole pool by rounds: every vendor's first model, then every
    # vendor's second, and so on. Taking a prefix of this list therefore uses
    # as many different vendors as possible.
    ordered = []
    round_number = 0
    while len(ordered) < len(pool):
        for vendor in vendors:
            models = by_vendor[vendor]
            if round_number < len(models):
                ordered.append(models[round_number])
        round_number += 1

    if not ordered:
        return []
    # More topics than models: cycle the same spread order rather than stopping.
    return [ordered[i % len(ordered)] for i in range(count)]


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
                    help="pin a NIM model id; repeat to rotate. Default: sample "
                         "popular models across vendors")
    ap.add_argument("--seed", type=int, default=None,
                    help="seed the model sampling so a corpus can be regenerated")
    ap.add_argument("--words", type=int, default=110,
                    help="target words per paragraph (default %(default)s)")
    args = ap.parse_args(argv)

    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        ap.error("NVIDIA_API_KEY is not set. Get a key at https://build.nvidia.com and "
                 "export it yourself; aidetect never stores it.")

    with open(args.topics, encoding="utf-8") as f:
        topics = json.load(f)

    if args.model:
        models = [args.model[i % len(args.model)] for i in range(len(topics))]
    else:
        try:
            catalog = fetch_catalog()
        except (urllib.error.URLError, urllib.error.HTTPError) as error:
            raise SystemExit(f"could not read the NIM model catalog: {error}")
        pool = [model for model in POPULAR_MODELS if model in catalog]
        if not pool:
            raise SystemExit(
                "none of the known popular models are in NIM's catalog any more. "
                "Pass --model explicitly, or refresh POPULAR_MODELS in generate.py.")
        dropped = [model for model in POPULAR_MODELS if model not in catalog]
        if dropped:
            print(f"not served any more, skipping: {', '.join(dropped)}")
        models = pick_models(pool, len(topics), args.seed)
        vendors = sorted({vendor_of(model) for model in models})
        print(f"sampling {len(set(models))} models across {len(vendors)} vendors: "
              f"{', '.join(vendors)}")
        if args.seed is None:
            print("no --seed given, so this exact model assignment will not repeat")

    os.makedirs(args.out_dir, exist_ok=True)

    written = []
    for index, entry in enumerate(topics):
        human_id = entry["id"]
        # th01 -> ta01: keep the number, swap the prefix, so the pairing is obvious
        number = "".join(c for c in human_id if c.isdigit())
        out_id = f"{args.prefix}{number}"
        model = models[index]
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
            "vendor": vendor_of(model),
            "temperature": TEMPERATURE,
            "prompt_template": PROMPT_TEMPLATE,
            "words_requested": args.words,
            "seed": args.seed,
        })

    manifest_path = os.path.join(args.out_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(written, f, indent=2)
    used = sorted({row["generated_by"] for row in written})
    print(f"\nwrote {len(written)} samples + manifest -> {args.out_dir}")
    print(f"models used ({len(used)}): {', '.join(used)}")
    print("check a couple by eye before calibrating: a refusal or a chatty preamble "
          "would poison the class.")
    return 0
