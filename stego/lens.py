"""Hours 10-15: logit lens over saved residuals (Brauer et al. style, adapted to a digit-level tokenizer).

Qwen2.5 tokenizes numbers one digit per token, so a residual at one position can at best predict
ONE digit. We therefore ask: at (layer, position), after projecting through the final norm and the
unembedding and restricting to the ten digit tokens, is the FIRST digit of the target intermediate
the top digit?  Chance = 10%.  Per the paper, the cross-example mean logit vector is subtracted first
to remove position/layer bias. A shuffled-label control is reported alongside.

Reads only `lm_head.weight` and `model.norm.weight` from the safetensors shards (no full model load).

Usage:
  python -m stego.lens --cond filler --family syseq
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from safetensors import safe_open

MODEL = Path("/home/amit/models/hf/Qwen2.5-7B-Instruct")


def load_unembed(device):
    idx = json.loads((MODEL / "model.safetensors.index.json").read_text())["weight_map"]
    def get(name):
        with safe_open(MODEL / idx[name], framework="pt", device="cpu") as f:
            return f.get_tensor(name)
    W = get("lm_head.weight").to(torch.float32).to(device)      # [V, D]
    g = get("model.norm.weight").to(torch.float32).to(device)   # [D]
    return W, g


def rmsnorm(h, g, eps=1e-6):
    return h * torch.rsqrt(h.pow(2).mean(-1, keepdim=True) + eps) * g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cond", default="filler")
    ap.add_argument("--family", default="syseq")
    ap.add_argument("--root", default="results/probe")
    ap.add_argument("--targets", default="")   # comma list; default = all intermediates + ans
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()

    d = Path(args.root) / args.cond
    meta = json.loads((d / f"{args.family}.meta.json").read_text())
    resid = np.load(d / f"{args.family}.resid.npy", mmap_mode="r")      # [N, P, L1, D]
    N, P, L1, D = resid.shape
    names = meta["pos_names"]
    labels = meta["labels"]
    targets = args.targets.split(",") if args.targets else [k for k in labels[0] if not k.startswith("q_")]

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(MODEL))
    digit_ids = torch.tensor([tok.encode(str(i), add_special_tokens=False)[0] for i in range(10)])
    W, g = load_unembed(args.device)
    Wd = W[digit_ids.to(args.device)]                                       # [10, D]

    first_digit = {t: np.array([int(str(lab[t])[0]) for lab in labels]) for t in targets}
    rng = np.random.default_rng(0)
    shuffled = {t: rng.permutation(first_digit[t]) for t in targets}

    rows = []
    for p, pname in enumerate(names):
        for l in range(L1):
            h = torch.from_numpy(np.asarray(resid[:, p, l, :], dtype=np.float32)).to(args.device)  # [N, D]
            logits = rmsnorm(h, g) @ Wd.T                                    # [N, 10]
            logits = logits - logits.mean(0, keepdim=True)                   # cross-example mean subtraction
            top = logits.argmax(1).cpu().numpy()
            for t in targets:
                rows.append((t, pname, l, float((top == first_digit[t]).mean()),
                             float((top == shuffled[t]).mean())))
    out = d / f"{args.family}.lens.csv"
    with open(out, "w") as f:
        f.write("target,position,layer,top1_first_digit,top1_shuffled\n")
        for r in rows:
            f.write(",".join(map(str, r)) + "\n")

    # summary: best layer per (target, position group)
    print(f"logit lens {args.cond}/{args.family}: n={N}, chance=10%  (first digit of target; mean-subtracted)")
    print("| target | position | best layer | top-1 | shuffled |")
    print("|---|---|---|---|---|")
    groups = {}
    for pname in names:
        key = "dots" if pname.startswith("dot_") else pname
        groups.setdefault(key, []).append(pname)
    for t in targets:
        for key, pnames in groups.items():
            best = max((r for r in rows if r[0] == t and r[1] in pnames), key=lambda r: r[3])
            print(f"| {t} | {key}{'(' + best[1] + ')' if key == 'dots' else ''} | {best[2]} | {100 * best[3]:.0f}% | {100 * best[4]:.0f}% |")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
