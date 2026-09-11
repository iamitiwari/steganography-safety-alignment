"""Replicate Brauer et al. 2026's system-of-equations filler experiment on Qwen2.5-7B-Instruct,
using THEIR dataset, THEIR prompt builders and THEIR few-shot pool, only swapping the model.

Imports `build_prompt_messages_varbind` from the cloned paper repo
(/home/amit/filler-token-reasoning), so the system prompt, the `\\n\\nFiller: ...\\n\\nAnswer:`
scaffold, the bare-number assistant turns and the 5 held-out few-shot examples are byte-identical to
the paper's. Conditions follow their extraction/eval ladder: baseline (k=0) and dots / counting /
alphabet at several k.

Usage:
  python scripts/paper_varbind_replication.py                 # easy dataset (paper's Kimi K2.5 run)
  python scripts/paper_varbind_replication.py --dataset original
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PAPER = Path("/home/amit/filler-token-reasoning")
sys.path.insert(0, str(PAPER / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data.generate_varbind_dataset import build_prompt_messages_varbind  # noqa: E402  (paper repo)
from stego.client import Endpoint, LLMClient  # noqa: E402

DATASETS = {
    "easy": PAPER / "data/chained_var_binding_easy_dataset.json",
    "original": PAPER / "data/chained_var_binding_dataset.json",
}
# (filler_type, k). k=0 is the paper's no-filler baseline (no Filler: line at all).
LADDER = [("dots", 0), ("dots", 5), ("dots", 10), ("dots", 25), ("dots", 50), ("dots", 100),
          ("dots", 250), ("counting", 5), ("counting", 10), ("counting", 25), ("counting", 50),
          ("alphabet", 10), ("alphabet", 25), ("alphabet", 100)]
_NUM = re.compile(r"Answer:\s*(-?\d+)|(-?\d+)")


def extract(text: str) -> int | None:  # paper's prompt_utils.extract_answer, inlined
    m = re.search(r"Answer:\s*(-?\d+)", text) or re.search(r"(-?\d+)", text)
    return int(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=list(DATASETS), default="easy")
    ap.add_argument("--n", type=int, default=0, help="examples to use (0 = all 500)")
    ap.add_argument("--workers", type=int, default=128)
    ap.add_argument("--label", default="qwen2.5-7b-instruct-bf16")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    d = json.loads(DATASETS[args.dataset].read_text())
    few_shot = d["few_shot_examples"][:5]          # paper: "extraction/eval use the first 5"
    examples = d["examples"][: args.n] if args.n else d["examples"]
    out_dir = Path(args.out or f"results/paper_varbind_{args.dataset}_{args.label}")
    client = LLMClient(Endpoint(label=args.label), cache_dir="results/cache")
    t0 = time.time()

    def one(ft, k, ex):
        msgs = build_prompt_messages_varbind(few_shot, ex, ft, k, rng=random.Random(42))
        comp = client.chat(msgs, temperature=0.0, max_tokens=16)
        pred = extract(comp.text)
        return {"cond": "baseline" if k == 0 else f"{ft}_{k}", "filler_type": ft, "k": k,
                "idx": ex["idx"], "gold": ex["answer"], "pred": pred, "correct": pred == ex["answer"],
                "prompt_tokens": comp.prompt_tokens, "text": comp.text}

    jobs = [(ft, k, ex) for ft, k in LADDER for ex in examples]
    records = []
    with ThreadPoolExecutor(args.workers) as pool:
        futs = [pool.submit(one, *j) for j in jobs]
        for i, f in enumerate(as_completed(futs), 1):
            records.append(f.result())
            if i % 1000 == 0 or i == len(futs):
                print(f"{i}/{len(futs)} done, {time.time() - t0:.0f}s", flush=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    records.sort(key=lambda r: (LADDER.index((r["filler_type"], r["k"])), r["idx"]))
    with open(out_dir / "records.jsonl", "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    base = {r["idx"]: r["correct"] for r in records if r["cond"] == "baseline"}
    n = len(examples)
    lines = [f"Paper varbind ({args.dataset}) on {args.label}; n={n}; 5 few-shot (paper's held-out pool); temp 0",
             "", "| condition | accuracy | Δ vs baseline | wrong→right | right→wrong | max prompt tokens |",
             "|---|---|---|---|---|---|"]
    for ft, k in LADDER:
        cond = "baseline" if k == 0 else f"{ft}_{k}"
        rs = [r for r in records if r["cond"] == cond]
        acc = sum(r["correct"] for r in rs) / n
        bacc = sum(base.values()) / n
        wr = sum(r["correct"] and not base[r["idx"]] for r in rs)
        rw = sum(base[r["idx"]] and not r["correct"] for r in rs)
        lines.append(f"| {cond} | {100 * acc:.1f}% | {100 * (acc - bacc):+.1f} | {wr} | {rw} | "
                     f"{max(r['prompt_tokens'] for r in rs)} |")
    unparsed = Counter(r["cond"] for r in records if r["pred"] is None)
    summary = "\n".join(lines) + f"\n\nunparsed: {dict(unparsed)}\nwall-clock: {time.time() - t0:.0f}s\n"
    (out_dir / "summary.md").write_text(summary)
    print(summary)


if __name__ == "__main__":
    main()
