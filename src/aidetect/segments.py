"""
Turnitin-shaped segment scoring: sentence windows instead of paragraphs.

What is publicly known about Turnitin's AI indicator: it wants roughly 300
words minimum, splits the prose into overlapping runs of about 5-10 sentences,
scores each run, and its headline number is what share of the document sits in
flagged runs. The paragraph scorer in detect.py cannot mimic that shape: it
skips anything under 25 words, and short formulaic connective prose
(transitions, the sentences around figures) is exactly what detectors flag
most. Sliding windows absorb those short paragraphs instead of skipping them.

Only window arithmetic lives in this module, no torch: detect.py and check.py
bring the model and pass scores in, so the tests can run this file without
downloading anything.

The sentence split is regex-grade on purpose. Windows overlap, so a boundary
missed at an abbreviation only shifts a window edge, and the worst-window rule
washes the difference out.
"""

import re

WINDOW = 7   # sentences per segment: the middle of Turnitin's reported 5-10
STRIDE = 3   # a new window starts every 3 sentences, so windows overlap

# A sentence ends at . ! or ?, possibly followed by ONE closing quote or
# bracket ("”" and "’" are the curly closers Word inserts), then whitespace.
# Two alternated lookbehinds because Python only allows fixed-width ones; the
# closer stays part of the sentence, only the whitespace is consumed.
SENTENCE_END = re.compile(r'(?<=[.!?]["”’)\]])\s+|(?<=[.!?])\s+')

# red is the desklib model's own decision boundary; amber is the stand-in used
# until `aidetect calibrate` has fitted a data-derived edge from the corpus
RED_DEFAULT = 0.5
AMBER_FALLBACK = 0.35

SEVERITY = {"clean": 0, "amber": 1, "red": 2}


def split_sentences(text):
    parts = SENTENCE_END.split(text.strip())
    return [part.strip() for part in parts if part.strip()]


def document_sentences(paragraphs):
    """Flatten a draft into [(paragraph_number, sentence), ...].

    The paragraph number is kept so check.py can line each sentence up with
    the Binoculars verdict for the paragraph it came from."""
    out = []
    for number, paragraph in enumerate(paragraphs):
        for sentence in split_sentences(paragraph):
            out.append((number, sentence))
    return out


def build_windows(sentence_count):
    """(start, end) index pairs over the sentence list. Every sentence lands in
    at least one window; the last window may be short rather than dropping the
    tail of the document."""
    if sentence_count == 0:
        return []
    windows = []
    start = 0
    while True:
        end = min(start + WINDOW, sentence_count)
        windows.append((start, end))
        if end == sentence_count:
            return windows
        start += STRIDE


def sentence_scores(sentence_count, windows, window_scores):
    """Each sentence takes the WORST (highest) score of any window covering it,
    so a sentence that drags down only one of its windows still surfaces."""
    worst_per_sentence = [0.0] * sentence_count
    for (start, end), score in zip(windows, window_scores):
        for i in range(start, end):
            if score > worst_per_sentence[i]:
                worst_per_sentence[i] = score
    return worst_per_sentence


def classify(score, red=RED_DEFAULT, amber=AMBER_FALLBACK):
    if score >= red:
        return "red"
    if score >= amber:
        return "amber"
    return "clean"


def worse(status_a, status_b):
    if SEVERITY[status_a] >= SEVERITY[status_b]:
        return status_a
    return status_b


def word_shares(sentences, statuses):
    """(red_share, amber_share) of the prose, weighted by words: the same kind
    of number as Turnitin's headline percentage."""
    total_words = red_words = amber_words = 0
    for (_number, sentence), status in zip(sentences, statuses):
        words = len(sentence.split())
        total_words += words
        if status == "red":
            red_words += words
        elif status == "amber":
            amber_words += words
    if total_words == 0:
        return 0.0, 0.0
    return red_words / total_words, amber_words / total_words


def flagged_runs(statuses):
    """Consecutive non-clean sentences, as (start, end, worst_status) spans.
    A run is the unit you reword: one sentence rarely trips a detector alone."""
    runs = []
    start = None
    worst_status = "clean"
    for i, status in enumerate(statuses):
        if status == "clean":
            if start is not None:
                runs.append((start, i, worst_status))
                start = None
                worst_status = "clean"
            continue
        if start is None:
            start = i
        worst_status = worse(worst_status, status)
    if start is not None:
        runs.append((start, len(statuses), worst_status))
    return runs


def print_report(sentences, scores, statuses):
    """The Turnitin-shaped report: flagged runs first, then the headline share."""
    runs = flagged_runs(statuses)
    if not runs:
        print("no flagged segments")
    for start, end, worst_status in runs:
        worst_score = max(scores[start:end])
        label = "AI-ish" if worst_status == "red" else "borderline"
        print(f"\n-- {label} run, sentences {start + 1}-{end}, worst {worst_score:.2f} --")
        for i in range(start, end):
            _number, sentence = sentences[i]
            print(f"  [{statuses[i]:>5}] {sentence[:90]}")
    red_share, amber_share = word_shares(sentences, statuses)
    print("-" * 60)
    print(f"{red_share:.0%} of prose in AI-flagged segments, plus {amber_share:.0%} borderline")
