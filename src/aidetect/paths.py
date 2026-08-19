"""
Where thresholds live.

Two locations, checked in this order:
  1. ~/.config/aidetect/threshold-<tag>.json — what `aidetect calibrate` writes.
  2. the thresholds/ folder inside the installed package — the ones shipped.

The package folder is read-only in spirit (it is site-packages on an install and
gets replaced on upgrade), so calibration output never goes there.
"""

import os
from importlib import resources

USER_DIR = os.path.expanduser("~/.config/aidetect")


def user_threshold_path(tag):
    return os.path.join(USER_DIR, f"threshold-{tag}.json")


def threshold_path(tag):
    """Path to the shipped threshold for this pair, or None if there isn't one."""
    ref = resources.files("aidetect") / "thresholds" / f"threshold-{tag}.json"
    # as_file would be needed for a zipped install; these are always unpacked
    # because the wheel has no zip-safe flag, so a plain path is fine.
    return str(ref) if ref.is_file() else None


def ensure_user_dir():
    os.makedirs(USER_DIR, exist_ok=True)
    return USER_DIR
