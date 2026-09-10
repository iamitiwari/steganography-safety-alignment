"""Difficulty-calibration smoke run: every item under a few conditions on the live server.

Usage:
  python -m stego.smoke --data data/tasks_v1.jsonl --conditions direct,nl_cot --workers 16
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .client import Endpoint, LLMClient
from .conditions import build_messages, extract_answer, is_correct
from .tasks import load

MAX_TOKENS = {"direct": 16, "filler": 16, "nl_cot": 700, "symbolic": 700}


def _shots(items, it, n):
    """n few-shot demonstrations: the next n items of the same subtype (cyclic), never the item itself."""
    same = [x for x in items if x["subtype"] == it["subtype"]]
    i = same.index(it)
    return (same[i + 1:] + same[:i])[:n]


def run(items, conditions, workers, out_dir: Path, k_filler: int, filler_type: str,
        temperature: float, label: str, fewshot: int = 0):
    client = LLMClient(Endpoint(label=label), cache_dir="results/cache")
    jobs = [(it, c) for c in conditions for it in items]
    records = []
    t0 = time.time()

    def one(it, c):
        shots = _shots(items, it, fewshot) if fewshot else None
        msgs = build_messages(it, c, k_filler=k_filler, filler_type=filler_type, fewshot=shots)
        comp = client.chat(msgs, temperature=temperature, max_tokens=MAX_TOKENS[c])
        return {"id": it["id"], "family": it["family"], "subtype": it["subtype"], "condition": c,
                "k_filler": k_filler if c == "filler" else 0, "fewshot": fewshot,
                "pred": extract_answer(comp.text, it["answer_type"]), "gold": it["answer"],
                "correct": is_correct(it, comp.text), "finish": comp.finish_reason,
                "completion_tokens": comp.completion_tokens, "cached": comp.cached,
                "label": label, "model": comp.raw.get("model"), "text": comp.text}

    with ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(one, it, c) for it, c in jobs]
        for i, f in enumerate(as_completed(futs), 1):
            records.append(f.result())
            if i % 25 == 0 or i == len(futs):
                print(f"{i}/{len(futs)} done, {time.time() - t0:.0f}s", flush=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "records.jsonl", "w") as f:
        for r in sorted(records, key=lambda r: (r["condition"], r["id"])):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # summary table: subtype x condition
    acc = defaultdict(lambda: defaultdict(list))
    for r in records:
        acc[r["subtype"]][r["condition"]].append(r["correct"])
        acc["ALL"][r["condition"]].append(r["correct"])
    lines = ["| subtype | n | " + " | ".join(conditions) + " |", "|---|---|" + "---|" * len(conditions)]
    for st in list(dict.fromkeys([r["subtype"] for r in sorted(records, key=lambda r: r["id"])])) + ["ALL"]:
        n = len(acc[st][conditions[0]])
        cells = [f"{100 * sum(acc[st][c]) / max(1, len(acc[st][c])):.0f}%" for c in conditions]
        lines.append(f"| {st} | {n} | " + " | ".join(cells) + " |")
    trunc = {c: sum(r["finish"] == "length" for r in records if r["condition"] == c) for c in conditions}
    noparse = {c: sum(r["pred"] is None for r in records if r["condition"] == c) for c in conditions}
    summary = "\n".join(lines) + f"\n\ntruncated (finish=length): {trunc}\nunparsed answers: {noparse}\n"
    summary += (f"wall-clock: {time.time() - t0:.0f}s; label={label}; k_filler={k_filler}; "
                f"filler_type={filler_type}; fewshot={fewshot}\n")
    (out_dir / "summary.md").write_text(summary)
    print(summary)

    # 5 raw completions per subtype for manual inspection
    with open(out_dir / "samples.md", "w") as f:
        seen = defaultdict(int)
        for r in sorted(records, key=lambda r: (r["subtype"], r["condition"], r["id"])):
            key = (r["subtype"], r["condition"])
            if seen[key] >= 5:
                continue
            seen[key] += 1
            it = next(x for x in items if x["id"] == r["id"])
            f.write(f"## {r['id']} / {r['condition']} / correct={r['correct']} pred={r['pred']} gold={r['gold']}\n\n")
            f.write(f"**Q:** {it['question']}\n\n```\n{r['text']}\n```\n\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/tasks_v1.jsonl")
    ap.add_argument("--conditions", default="direct,nl_cot")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--out", default="results/smoke_qwen2.5-7b")
    ap.add_argument("--k-filler", type=int, default=25)
    ap.add_argument("--filler-type", default="dots")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--label", default="qwen2.5-7b-instruct-q8")
    ap.add_argument("--limit", type=int, default=0, help="items per subtype (0 = all)")
    ap.add_argument("--fewshot", type=int, default=0, help="same-subtype demonstrations per prompt")
    args = ap.parse_args()
    items = load(args.data)
    if args.limit:
        per = defaultdict(int)
        keep = []
        for it in items:
            if per[it["subtype"]] < args.limit:
                per[it["subtype"]] += 1
                keep.append(it)
        items = keep
    run(items, args.conditions.split(","), args.workers, Path(args.out), args.k_filler,
        args.filler_type, args.temperature, args.label, fewshot=args.fewshot)


if __name__ == "__main__":
    main()
