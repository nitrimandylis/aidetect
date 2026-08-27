"""
`aidetect` entry point.

Subcommand modules are imported lazily and on demand: `aidetect count` must not
pay a ~2s torch import to count words, and on a machine without mlx-vlm the
torch-free subcommands still have to work.
"""

import sys

COMMANDS = {
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

    module_name = COMMANDS[command][0]
    from importlib import import_module
    module = import_module(module_name)
    return module.main(sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
