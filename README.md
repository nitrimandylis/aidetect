```
 █████╗ ██╗      ██████╗ ███████╗████████╗███████╗ ██████╗████████╗
██╔══██╗██║      ██╔══██╗██╔════╝╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝
███████║██║█████╗██║  ██║█████╗     ██║   █████╗  ██║        ██║
██╔══██║██║╚════╝██║  ██║██╔══╝     ██║   ██╔══╝  ██║        ██║
██║  ██║██║      ██████╔╝███████╗   ██║   ███████╗╚██████╗   ██║
╚═╝  ╚═╝╚═╝      ╚═════╝ ╚══════╝   ╚═╝   ╚══════╝ ╚═════╝   ╚═╝
```
<div align="center">

### `SCORE YOUR OWN PROSE // BEFORE A TEACHER SCORES IT FOR YOU`

*a local, offline AI-writing detector for drafts you actually wrote*

![language](https://img.shields.io/badge/language-python-3776AB?style=flat-square&labelColor=111111)
![runs](https://img.shields.io/badge/runs-offline-2ea043?style=flat-square&labelColor=111111)
![model](https://img.shields.io/badge/model-desklib_DeBERTa-8957e5?style=flat-square&labelColor=111111)
![license](https://img.shields.io/badge/license-MIT-2ea043?style=flat-square&labelColor=111111)
![telemetry](https://img.shields.io/badge/telemetry-0_(it's_your_essay)-111111?style=flat-square&labelColor=111111)

</div>

---

## 🔍 What is this

A command-line tool that reads a `.docx` or `.txt` and scores each paragraph
0–1 on how AI-generated it reads, using the `desklib/ai-text-detector-v1.01`
DeBERTa model — the one sitting at #1 on the RAID benchmark. Everything runs
on your own machine; after the first model download it never touches the
network. You point it at your Extended Essay, it tells you which paragraphs
sound like a language model wrote them.

The point isn't to cheat a detector. It's the opposite: I write my own drafts,
and sometimes my own honest prose still trips these classifiers because that's
what earnest formal writing looks like to them. This flags those paragraphs so
I can reword before a teacher runs Turnitin and has an awkward conversation
with me about it.

It is directional, not oracular. A high score means "reword this," not "you're
caught." It is not, and cannot be, the number Turnitin shows a teacher.

```console
nick@ai-detect:~$ python detect.py EE-clean.txt
P  1   0.08  [##------------------]
P  2   0.71  [##############------]  <-- AI-ish
average AI score: 0.34   |   1/6 paragraphs flagged
reminder: directional only, not a Turnitin score.
```

## 🧠 The detection engine

| | feature | what it actually does |
|---|---|---|
| 01 | **per-paragraph scoring** | what it actually catches — splits your draft and scores each paragraph, so you fix the two bad ones instead of rewriting everything |
| 02 | **docx + txt input** | reads Word files straight (paragraphs, no headings) or plain text split on blank lines |
| 03 | **prose extractor** | `extract.py` strips headings, bullets, footnotes and your own note-scaffolding first, so the score is about writing, not structure |
| 04 | **offline after setup** | first run pulls ~1.5GB of model, every run after is airgapped — your essay never leaves the laptop |
| 05 | **second opinion** | cross-check against the lighter [Ejhfast/fast-ai-detector] when one model's paranoia isn't enough |

## 🚀 Run it

Needs Python and a machine that can hold a DeBERTa model (built and tested on
an 18GB Apple Silicon Mac, MPS-accelerated).

```bash
git clone https://github.com/nitrimandylis/ai-detect.git
cd ai-detect
pip install -r requirements.txt

python detect.py "path/to/draft.docx"     # score a whole draft
python detect.py --text "one sentence"    # score a single string
```

First run downloads the model and will sit there for a minute — that's normal,
not a hang. Every run after is fast and offline.

## 🔩 Under the hood

```mermaid
flowchart LR
    A[.docx / .txt] --> B[extract.py<br/>strip non-prose]
    B --> C[read_paragraphs<br/>>= 25 words]
    C --> D[desklib DeBERTa<br/>mean-pool + sigmoid]
    D --> E[per-paragraph<br/>0-1 score + flags]
```

| file | job |
|---|---|
| `detect.py` | loads the desklib model, scores each paragraph, prints the bars and flags |
| `extract.py` | pulls clean prose out of a `.docx` into a `.txt` — drops headings, bullets, note-labels |
| `requirements.txt` | torch · transformers · python-docx |

**Stack:** python · pytorch · transformers · desklib DeBERTa

The lighter cross-check tool lives at [Ejhfast/fast-ai-detector] — it's a
separate repo, not vendored here.

---

<div align="center">

**[Nick Trimandylis](https://github.com/nitrimandylis)**

`I WRITE MY OWN ESSAYS — THIS JUST CHECKS THEY STILL READ LIKE IT`

MIT licensed — see [LICENSE](LICENSE).

</div>

[Ejhfast/fast-ai-detector]: https://github.com/Ejhfast/fast-ai-detector
