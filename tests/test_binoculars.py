"""Math checks for the Binoculars core — no model download needed."""

import math
import os
import sys

import torch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from aidetect.binoculars import cross_perplexity, perplexity  # noqa: E402
from aidetect.calibrate import pick_threshold  # noqa: E402


def test_perplexity_confident_correct_is_low():
    # logits that put almost all mass on the true next token -> ~0 cross-entropy
    input_ids = torch.tensor([[0, 1, 2]])
    logits = torch.zeros(1, 3, 4)
    logits[0, 0, 1] = 20.0   # at pos 0, predict token 1 (correct)
    logits[0, 1, 2] = 20.0   # at pos 1, predict token 2 (correct)
    assert perplexity(input_ids, logits) < 0.01


def test_perplexity_confident_wrong_is_high():
    input_ids = torch.tensor([[0, 1, 2]])
    logits = torch.zeros(1, 3, 4)
    logits[0, 0, 3] = 20.0   # confidently predicts the wrong token
    logits[0, 1, 3] = 20.0
    assert perplexity(input_ids, logits) > 5.0


def test_cross_perplexity_identical_models_equals_entropy():
    # if observer == performer, cross-perplexity is just the model's own entropy.
    # uniform over 4 tokens -> entropy = ln(4)
    logits = torch.zeros(1, 3, 4)
    x = cross_perplexity(logits, logits)
    assert abs(x - math.log(4)) < 1e-5


def test_cross_perplexity_disagreement_raises_it():
    same = cross_perplexity(torch.zeros(1, 2, 4), torch.zeros(1, 2, 4))
    obs = torch.zeros(1, 2, 4); obs[0, :, 0] = 10.0     # observer sure it's token 0
    perf = torch.zeros(1, 2, 4); perf[0, :, 1] = 10.0   # performer sure it's token 1
    assert cross_perplexity(obs, perf) > same


def test_pick_threshold_separates_clean_clusters():
    human = [1.00, 1.10, 1.05]   # higher
    ai = [0.80, 0.85, 0.90]      # lower
    cutoff, acc = pick_threshold(human, ai)
    assert acc == 1.0
    assert 0.90 < cutoff < 1.00   # lands in the gap


def test_pick_threshold_reports_partial_accuracy_when_overlapping():
    human = [1.0, 0.85]          # one human dips into AI range
    ai = [0.8, 0.9]
    cutoff, acc = pick_threshold(human, ai)
    assert acc < 1.0             # can't perfectly separate


def test_mlx_convert_survives_readonly_source_and_redoes_partial():
    # Fake mlx_vlm whose convert() behaves like the real one: copies *.json
    # keeping the mode, then overwrites its own tokenizer.json, then writes
    # the quantization config last.
    import json, shutil, stat, tempfile, types
    from aidetect import binoculars

    tmp = tempfile.mkdtemp()
    src = os.path.join(tmp, "hf")
    os.makedirs(src)
    for name in ("tokenizer.json", "config.json", "model.safetensors"):
        with open(os.path.join(src, name), "w") as f:
            f.write("{}")
        os.chmod(os.path.join(src, name), stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    def convert(hf_path, mlx_path, quantize):
        os.makedirs(mlx_path)
        for name in os.listdir(hf_path):
            shutil.copy(os.path.join(hf_path, name), mlx_path)
        with open(os.path.join(mlx_path, "tokenizer.json"), "w") as f:
            f.write("{}")   # raises PermissionError if the copy is read-only
        os.chmod(os.path.join(mlx_path, "config.json"), stat.S_IRWXU)
        with open(os.path.join(mlx_path, "config.json"), "w") as f:
            json.dump({"quantization": {"bits": 4}}, f)

    fake = types.ModuleType("mlx_vlm")
    fake.convert = convert
    fake.utils = types.ModuleType("mlx_vlm.utils")
    fake.utils.get_model_path = lambda repo: src
    sys.modules["mlx_vlm"] = fake
    sys.modules["mlx_vlm.utils"] = fake.utils
    binoculars.MLX_CACHE = os.path.join(tmp, "cache")

    # a crashed earlier run: weights, but no quantization key
    stale = os.path.join(binoculars.MLX_CACHE, "org_model-4bit")
    os.makedirs(stale)
    with open(os.path.join(stale, "config.json"), "w") as f:
        json.dump({}, f)

    out = binoculars._mlx_quantized("org/model")
    assert out == stale
    assert binoculars._is_quantized(out)
    assert not os.path.exists(out + ".partial")
    assert sorted(os.listdir(binoculars.MLX_CACHE)) == ["org_model-4bit"]   # shadow dir gone


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("all passed")
