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
import collections
import concurrent.futures
import json
import os
import random
import re
import threading
import time
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
# Ordered so the models most accounts can actually call come first: a free NIM
# account 404s on much of the catalog, and a model that is listed but not
# callable costs a wasted request before the fallback kicks in.
POPULAR_MODELS = [
    "deepseek-ai/deepseek-v4-pro-0813",
    "moonshotai/kimi-k3",
    "nvidia/nemotron-3-super-120b-a12b",
    "meta/muse-glimmer-30b",
    "minimaxai/minimax-m3",
    "stepfun-ai/step-3.7-flash",
    "openai/gpt-oss-20b",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "nvidia/nemotron-3-nano-30b-a3b",
    "openai/gpt-oss-120b",
    "deepseek-ai/deepseek-v4-flash-0731",
    "moonshotai/kimi-k2.6",
    "mistralai/mistral-large-2-instruct",
    "microsoft/phi-3.5-moe-instruct",
    "ibm/granite-3.0-8b-instruct",
    "01-ai/yi-large",
    "ai21labs/jamba-1.5-large-instruct",
    "databricks/dbrx-instruct",
    "zyphra/zamba2-7b-instruct",
]

# The whole point: topic, length and position, nothing about tone, register or
# style. Do NOT add "write like a student" or any style hint here. Any styling
# makes the adversary weaker and the threshold more lenient.
PROMPT_TEMPLATE = (
    "Write a single paragraph of about {words} words from an IB Extended Essay "
    "on the following topic:\n\n{topic}\n\n"
    "Return only the paragraph itself, with no title, heading or commentary."
)

# Used when the human entry records WHERE in the essay its paragraph came from.
#
# This is structural, not stylistic, and the distinction is the whole reason it
# is allowed here. It says which part of an essay to write, exactly like the
# word count says how long. It does not say how to write.
#
# It exists because the human samples are drawn one per third of the body, so
# they carry the register spread a real essay has: a framing paragraph, an
# analytical one, a closing one. Prompting every AI sample identically would
# leave the AI class uniformly mid-essay, and that difference is learnable
# without being anything to do with human versus machine. If anything this
# makes the adversary stronger, because a real conclusion is formulaic too.
POSITIONED_TEMPLATE = (
    "Write a single paragraph of about {words} words from the {position} section "
    "of an IB Extended Essay on the following topic:\n\n{topic}\n\n"
    "Return only the paragraph itself, with no title, heading or commentary."
)

TEMPERATURE = 1.0   # the model's own default register; low temp writes flatter prose

# Only reached when EVERY model is rate limited at once; a 429 from one model
# switches to another instead of waiting. See the 429 branch in generate_one.
RATE_LIMIT_BACKOFF = 20   # seconds, multiplied by how many times we have waited

# A model that answers with a reasoning trace instead of the paragraph has had
# ONE bad roll, not a permanent fault: the nemotron models do it perhaps one
# time in five and write perfectly good prose the rest of the time. Dropping
# them on the first miss quietly collapsed the AI class onto the two or three
# models that never slip, which is precisely the loss of vendor spread this
# whole file exists to prevent. Temperature is 1.0, so a retry really is a
# different roll.
#
# This budget is PER SAMPLE, not per model. Counting misses over a model's
# whole run has the same bug in slow motion: a model that slips one time in
# five is certain to accumulate three misses somewhere in ninety samples and
# get dropped anyway. Rolling badly on one topic says nothing about the next.
BAD_RESPONSE_RETRIES = 3

# How many times to work through the whole model pool for one sample before
# giving up on it. Without this a sample is abandoned the moment every model has
# been tried once, and `tried` does not distinguish "this model will not write
# this topic" from "this model was busy for a second" — a few 429s in a row are
# enough to burn through the pool and lose the sample for good. Losing one
# leaves the AI class short against its human counterpart, which is exactly the
# imbalance the matched design exists to avoid.
POOL_SWEEPS = 3

# The shortest answer worth keeping. build_corpus.py takes human paragraphs of
# 60-160 words, and `trim_to_words` already stops the AI class running long; this
# is the other end of the same rule. Without it a truncated answer is saved as a
# sample: one real run produced an "AI paragraph" consisting of the single word
# "Here", and five more of 7 to 32 words. Perplexity over a handful of tokens is
# noise, and a class whose members are far shorter than their human counterparts
# teaches the threshold that length is the signal.
MIN_SAMPLE_WORDS = 60


def build_prompt(topic, words, position=None):
    """The prompt for one sample.

    Falls back to the position-free template when the human entry does not say
    where its paragraph came from, so a set built before positions were
    recorded, or someone else's topics file, generates exactly as it used to.
    """
    if position:
        return POSITIONED_TEMPLATE.format(topic=topic, words=words, position=position)
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
    choices = body.get("choices") or []
    if not choices:
        return ""
    # Reasoning models can answer with content=null and put their thinking in
    # reasoning_content. That is not prose for the corpus, so it counts as empty
    # and the caller drops the model.
    content = choices[0].get("message", {}).get("content")
    return content.strip() if content else ""


def substitute(pool, unavailable, vendor_counts):
    """Another model to try after one turned out to be uncallable.

    Draws from the WHOLE pool, not just the models already assigned, and picks
    the least-used vendor first. Half of NIM's catalog 404s per account, so
    without this the corpus collapses onto the two or three models that happen
    to answer. Returns None when nothing is left.
    """
    candidates = [model for model in pool if model not in unavailable]
    if not candidates:
        return None
    return min(candidates, key=lambda model: (vendor_counts[vendor_of(model)], model))


# Openings that mean the model is talking about the task instead of doing it:
# a planning trace, a preamble, or a refusal. One of these in the corpus would
# be scored as "AI prose" when it is really chat scaffolding, which teaches the
# threshold the wrong thing.
META_MARKERS = (
    "we need to", "let's", "let me", "i need to", "i should", "i'll write",
    "the user", "as an ai", "here is", "here's", "sure,", "certainly,",
    "okay,", "first, i", "no title", "word count", "i cannot", "i can't",
)


def looks_like_prose(text):
    """False when the model answered with commentary rather than the paragraph.

    Three ways it can fail, and the first two were found the hard way:

    - a phrase from META_MARKERS, e.g. "we need to write a single paragraph";
    - **markdown**, which a plain paragraph never contains but a planning trace
      is full of;
    - list formatting, caught by the same rule the detector uses. A real sample
      that got as far as being written to the corpus opened
      "1. **Analyze the Request:** - **Task:** Write a single paragraph...",
      which is the model thinking out loud in a numbered list and matches no
      marker phrase at all.

    A trace saved as an AI sample teaches the threshold that machine writing
    looks like meeting notes, which is worse than useless.
    """
    from .text import is_list_item      # torch-free, so this costs nothing

    flat = " ".join(text.split())
    if "**" in flat or flat.startswith("#"):
        return False
    if is_list_item(flat):
        return False
    opening = flat[:300].lower()
    return not any(marker in opening for marker in META_MARKERS)


# A model sometimes annotates its own answer: "... sustain exclusion. (110 words)".
# That is commentary, not essay prose.
WORD_COUNT_NOTE = re.compile(r"\s*\(\s*(?:about\s*|approx\.?\s*|~\s*)?\d+\s*words?\s*\)\s*$",
                             re.IGNORECASE)

# A finished sentence ends in a stop, allowing for a closing quote or bracket.
ENDS_A_SENTENCE = re.compile(r"[.!?][\"\u201d\')\]]?$")


def trim_to_words(text, budget):
    """Keep whole sentences up to roughly `budget` words.

    Models routinely overshoot the requested length, and the human samples are
    fixed-size excerpts from long essays. Without this the AI class runs ~50%
    longer than the human class and the fitted threshold partly encodes "long
    means machine", which would not generalise to a student's own paragraphs.

    Whole sentences only, and never a rewrite: this excerpts, it does not edit.
    """
    text = WORD_COUNT_NOTE.sub("", text.strip())
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()]
    kept, count = [], 0
    for sentence in sentences:
        kept.append(sentence)
        count += len(sentence.split())
        if count >= budget:
            break

    # Drop a trailing fragment with no full stop. A model that hits its token
    # limit stops mid-clause, and that fragment would otherwise be saved as a
    # sample. It matters because EVERY human sample ends in a full stop by
    # construction, so an AI class where some do not hands the detector a
    # difference that is about truncation, not authorship. Emptying the list
    # here is fine: the MIN_SAMPLE_WORDS floor then rejects the answer and the
    # caller asks again.
    while kept and not ENDS_A_SENTENCE.search(kept[-1]):
        kept.pop()
    return " ".join(kept)


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


class ModelPool:
    """Which models are still worth calling, shared by every worker thread.

    Half of NIM's catalog 404s per account and a couple of models simply never
    answer, so a model that fails is dropped once and every worker sees that
    immediately rather than each rediscovering it. All the shared counters live
    behind one lock: they are only touched between HTTP calls, so contention is
    irrelevant and one lock is easier to reason about than three.
    """

    def __init__(self, pool):
        self.pool = pool
        self.lock = threading.Lock()
        self.unavailable = set()
        self.vendor_counts = collections.Counter()

    def replacement_for(self, model):
        """Drop `model` and return another one to try, or None if none are left."""
        with self.lock:
            self.unavailable.add(model)
            return substitute(self.pool, self.unavailable, self.vendor_counts)

    def still_usable(self, model):
        with self.lock:
            if model not in self.unavailable:
                return model
            return substitute(self.pool, self.unavailable, self.vendor_counts)

    def another_than(self, model, already_tried):
        """A different model for THIS sample, without blacklisting `model`.

        Used when a model keeps returning commentary for one particular topic.
        The model stays in rotation for every other sample, because the problem
        was the roll, not the model.
        """
        with self.lock:
            skip = set(already_tried) | self.unavailable | {model}
            candidates = []
            for candidate in self.pool:
                if candidate not in skip:
                    candidates.append(candidate)
            if not candidates:
                return None
            return min(candidates,
                       key=lambda name: (self.vendor_counts[vendor_of(name)], name))

    def note_use(self, model):
        with self.lock:
            self.vendor_counts[vendor_of(model)] += 1


def sample_id_for(human_id, prefix):
    """th07a -> ta07a: keep the essay number AND the paragraph letter.

    The letter is what lets calibrate group an essay's three AI samples with
    its three human ones. Older single-paragraph ids (h01) end in a digit and
    simply have no letter.
    """
    number = ""
    for character in human_id:
        if character.isdigit():
            number += character
    letter = ""
    if human_id[-1].isalpha() and number:
        letter = human_id[-1]
    return f"{prefix}{number}{letter}"


def generate_one(entry, model, models_state, api_key, args, models=()):
    """Write one sample and return its manifest row, or None if nothing worked.

    Returns rather than exiting, because this runs in a worker thread where a
    SystemExit would be swallowed and leave the corpus quietly short.
    """
    out_id = sample_id_for(entry["id"], args.prefix)
    position = entry.get("position")
    prompt = build_prompt(entry["topic"], args.words, position)

    model = models_state.still_usable(model)
    sweeps = 0            # how many times the whole pool has been worked through
    # Models that would not serve this particular sample, whether because they
    # kept answering with commentary or because they were busy. Note this means
    # a sample can end up on a different model than --seed assigned; the
    # manifest records the model actually used, so the set stays auditable.
    tried = []
    bad_responses = 0     # unusable answers for this sample, reset per model
    rate_limit_waits = 0  # 429s seen while working on this sample
    timeouts = 0          # consecutive timeouts from the current model
    text = ""
    while not text:
        if model is None:
            # Pool exhausted. Most of the time that is a run of bad luck rather
            # than six broken models, so let everything back in and sweep again.
            sweeps += 1
            if sweeps < POOL_SWEEPS:
                print(f"      {out_id}: every model tried, sweeping again "
                      f"({sweeps}/{POOL_SWEEPS - 1}) after {RATE_LIMIT_BACKOFF}s")
                time.sleep(RATE_LIMIT_BACKOFF)
                tried = []
                model = models_state.still_usable(models[0] if models else None)
                if model is None:
                    print(f"      {out_id}: no model left at all, no sample written")
                    return None
                continue
            print(f"      {out_id}: every model failed {POOL_SWEEPS} sweeps, "
                  f"no sample written")
            return None
        print(f"{out_id}  {model}  {entry['topic'][:50]}...")
        try:
            text = clean(call_nim(prompt, model, api_key, args.timeout))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:200]
            if error.code in (401, 403) and "account" not in detail:
                raise SystemExit(f"NIM rejected the API key ({error.code}): {detail}")
            if error.code == 429:
                # build.nvidia.com is not credit-based. It rate limits by how
                # busy THAT model is right now ("dependent on model, use-case
                # and the amount of current overall traffic using the same
                # access"), so a 429 says the model is popular this minute, not
                # that the account is out of anything. Measured: two models can
                # 429 while four others answer 200 in the same second.
                #
                # So the cheap fix is another model, not a sleep. Only when
                # every model is busy is there anything to wait for.
                alternative = models_state.another_than(model, tried)
                if alternative is not None:
                    print(f"      429 for {model} (busy), switching model")
                    tried.append(model)
                    model = alternative
                    continue
                rate_limit_waits += 1
                wait = RATE_LIMIT_BACKOFF * rate_limit_waits
                print(f"      429 from every model, waiting {wait}s")
                time.sleep(wait)
                tried = []          # let them all back in after the wait
                continue
            print(f"      {error.code} for {model}, dropping it: {detail[:90]}")
            model = models_state.replacement_for(model)
        except TimeoutError:
            # A cold or heavily loaded model can sit past the timeout. One more
            # go for this sample, then drop it: unlike a 429, a model that will
            # not answer twice running really is unusable.
            timeouts += 1
            if timeouts <= 1:
                print(f"      {model} timed out, retrying once")
                continue
            print(f"      {model} timed out twice, dropping it")
            model = models_state.replacement_for(model)
            timeouts = 0
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError):
                print(f"      {model} timed out, dropping it")
                model = models_state.replacement_for(model)
            else:
                raise SystemExit(f"could not reach NIM: {error.reason}")
        else:
            if text and not looks_like_prose(text):
                text = ""          # a reasoning trace or a preamble leaked in
            if text and len(text.split()) < MIN_SAMPLE_WORDS:
                print(f"      {model} returned {len(text.split())} words, "
                      f"under the {MIN_SAMPLE_WORDS}-word floor")
                text = ""
            if not text:
                # Answered, but with nothing usable: a refusal, a planning
                # trace, or a reasoning model that put everything in
                # reasoning_content. Retry the same model first — this is a bad
                # roll, not a broken model.
                bad_responses += 1
                if bad_responses <= BAD_RESPONSE_RETRIES:
                    print(f"      {model} returned no prose, retrying "
                          f"({bad_responses}/{BAD_RESPONSE_RETRIES})")
                    continue
                print(f"      {model} keeps returning commentary for this topic, "
                      f"trying another model")
                tried.append(model)
                model = models_state.another_than(model, tried)
                bad_responses = 0

    models_state.note_use(model)
    text = trim_to_words(text, args.words)
    path = os.path.join(args.out_dir, f"{out_id}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return {
        "id": out_id,
        "matches": entry["id"],
        "subject": entry.get("subject"),
        "topic": entry["topic"],
        "position": position,
        "generated_by": model,
        "vendor": vendor_of(model),
        "temperature": TEMPERATURE,
        "prompt_template": POSITIONED_TEMPLATE if position else PROMPT_TEMPLATE,
        "words_requested": args.words,
        "words_kept": len(text.split()),
        "seed": args.seed,
    }


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
    ap.add_argument("--append", action="store_true",
                    help="merge into the manifest already in --out-dir instead of "
                         "replacing it. Use when the human corpus has grown and only "
                         "the new samples need an AI counterpart; regenerating the "
                         "whole set costs hundreds of calls to no purpose.")
    ap.add_argument("--workers", type=int, default=1,
                    help="how many completions to request at once (default %(default)s, "
                         "i.e. sequential). Raise it when the model pool mixes fast and "
                         "slow models; too high and NIM starts answering 429.")
    ap.add_argument("--timeout", type=int, default=180,
                    help="seconds to wait for one completion (default %(default)s). "
                         "Measured: a large hosted model can legitimately take ~120s, "
                         "so a tighter limit drops working models as if they were dead.")
    args = ap.parse_args(argv)

    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        ap.error("NVIDIA_API_KEY is not set. Get a key at https://build.nvidia.com and "
                 "export it yourself; aidetect never stores it.")

    with open(args.topics, encoding="utf-8") as f:
        topics = json.load(f)

    if args.model:
        pool = list(dict.fromkeys(args.model))
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

    models_state = ModelPool(pool)

    # Threads, not processes: every worker spends its time waiting on an HTTP
    # response. It matters here because the usable models differ in speed by
    # more than 10x (one large model legitimately takes ~120s while others
    # answer in ~10s), so in a sequential run the slow ones block everything.
    written = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as workers:
        jobs = {}
        for index, entry in enumerate(topics):
            job = workers.submit(generate_one, entry, models[index],
                                 models_state, api_key, args, models)
            jobs[job] = index

        rows_by_index = {}
        for job in concurrent.futures.as_completed(jobs):
            row = job.result()
            if row is not None:
                rows_by_index[jobs[job]] = row

    # keep manifest order matching the topics file, not completion order
    for index in sorted(rows_by_index):
        written.append(rows_by_index[index])

    manifest_path = os.path.join(args.out_dir, "manifest.json")
    if args.append and os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            existing = json.load(f)
        fresh_ids = set()
        for row in written:
            fresh_ids.add(row["id"])
        merged = []
        for row in existing:
            if row["id"] not in fresh_ids:      # a regenerated id replaces the old one
                merged.append(row)
        merged.extend(written)
        merged.sort(key=lambda row: row["id"])
        written = merged
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(written, f, indent=2)
    used = sorted({row["generated_by"] for row in written})
    print(f"\nwrote {len(written)} samples + manifest -> {args.out_dir}")
    print(f"models used ({len(used)}): {', '.join(used)}")
    print("check a couple by eye before calibrating: a refusal or a chatty preamble "
          "would poison the class.")
    return 0
