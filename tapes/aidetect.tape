# The README hero. Record with:  vhs tapes/aidetect.tape   (from the repo root)
# Runs against tapes/fixture.py, not your real files: a fake HOME holding a short
# synthetic Extended Essay draft (draft.docx, invented, not real coursework).
# Build it first:  uv run --python 3.14 --managed-python --project . python tapes/fixture.py
# The desklib model is read from the real ~/.cache/huggingface (HF_HOME), since
# the redirected HOME would hide it. Needs the model downloaded once.
# Terminal settings match ghostty on the machine this was shot on:
# Cascadia Code NF at 19, padding 12, swatch theme creation.
Output .github/assets/aidetect.gif
Set Shell "zsh"
Set FontFamily "Cascadia Code NF"
Set FontSize 19
Set Width 1200
Set Height 630
Set Padding 12
Set TypingSpeed 55ms
Set Theme { "name": "creation", "background": "#000000", "foreground": "#d6d6d6", "cursor": "#ffffff", "selection": "#1c1c1c", "black": "#1c1c1c", "red": "#d07a7a", "green": "#8fae86", "yellow": "#cdb27a", "blue": "#7f9bb8", "magenta": "#b391a8", "cyan": "#82adad", "white": "#b3b3b3", "brightBlack": "#4d4d4d", "brightRed": "#e39a9a", "brightGreen": "#a8c69f", "brightYellow": "#e0c895", "brightBlue": "#9db6cf", "brightMagenta": "#c9abbf", "brightCyan": "#9fc5c5", "brightWhite": "#ffffff" }
Hide
Type "REPO=$PWD; REAL=$HOME; uv run --python 3.14 --managed-python --project $REPO python $REPO/tapes/fixture.py >/dev/null 2>&1; export HOME=$REPO/tapes/fixtures/home; export HF_HOME=$REAL/.cache/huggingface; aidetect() { uv run --python 3.14 --managed-python --project $REPO aidetect $@ 2>/dev/null }; export PS1='%F{5}❯%f '; cd $HOME; clear"
Enter
Sleep 8s
Show
Type "aidetect count draft.docx --limit 150"
Sleep 500ms
Enter
Sleep 5s
Type "aidetect score draft.docx"
Sleep 500ms
Enter
Wait+Screen@90s /reminder/
Sleep 4s
