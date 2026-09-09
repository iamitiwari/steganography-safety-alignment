"""Feasibility check for Hours 10-15: load Qwen2.5-7B-Instruct with HF transformers on CPU,
run one forward pass with hidden states, and apply the logit lens at filler positions.

Usage: python scripts/hf_smoke.py [--dtype bf16|fp32] [--k 25]
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stego.conditions import build_messages  # noqa: E402
from stego.tasks import load  # noqa: E402

MODEL = os.environ.get("HF_MODEL", "/home/amit/models/hf/Qwen2.5-7B-Instruct")


def rss_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dtype", default="bf16")
    ap.add_argument("--k", type=int, default=25)
    ap.add_argument("--threads", type=int, default=24)
    ap.add_argument("--item", default="syseq_000")
    args = ap.parse_args()
    torch.set_num_threads(args.threads)
    from transformers import AutoModelForCausalLM, AutoTokenizer

    dtype = {"bf16": torch.bfloat16, "fp32": torch.float32}[args.dtype]
    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=dtype, low_cpu_mem_usage=True)
    model.eval()
    print(f"loaded in {time.time() - t0:.0f}s, rss={rss_gb():.1f}GB, dtype={dtype}, "
          f"layers={model.config.num_hidden_layers}, d={model.config.hidden_size}", flush=True)

    items = load("data/tasks_v1.jsonl")
    item = next(it for it in items if it["id"] == args.item)
    msgs = build_messages(item, "filler", k_filler=args.k)
    text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    enc = tok(text, return_tensors="pt")
    ids = enc["input_ids"][0]
    # locate filler region: tokens between "Filler:" and "Answer:" in the last user turn
    dot_id = tok.encode(" .", add_special_tokens=False)
    print("token ids for ' .':", dot_id)
    positions = [i for i, t in enumerate(ids.tolist()) if t in dot_id]
    print(f"prompt tokens={len(ids)}, filler positions found={len(positions)}", flush=True)

    t1 = time.time()
    with torch.no_grad():
        out = model(**enc, output_hidden_states=True)
    dt = time.time() - t1
    print(f"forward pass: {dt:.1f}s for {len(ids)} tokens, rss={rss_gb():.1f}GB", flush=True)

    # greedy next token (should be the answer digits)
    nxt = out.logits[0, -1].argmax().item()
    print("next token:", repr(tok.decode([nxt])), "| gold answer:", item["answer"],
          "| intermediates:", item["intermediates"], flush=True)

    # logit lens at filler positions, late layers
    norm = model.model.norm
    head = model.lm_head
    hs = out.hidden_states  # tuple(len = layers+1) of [1, T, d]
    L = len(hs) - 1
    layers = [L // 2, 3 * L // 4, L - 4, L - 1]
    sel = positions[:: max(1, len(positions) // 5)][:5] + [len(ids) - 1]
    with torch.no_grad():
        for layer in layers:
            row = []
            for p in sel:
                logits = head(norm(hs[layer][0, p].float().to(dtype)))
                top = logits.float().topk(5).indices.tolist()
                row.append(f"pos{p}:" + "/".join(repr(tok.decode([t])) for t in top))
            print(f"L{layer:02d} " + "  ".join(row), flush=True)
    t2 = time.time()
    # timing for a batched extraction estimate
    print(json.dumps({"load_s": round(t1 - t0), "forward_s": round(dt, 1), "lens_s": round(t2 - t1 - dt, 1),
                      "prompt_tokens": len(ids), "rss_gb": round(rss_gb(), 1), "dtype": args.dtype}))


if __name__ == "__main__":
    main()
