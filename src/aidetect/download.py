"""
`aidetect download`: the only command that talks to the network.

Fetches the desklib detector and, on request, a Binoculars pair into the
Hugging Face cache. Every other command runs with HF_HUB_OFFLINE=1 and fails
fast if something is missing, so this is the one place a download can happen.

Where things go:
  * Hugging Face models: the folder given here, remembered in
    ~/.config/aidetect/models-dir and used as HF_HOME by every later run.
    No folder given: $HF_HOME, else the saved one, else ~/.cache/huggingface.
  * the locally quantized 4-bit MLX observer: $AIDETECT_MLX_CACHE
    (default ~/.cache/ai-detect-mlx).

Usage:
    aidetect download                     # desklib only, ~1.5GB
    aidetect download /Volumes/big/models # same, into that folder, remembered
    aidetect download --pair gemma --mlx  # plus the Gemma 4 MLX pair (Apple Silicon)
    aidetect download --pair small        # plus the Qwen 0.5B torch pair
"""

import argparse
import os

from .paths import MODELS_DIR_FILE, save_models_dir


def fetch(repo):
    from huggingface_hub import snapshot_download
    print(f"fetching {repo}...")
    path = snapshot_download(repo)
    print(f"  -> {path}")


def main(argv):
    ap = argparse.ArgumentParser(prog="aidetect download", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", nargs="?", default=None,
                    help="folder to keep the models in; saved so every later run uses it")
    ap.add_argument("--pair", default=None,
                    help="also fetch this Binoculars pair: small, big, gemma, gemma+ (default: desklib only)")
    ap.add_argument("--mlx", action="store_true",
                    help="fetch the 4-bit MLX version of --pair and quantize the observer (Apple Silicon)")
    args = ap.parse_args(argv)

    if args.dir:
        path = os.path.abspath(os.path.expanduser(args.dir))
        os.makedirs(path, exist_ok=True)
        # must precede the first huggingface_hub import: it reads HF_HOME at import time
        os.environ["HF_HOME"] = path
        save_models_dir(path)
        print(f"models folder: {path} (saved in {MODELS_DIR_FILE})")

    # imported only now: these pull torch and huggingface_hub in
    from .binoculars import MLX_CACHE, MLX_PAIRS, PAIRS, _mlx_quantized
    from .detect import MODEL_ID
    if args.pair and args.pair not in PAIRS:
        raise SystemExit(f"--pair must be one of {list(PAIRS)}")

    fetch(MODEL_ID)

    if args.pair and args.mlx:
        if args.pair not in MLX_PAIRS:
            raise SystemExit(f"--mlx only supports {list(MLX_PAIRS)}; pass e.g. --pair gemma")
        obs_src, perf_repo = MLX_PAIRS[args.pair]
        print(f"observer {obs_src}: 4-bit copy in {MLX_CACHE}")
        _mlx_quantized(obs_src)
        fetch(perf_repo)
    elif args.pair:
        for repo in PAIRS[args.pair]:
            fetch(repo)

    print(f"done. models live in {os.environ.get('HF_HOME') or '~/.cache/huggingface'}; "
          "every other aidetect command now runs offline.")
    return 0
