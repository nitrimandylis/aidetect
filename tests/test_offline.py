"""
Every command but `download` must refuse to touch the network.

Run against an empty HF cache: `score` has to fail fast with the download hint
instead of fetching the model. Checked in a subprocess because the offline
switch is an env var read at import time, so it cannot be toggled in-process.
"""

import os
import subprocess
import sys


def run(args, tmp_path):
    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    env = dict(os.environ, PYTHONPATH=src, HF_HOME=str(tmp_path))
    env.pop("HF_HUB_OFFLINE", None)   # the CLI must set it itself
    p = subprocess.run([sys.executable, "-c", "import sys; from aidetect.cli import main; sys.exit(main() or 0)",
                        *args], env=env, capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout, p.stderr


def test_score_with_empty_cache_does_not_download(tmp_path):
    rc, out, err = run(["score", "--text", "twenty five words of prose " * 6], tmp_path)
    assert rc == 3, (out, err)
    assert "aidetect download" in err
    assert not any(os.scandir(tmp_path)) or not os.path.isdir(tmp_path / "hub") \
        or not any(os.scandir(tmp_path / "hub")), "something was written to the model cache"
