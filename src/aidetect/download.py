"""
`aidetect download`: the only command that talks to the network.

Fetches the desklib detector and, on request, a Binoculars pair into the
Hugging Face cache. Every other command runs with HF_HUB_OFFLINE=1 and fails
fast if something is missing, so this is the one place a download can happen.

Where things go:
  * Hugging Face models: $HF_HOME (default ~/.cache/huggingface). Set it before
    both `download` and later runs if the default folder does not suit you.
  * the locally quantized 4-bit MLX observer: $AIDETECT_MLX_CACHE
    (default ~/.cache/ai-detect-mlx).

Usage:
    aidetect download                     # desklib only, ~1.5GB
    aidetect download --pair gemma --mlx  # plus the Gemma 4 MLX pair (Apple Silicon)
    aidetect download --pair small        # plus the Qwen 0.5B torch pair
"""

import argparse
import os

from huggingface_hub import snapshot_download


def fetch(repo):
    print(f"fetching {repo}...")
    path = snapshot_download(repo)
    print(f"  -> {path}")


def main(argv):
    # imported here, not at the top: these modules pull torch in, and the
    # PAIRS tables are only needed once a pair was asked for.
    from .binoculars import MLX_CACHE, MLX_PAIRS, PAIRS, _mlx_quantized
    from .detect import MODEL_ID

    ap = argparse.ArgumentParser(prog="aidetect download", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pair", choices=list(PAIRS), default=None,
                    help="also fetch this Binoculars pair (default: desklib only)")
    ap.add_argument("--mlx", action="store_true",
                    help="fetch the 4-bit MLX version of --pair and quantize the observer (Apple Silicon)")
    args = ap.parse_args(argv)

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

    print(f"done. models live in {os.environ.get('HF_HOME', '~/.cache/huggingface')}; "
          "every other aidetect command now runs offline.")
    return 0
