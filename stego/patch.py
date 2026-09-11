"""Hours 10-15 (step 4): activation patching — is the filler region causally used by the answer position?

Matched pairs: item A and its counterfactual twin B (same prompt except one number: syseq `x`, chain
`N`), so answers differ. We run A with the residual stream at chosen positions and layer(s) replaced,
and measure at the final position (the one that predicts the first answer token):

  recovery  = (m_patched - m_A) / (m_B - m_A),   m = logit(first digit of B's answer) - logit(first digit of A's answer)
              0 = no effect, 1 = output moved fully to what B would produce
  kl        = KL(patched next-token distribution || clean A)
  probe     = (probe(x)_patched - x_A) / (x_B - x_A) with a ridge probe for the prompt operand fitted on
              clean runs at the final position (does the operand reach the answer position via the dots?)

Sources (what is written into A):
  twin_dots      B's residuals at all dot positions                    (paper's KV-transplant analogue)
  twin_operand   B's residuals at the operand's digit tokens in the question   (positive control)
  other_dots     an unrelated item's residuals at the dot positions
  mean_dots      the across-item mean residual at the dot positions   (mean ablation)
  random_dots    Gaussian noise with the same norm as A's own vector  (README's random-vector control)
Layers: each L in --layers replaces the OUTPUT of decoder layer L (= hidden_states[L+1]); "all" replaces
every layer's output at those positions (= transplanting the region's whole computation).

Usage:
  CUDA_VISIBLE_DEVICES=1 python -m stego.patch --family chain --n 500
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch

from .conditions import build_messages
from .tasks import load

MODEL = "/home/amit/models/hf/Qwen2.5-7B-Instruct"
SOURCES = ["twin_dots", "twin_operand", "other_dots", "mean_dots", "random_dots"]


# --------------------------------------------------------------------------- prompt / positions
def _tok_at(offs, char):
    for i, (s, e) in enumerate(offs):
        if s <= char < e:
            return i
    raise ValueError(char)


def prompt_and_positions(tok, item, k):
    msgs = build_messages(item, "filler", k_filler=k)
    text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    enc = tok(text, return_offsets_mapping=True, add_special_tokens=False)
    offs = enc["offset_mapping"]
    fi, ai = text.rfind("\nFiller:"), text.rfind("\nAnswer:")
    dots = [i for i, (s, e) in enumerate(offs) if fi < s < ai and text[s:e].strip() == "."]
    # operand digits in the question (search from the FIRST "Question: " — syseq prompts contain a
    # second one, "Question: What is ...", after the variable block)
    q0 = text.find("Question: ")
    p = item["params"]
    if item["family"] == "syseq":
        needle = f"\n{p['names'][1]} = {p['x']}\n"
        i = text.find(needle, q0)
        assert i >= 0, (needle, text[q0:q0 + 200])
        c0 = i + len(needle) - 1 - len(str(p["x"]))
        span = (c0, c0 + len(str(p["x"])))
    else:
        needle = f"Start with {p['N']}."
        i = text.find(needle, q0)
        assert i >= 0, (needle, text[q0:q0 + 200])
        c0 = i + len("Start with ")
        span = (c0, c0 + len(str(p["N"])))
    assert text[span[0]:span[1]] == str(p["x" if item["family"] == "syseq" else "N"]), text[span[0] - 10:span[1] + 10]
    operand = sorted({_tok_at(offs, c) for c in range(*span)})
    return text, {"dots": dots, "operand": operand, "final": len(offs) - 1}


def twin_item(item):
    cf = item["counterfactual"]
    t = dict(item)
    t["question"], t["answer"] = cf["question"], cf["answer"]
    t["params"] = dict(item["params"])
    key = "x" if item["family"] == "syseq" else "N"
    t["params"][key] = int(next(iv["value"] for iv in cf["intermediates"] if iv["name"] == ("x" if key == "x" else "s1"))) - (
        0 if key == "x" else item["params"]["a"])
    return t


# --------------------------------------------------------------------------- model plumbing
class Patcher:
    """Registers hooks on decoder layers; `plan[L] = (mask[B,T] bool, src[B,T,D] or callable)`."""

    def __init__(self, model):
        self.model = model
        self.layers = model.model.layers
        self.plan = {}
        self.handles = [layer.register_forward_hook(self._hook(i)) for i, layer in enumerate(self.layers)]

    def _hook(self, i):
        def f(module, inp, out):
            if i not in self.plan:
                return out
            mask, src = self.plan[i]
            h = out[0] if isinstance(out, tuple) else out
            rep = src(h) if callable(src) else src
            h = torch.where(mask.unsqueeze(-1), rep.to(h.dtype), h)
            return (h, *out[1:]) if isinstance(out, tuple) else h
        return f

    def clear(self):
        self.plan = {}


@torch.no_grad()
def run(model, enc, want_hidden=False):
    out = model(**enc, output_hidden_states=want_hidden)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="chain")
    ap.add_argument("--data", default="data/probe_v1.jsonl")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--k", type=int, default=25)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--layers", default="0,4,8,12,16,20,24,all")
    ap.add_argument("--probe_layer", type=int, default=24)
    ap.add_argument("--out", default="results/patch")
    args = ap.parse_args()
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    tok.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16).to("cuda").eval()
    L = model.config.num_hidden_layers
    D = model.config.hidden_size
    digit_id = {str(i): tok.encode(str(i), add_special_tokens=False)[0] for i in range(10)}

    items = [it for it in load(args.data) if it["family"] == args.family][: args.n]
    pairs = []
    for it in items:
        tw = twin_item(it)
        ta, pa = prompt_and_positions(tok, it, args.k)
        tb, pb = prompt_and_positions(tok, tw, args.k)
        na, nb = len(tok(ta, add_special_tokens=False)["input_ids"]), len(tok(tb, add_special_tokens=False)["input_ids"])
        if na != nb or pa != pb or str(it["answer"])[0] == str(tw["answer"])[0]:
            continue                      # need identical token layout and a different first answer digit
        pairs.append((it, tw, ta, tb, pa))
    print(f"{args.family}: {len(pairs)} usable pairs of {len(items)} (same token layout, different first digit)", flush=True)

    layer_specs = [("all" if s == "all" else int(s)) for s in args.layers.split(",")]
    patcher = Patcher(model)
    t0 = time.time()
    rows, means, probe_X, probe_y = [], None, [], []

    for b0 in range(0, len(pairs), args.batch):
        chunk = pairs[b0:b0 + args.batch]
        B = len(chunk)
        encA = tok([c[2] for c in chunk], return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
        encB = tok([c[3] for c in chunk], return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
        T = encA["input_ids"].shape[1]
        pad = (T - encA["attention_mask"].sum(1)).tolist()
        # position masks (left padding offset per row)
        masks = {}
        for key in ("dots", "operand"):
            m = torch.zeros(B, T, dtype=torch.bool, device="cuda")
            for j, c in enumerate(chunk):
                for p in c[4][key]:
                    m[j, p + pad[j]] = True
            masks[key] = m
        # clean runs
        patcher.clear()
        outA = run(model, encA, want_hidden=True)
        outB = run(model, encB, want_hidden=True)
        hsA = [h.clone() for h in outA.hidden_states]      # L+1 tensors [B,T,D]; hsA[l+1] = output of layer l
        hsB = [h.clone() for h in outB.hidden_states]
        if means is None:                                   # across-item mean at dot positions, per layer output
            means = [hs[masks["dots"]].float().mean(0) for hs in hsA[1:]]
        # readouts
        dA = torch.tensor([digit_id[str(c[0]["answer"])[0]] for c in chunk], device="cuda")
        dB = torch.tensor([digit_id[str(c[1]["answer"])[0]] for c in chunk], device="cuda")
        ar = torch.arange(B, device="cuda")

        def metric(logits):                                 # [B, V] at final position
            return (logits[ar, dB] - logits[ar, dA]).float()

        logpA = torch.log_softmax(outA.logits[:, -1].float(), -1)
        mA, mB = metric(outA.logits[:, -1]), metric(outB.logits[:, -1])
        xA = torch.tensor([float(c[0]["params"]["x" if args.family == "syseq" else "N"]) for c in chunk])
        xB = torch.tensor([float(c[1]["params"]["x" if args.family == "syseq" else "N"]) for c in chunk])
        probe_X.append(hsA[args.probe_layer + 1][:, -1].float().cpu().numpy()); probe_y.append(xA.numpy())

        for spec in layer_specs:
            Ls = list(range(L)) if spec == "all" else [spec]
            for src in SOURCES:
                patcher.clear()
                for l in Ls:
                    if src == "twin_dots":
                        patcher.plan[l] = (masks["dots"], hsB[l + 1])
                    elif src == "twin_operand":
                        patcher.plan[l] = (masks["operand"], hsB[l + 1])
                    elif src == "other_dots":
                        patcher.plan[l] = (masks["dots"], hsB[l + 1].roll(1, dims=0))   # another pair's twin
                    elif src == "mean_dots":
                        patcher.plan[l] = (masks["dots"], means[l].expand(B, T, D))
                    elif src == "random_dots":
                        patcher.plan[l] = (masks["dots"], (lambda h: torch.randn_like(h, dtype=torch.float32)
                                                          * (h.float().norm(dim=-1, keepdim=True) / D ** 0.5)))
                out = run(model, encA, want_hidden=True)
                mP = metric(out.logits[:, -1])
                logpP = torch.log_softmax(out.logits[:, -1].float(), -1)
                kl = (logpP.exp() * (logpP - logpA)).sum(-1)
                hP = out.hidden_states[args.probe_layer + 1][:, -1].float().cpu().numpy()
                for j, c in enumerate(chunk):
                    rows.append({"id": c[0]["id"], "layer": spec, "source": src,
                                 "mA": mA[j].item(), "mB": mB[j].item(), "mP": mP[j].item(),
                                 "kl": kl[j].item(), "xA": xA[j].item(), "xB": xB[j].item(),
                                 "hP": hP[j]})
        patcher.clear()
        print(f"  {min(b0 + args.batch, len(pairs))}/{len(pairs)} pairs, {time.time() - t0:.0f}s", flush=True)

    # probe for the operand at the final position, fitted on the clean A runs
    from sklearn.decomposition import PCA
    from sklearn.linear_model import RidgeCV
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    X, y = np.concatenate(probe_X), np.concatenate(probe_y)
    probe = make_pipeline(StandardScaler(), PCA(min(64, len(y) - 1), random_state=0), RidgeCV(alphas=np.logspace(0, 5, 11))).fit(X, y)
    fit_r2 = probe.score(X, y)
    clean_pred = dict(zip([c[0]["id"] for c in pairs], probe.predict(X)))   # per-pair baseline on the clean A run
    for r in rows:
        r["probe_x"] = float(probe.predict(r.pop("hP")[None])[0])
        r["probe_clean"] = float(clean_pred[r["id"]])

    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / f"{args.family}.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    # summary
    lines = [f"activation patching, {args.family}, {len(pairs)} twin pairs, k={args.k} dots; "
             f"probe for operand at final/L{args.probe_layer} fit R2={fit_r2:.2f}", "",
             "recovery = (m_patched - m_A)/(m_B - m_A) on the first-digit logit difference, pairs with |m_B - m_A| > 0.5; "
             "probe shift = (probe_x - x_A)/(x_B - x_A); KL vs clean A (nats)", "",
             "| layer | source | n | recovery mean | recovery median | probe shift | KL |", "|---|---|---|---|---|---|---|"]
    for spec in layer_specs:
        for src in SOURCES:
            rs = [r for r in rows if r["layer"] == spec and r["source"] == src]
            ok = [r for r in rs if abs(r["mB"] - r["mA"]) > 0.5]
            rec = np.array([(r["mP"] - r["mA"]) / (r["mB"] - r["mA"]) for r in ok])
            ps = np.array([(r["probe_x"] - r["probe_clean"]) / (r["xB"] - r["xA"]) for r in rs])
            kl = np.array([r["kl"] for r in rs])
            lines.append(f"| {spec} | {src} | {len(ok)} | {rec.mean():+.2f} | {np.median(rec):+.2f} | {ps.mean():+.2f} | {kl.mean():.3f} |")
    summary = "\n".join(lines) + f"\n\nwall-clock {time.time() - t0:.0f}s\n"
    (out_dir / f"{args.family}.summary.md").write_text(summary)
    print(summary)


if __name__ == "__main__":
    main()
