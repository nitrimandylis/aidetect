"""
`aidetect` entry point.

Subcommand modules are imported lazily and on demand: `aidetect count` must not
pay a ~2s torch import to count words, and on a machine without mlx-vlm the
torch-free subcommands still have to work.
"""

import os
import sys

# Every command except `download` runs with the Hugging Face Hub switched off.
# Without this, transformers and mlx-vlm phone home on every from_pretrained to
# check for a newer revision, even when the model is fully cached. Set before
# any import: huggingface_hub reads these once at import time.
OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
}

COMMANDS = {
    "download":  ("aidetect.download",   "fetch the models once; every other command is offline"),
    "count":     ("aidetect.count",      "IB-rules word count for a draft"),
    "score":     ("aidetect.detect",     "score paragraphs with the desklib detector"),
    "check":     ("aidetect.check",      "run both detectors, worst opinion wins"),
    "bino":      ("aidetect.binoculars", "second opinion via Binoculars (needs a model pair)"),
    "extract":   ("aidetect.extract",    "pull finished prose out of a .docx into a .txt"),
    "calibrate": ("aidetect.calibrate",  "fit a Binoculars threshold on your own labelled set"),
    "generate":  ("aidetect.generate",   "generate the AI half of a calibration set (NVIDIA NIM)"),
}

USAGE = "usage: aidetect <command> [options]\n\ncommands:\n" + "".join(
    f"  {name:<10} {help}\n" for name, (_mod, help) in COMMANDS.items()
) + "\nrun `aidetect <command> --help` for a command's options.\n"


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(USAGE, end="")
        return 0
    if sys.argv[1] in ("-V", "--version"):
        from importlib.metadata import version
        print(version("aidetect"))
        return 0

    command = sys.argv[1]
    if command not in COMMANDS:
        print(f"aidetect: unknown command {command!r}\n", file=sys.stderr)
        print(USAGE, end="", file=sys.stderr)
        return 2

    if command != "download":
        os.environ.update(OFFLINE_ENV)

    module_name = COMMANDS[command][0]
    from importlib import import_module
    module = import_module(module_name)
    try:
        return module.main(sys.argv[2:])
    except OSError as e:
        # transformers wraps huggingface_hub's cache miss in an OSError whose
        # message names offline mode; anything else is a real I/O error.
        if "offline" not in str(e).lower():
            raise
        print("aidetect: a model is not in the local cache and aidetect never "
              "downloads during a run.\nrun `aidetect download` once "
              "(`aidetect download --help` for the Binoculars pairs).",
              file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
