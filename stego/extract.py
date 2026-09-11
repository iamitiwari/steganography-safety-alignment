"""Hours 10-15: residual-stream extraction at chosen token positions (GPU, HF transformers, bf16).

Conditions
  filler   zero-shot filler prompt (k dots). Positions: q_last (the '?' of the question),
           dot_0 .. dot_{m-1} (every dot token in the target's filler region), final (last prompt token,
           i.e. the position that predicts the first answer token).
  direct   zero-shot direct prompt. Positions: q_last, final.
  sym      teacher-forced: canonical `sym_cot` supplied as the assistant turn. For every intermediate
           (in order) and the answer: pre_<name> = last token of the marker before the value ('='),
           val_<name> = last token of the value itself.
  nl       same with `nl_cot` (markers 'is' for syseq, 'gives' for chain).

Output per (condition, family):
  results/probe/<cond>/<family>.resid.npy   float16 memmap [N, P, L+1, D]   (L+1 = embeddings + 28 layers)
  results/probe/<cond>/<family>.meta.json   ids, position names, per-item labels, per-item final argmax token

Usage:
  CUDA_VISIBLE_DEVICES=1 python -m stego.extract --conditions filler,direct,sym,nl --k 25
  CUDA_VISIBLE_DEVICES=1 python -m stego.extract --check 3      # print positions for 3 items, no extraction
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch

from .conditions import build_messages
from .tasks import load

MODEL = "/home/amit/models/hf/Qwen2.5-7B-Instruct"
NL_MARKER = {"syseq": "is", "chain": "gives"}


# --------------------------------------------------------------------------- position finding
def _tok_at(offs, char: int) -> int:
    """Index of the token whose span contains `char`."""
    for i, (s, e) in enumerate(offs):
        if s <= char < e:
            return i
    raise ValueError(f"no token covers char {char}")


def positions_filler(tok, text: str, k: int) -> dict[str, int]:
    enc = tok(text, return_offsets_mapping=True, add_special_tokens=False)
    offs = enc["offset_mapping"]
    fi = text.rfind("\nFiller:")
    ai = text.rfind("\nAnswer:")
    assert 0 < fi < ai
    dots = [i for i, (s, e) in enumerate(offs) if fi < s < ai and text[s:e].strip() == "."]
    pos = {"q_last": _tok_at(offs, fi - 1)}
    pos.update({f"dot_{j}": p for j, p in enumerate(dots)})
    pos["final"] = len(offs) - 1
    return pos


def positions_direct(tok, text: str) -> dict[str, int]:
    enc = tok(text, return_offsets_mapping=True, add_special_tokens=False)
    offs = enc["offset_mapping"]
    ai = text.rfind("\nAnswer:")
    return {"q_last": _tok_at(offs, ai - 1), "final": len(offs) - 1}


def positions_cot(tok, text: str, cot: str, item: dict, fmt: str) -> dict[str, int] | None:
    """pre_<name>/val_<name> for each intermediate and the answer, in order. None if ambiguous."""
    enc = tok(text, return_offsets_mapping=True, add_special_tokens=False)
    offs = enc["offset_mapping"]
    base = text.rfind(cot)
    assert base >= 0
    marker = "=" if fmt == "sym" else NL_MARKER[item["family"]]
    targets = [(iv["name"], iv["value"]) for iv in item["intermediates"]] + [("ans", item["answer"])]
    pos, last_char = {}, -1
    for name, val in targets:
        m = re.search(rf"{re.escape(marker)} {re.escape(str(val))}(?!\d)", cot)
        if m is None or m.start() <= last_char:      # missing, or out of order (value collision)
            return None
        last_char = m.start()
        pre_char = base + m.start() + len(marker) - 1
        val_end = base + m.end() - 1
        pos[f"pre_{name}"] = _tok_at(offs, pre_char)
        pos[f"val_{name}"] = _tok_at(offs, val_end)
    return pos


def build(tok, item: dict, cond: str, k: int):
    """Return (text, positions) for one item under one condition."""
    if cond == "filler":
        msgs = build_messages(item, "filler", k_filler=k)
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        return text, positions_filler(tok, text, k)
    if cond == "direct":
        msgs = build_messages(item, "direct")
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        return text, positions_direct(tok, text)
    fmt = cond  # sym | nl
    cot = item["sym_cot"] if fmt == "sym" else item["nl_cot"]
    msgs = build_messages(item, "symbolic" if fmt == "sym" else "nl_cot") + [{"role": "assistant", "content": cot}]
    text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
    return text, positions_cot(tok, text, cot, item, fmt)


# --------------------------------------------------------------------------- extraction
@torch.no_grad()
def extract(model, tok, items, cond, k, batch, out_dir: Path):
    by_fam = defaultdict(list)
    for it in items:
        by_fam[it["family"]].append(it)
    for fam, fam_items in by_fam.items():
        built, skipped = [], 0
        for it in fam_items:
            text, pos = build(tok, it, cond, k)
            if pos is None:
                skipped += 1
                continue
            built.append((it, text, pos))
        names = list(built[0][2].keys())
        assert all(list(b[2].keys()) == names for b in built), "position layout differs across items"
        N, P = len(built), len(names)
        L1, D = model.config.num_hidden_layers + 1, model.config.hidden_size
        out_dir.mkdir(parents=True, exist_ok=True)
        resid = np.lib.format.open_memmap(out_dir / f"{fam}.resid.npy", mode="w+", dtype=np.float16,
                                          shape=(N, P, L1, D))
        final_argmax, t0 = [], time.time()
        for b0 in range(0, N, batch):
            chunk = built[b0:b0 + batch]
            enc = tok([c[1] for c in chunk], return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
            out = model(**enc, output_hidden_states=True)
            hs = torch.stack(out.hidden_states, 0)                       # [L+1, B, T, D]
            T = enc["input_ids"].shape[1]
            for j, (it, text, pos) in enumerate(chunk):
                n_tok = int(enc["attention_mask"][j].sum())
                pad = T - n_tok                                             # left padding offset
                idx = torch.tensor([pos[n] + pad for n in names], device=hs.device)
                resid[b0 + j] = hs[:, j, idx, :].permute(1, 0, 2).to(torch.float16).cpu().numpy()
                final_argmax.append(int(out.logits[j, -1].argmax()))
            print(f"  {cond}/{fam}: {min(b0 + batch, N)}/{N}  {time.time() - t0:.0f}s", flush=True)
        resid.flush()
        meta = {"condition": cond, "family": fam, "k": k, "model": MODEL, "pos_names": names,
                "skipped_ambiguous": skipped, "ids": [b[0]["id"] for b in built],
                "labels": [{"answer": b[0]["answer"], **{iv["name"]: iv["value"] for iv in b[0]["intermediates"]},
                            **{f"q_{kk}": v for kk, v in b[0]["params"].items() if isinstance(v, int)}}
                           for b in built],
                "final_argmax_token": [tok.decode([t]) for t in final_argmax],
                "shape": [N, P, L1, D]}
        (out_dir / f"{fam}.meta.json").write_text(json.dumps(meta))
        print(f"wrote {out_dir / fam}.resid.npy {resid.shape} ({resid.nbytes / 1e9:.1f} GB), skipped {skipped}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/probe_v1.jsonl")
    ap.add_argument("--conditions", default="filler,direct,sym,nl")
    ap.add_argument("--k", type=int, default=25)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--out", default="results/probe")
    ap.add_argument("--limit", type=int, default=0, help="items per family (0 = all)")
    ap.add_argument("--check", type=int, default=0, help="print positions for N items per family and exit")
    args = ap.parse_args()
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    tok.padding_side = "left"
    items = load(args.data)
    if args.limit or args.check:
        per, keep, n = defaultdict(int), [], args.limit or args.check
        for it in items:
            if per[it["family"]] < n:
                per[it["family"]] += 1
                keep.append(it)
        items = keep
    if args.check:
        for cond in args.conditions.split(","):
            for it in items:
                text, pos = build(tok, it, cond, args.k)
                enc = tok(text, add_special_tokens=False)["input_ids"]
                print(f"--- {cond} {it['id']} ({len(enc)} tokens) answer={it['answer']} intermediates={[(i['name'], i['value']) for i in it['intermediates']]}")
                if pos is None:
                    print("   AMBIGUOUS, skipped")
                    continue
                shown = {n: (p, tok.decode([enc[p]])) for n, p in pos.items()}
                if cond == "filler":
                    dots = [n for n in shown if n.startswith("dot_")]
                    shown = {n: shown[n] for n in ["q_last", dots[0], dots[-1], "final"]}
                    shown["n_dots"] = len(dots)
                print("   ", shown)
        return
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16).to("cuda").eval()
    for cond in args.conditions.split(","):
        extract(model, tok, items, cond, args.k, args.batch, Path(args.out) / cond)


if __name__ == "__main__":
    main()
