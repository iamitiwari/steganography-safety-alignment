"""Hours 10-15, cipher family: can the PLAINTEXT letter be read from the residual stream before the
token is generated?  (README angle 2: "extract the true plaintext intermediate values before the
token itself is generated".)

Items: every WORDS x shift {1,2,3} x queried position {2,3,last} for the `letter` subtype (702 unique).

Conditions and positions
  sym / nl   teacher-forced canonical scratchpad. Per plaintext letter i (letter-level rows):
               cipher_i  the ciphertext letter token (' U')     arrow_i  the '->' token (letter not yet written)
               plain_i   the plaintext letter token ('r')       (sanity: trivially decodable)
             Per item: word_pre (the token before the decoded word), word_tok, ans_pre (token before the
             answer letter), ans_tok.
  filler     zero-shot 25 dots: q_last, dot_0, dot_6, dot_12, dot_18, dot_24, final.   direct: q_last, final.

Probe: StandardScaler -> PCA-64 -> multinomial logistic regression, 5-fold CV accuracy, 26-way.
Targets: letter-level = plaintext letter p_i;  item-level = the answer letter.
Controls: shuffled labels; majority class; INPUT CEILING = the same classifier on one-hot(cipher letter)
+ one-hot(shift) [+ one-hot(queried position)], i.e. what a linear readout of the prompt's symbols can
reach without doing the modular subtraction.

Usage:
  CUDA_VISIBLE_DEVICES=1 python -m stego.cipher_probe --stage extract
  python -m stego.cipher_probe --stage probe
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

from .conditions import build_messages
from .tasks import WORDS, _cipher_instance, _item

MODEL = "/home/amit/models/hf/Qwen2.5-7B-Instruct"
ROOT = Path("results/probe/cipher")
LAYERS = [0, 4, 8, 12, 16, 20, 24, 28]


# --------------------------------------------------------------------------- items
def build_items():
    items, seen = [], set()
    for w in WORDS:
        for k in (1, 2, 3):
            for pos in (2, 3, len(w)):
                inst = _cipher_instance(w, k, "letter", pos)
                if inst["question"] in seen:
                    continue
                seen.add(inst["question"])
                items.append(_item("cipher", "letter", len(items), inst["question"], inst["answer"],
                                   inst["answer_type"], inst["intermediates"], inst["nl_cot"], inst["sym_cot"],
                                   inst["params"], {"changed": "", "question": "", "answer": "", "intermediates": []}))
    return items


# --------------------------------------------------------------------------- positions
def _tok_at(offs, char):
    for i, (s, e) in enumerate(offs):
        if s <= char < e:
            return i
    raise ValueError(char)


def positions(tok, item, cond, k=25):
    """Return (text, item_positions{name: tok}, letter_positions[list of {cipher, arrow, plain}])."""
    p = item["params"]
    word, enc_word = p["word"], p["ciphertext"]
    if cond in ("filler", "direct"):
        msgs = build_messages(item, cond, k_filler=k)
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        enc = tok(text, return_offsets_mapping=True, add_special_tokens=False)
        offs = enc["offset_mapping"]
        ai = text.rfind("\nAnswer:")
        pos = {"final": len(offs) - 1}
        if cond == "filler":
            fi = text.rfind("\nFiller:")
            dots = [i for i, (s, e) in enumerate(offs) if fi < s < ai and text[s:e].strip() == "."]
            pos["q_last"] = _tok_at(offs, fi - 1)
            for j in (0, 6, 12, 18, len(dots) - 1):
                pos[f"dot_{j}"] = dots[j]
        else:
            pos["q_last"] = _tok_at(offs, ai - 1)
        return text, pos, []
    cot = item["sym_cot"] if cond == "sym" else item["nl_cot"]
    msgs = build_messages(item, "symbolic" if cond == "sym" else "nl_cot") + [{"role": "assistant", "content": cot}]
    text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
    enc = tok(text, return_offsets_mapping=True, add_special_tokens=False)
    offs = enc["offset_mapping"]
    base = text.rfind(cot)
    per = ", ".join(f"{e}->{c}" for e, c in zip(enc_word, word))
    i0 = base + cot.index(per)
    letters, c = [], i0
    for e, ch in zip(enc_word, word):
        letters.append({"cipher": _tok_at(offs, c), "arrow": _tok_at(offs, c + 1), "plain": _tok_at(offs, c + 3)})
        c += len(f"{e}->{ch}, ")
    ans = item["answer"]
    if cond == "sym":
        wq = base + cot.index(f"= {word}\n")                       # " =" before the word token
        w0 = wq + 2
        aq = base + cot.rindex("=")                                # last " =" before the answer letter
        a0 = aq + 2
    else:
        wq = base + cot.index(f"'{word}'")                         # " '" before the word
        w0 = wq + 1
        aq = base + cot.index(f"letter is '{ans}'") + len("letter is ")
        a0 = aq + 1
    pos = {"word_pre": _tok_at(offs, wq), "word_tok": _tok_at(offs, w0),
           "ans_pre": _tok_at(offs, aq), "ans_tok": _tok_at(offs, a0)}
    return text, pos, letters


# --------------------------------------------------------------------------- extraction
def extract(conds, batch):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    tok.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16).to("cuda").eval()
    L1, D = model.config.num_hidden_layers + 1, model.config.hidden_size
    items = build_items()
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "items.jsonl").write_text("\n".join(json.dumps(it) for it in items) + "\n")
    for cond in conds:
        built = [(it, *positions(tok, it, cond)) for it in items]
        names = list(built[0][2].keys())
        n_item, n_let = len(built), sum(len(b[3]) for b in built)
        R_item = np.lib.format.open_memmap(ROOT / f"{cond}.item.npy", "w+", np.float16, (n_item, len(names), L1, D))
        R_let = np.lib.format.open_memmap(ROOT / f"{cond}.letter.npy", "w+", np.float16, (n_let, 3, L1, D)) if n_let else None
        let_meta, li, t0 = [], 0, time.time()
        with torch.no_grad():
            for b0 in range(0, n_item, batch):
                chunk = built[b0:b0 + batch]
                enc = tok([c[1] for c in chunk], return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
                hs = torch.stack(model(**enc, output_hidden_states=True).hidden_states, 0)   # [L1, B, T, D]
                T = enc["input_ids"].shape[1]
                for j, (it, text, pos, letters) in enumerate(chunk):
                    pad = T - int(enc["attention_mask"][j].sum())
                    idx = torch.tensor([pos[n] + pad for n in names], device="cuda")
                    R_item[b0 + j] = hs[:, j, idx].permute(1, 0, 2).to(torch.float16).cpu().numpy()
                    for i, lp in enumerate(letters):
                        idx = torch.tensor([lp["cipher"] + pad, lp["arrow"] + pad, lp["plain"] + pad], device="cuda")
                        R_let[li] = hs[:, j, idx].permute(1, 0, 2).to(torch.float16).cpu().numpy()
                        let_meta.append({"item": b0 + j, "i": i, "cipher": it["params"]["ciphertext"][i],
                                         "plain": it["params"]["word"][i], "shift": it["params"]["shift"]})
                        li += 1
                print(f"  {cond}: {min(b0 + batch, n_item)}/{n_item} {time.time() - t0:.0f}s", flush=True)
        R_item.flush()
        if R_let is not None:
            R_let.flush()
        meta = {"cond": cond, "pos_names": names, "letter_pos_names": ["cipher", "arrow", "plain"],
                "items": [{"answer": it["answer"], "shift": it["params"]["shift"], "pos": it["params"]["pos"],
                           "cipher_q": it["params"]["ciphertext"][it["params"]["pos"] - 1]} for it, *_ in built],
                "letters": let_meta}
        (ROOT / f"{cond}.meta.json").write_text(json.dumps(meta))
        print(f"wrote {cond}: item {R_item.shape}" + (f", letter {R_let.shape}" if R_let is not None else ""), flush=True)


# --------------------------------------------------------------------------- probes
def cv_acc(X, y, seed=0, n_pca=64):
    from sklearn.decomposition import PCA
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    skf = StratifiedKFold(5, shuffle=True, random_state=seed)
    pred = np.empty_like(y)
    for tr, te in skf.split(X, y):
        m = make_pipeline(StandardScaler(), PCA(min(n_pca, len(tr) - 1), random_state=seed),
                          LogisticRegression(max_iter=2000, C=1.0))
        m.fit(X[tr], y[tr])
        pred[te] = m.predict(X[te])
    return float((pred == y).mean())


def onehot(cols):
    """cols: list of label arrays -> concatenated one-hot matrix."""
    mats = []
    for c in cols:
        vals = sorted(set(c))
        mats.append(np.array([[v == u for u in vals] for v in c], dtype=np.float32))
    return np.concatenate(mats, 1)


def ceiling_acc(cols, y):
    """Logistic regression from one-hot inputs (no PCA) — what a linear readout of the symbols can reach."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    X = onehot(cols)
    pred = cross_val_predict(LogisticRegression(max_iter=2000, C=10.0), X, y,
                             cv=StratifiedKFold(5, shuffle=True, random_state=0))
    return float((pred == y).mean())


def probe(conds):
    rng = np.random.default_rng(0)
    lines = []
    for cond in conds:
        meta = json.loads((ROOT / f"{cond}.meta.json").read_text())
        # ---- item level: answer letter
        R = np.load(ROOT / f"{cond}.item.npy", mmap_mode="r")
        y = np.array([m["answer"] for m in meta["items"]])
        maj = Counter(y).most_common(1)[0][1] / len(y)
        ceil = ceiling_acc([[m["cipher_q"] for m in meta["items"]], [m["shift"] for m in meta["items"]],
                            [m["pos"] for m in meta["items"]]], y)
        lines += [f"## {cond}: answer letter (26-way), n={len(y)}, majority {100 * maj:.0f}%, "
                  f"input-ceiling (one-hot cipher letter + shift + position) {100 * ceil:.0f}%", "",
                  "| position | " + " | ".join(f"L{l}" for l in LAYERS) + " | best | shuffled@best |", "|---|" + "---|" * (len(LAYERS) + 2)]
        for p, pname in enumerate(meta["pos_names"]):
            accs = [cv_acc(np.asarray(R[:, p, l, :], dtype=np.float32), y) for l in LAYERS]
            bl = LAYERS[int(np.argmax(accs))]
            sh = cv_acc(np.asarray(R[:, p, bl, :], dtype=np.float32), rng.permutation(y))
            lines.append(f"| {pname} | " + " | ".join(f"{100 * a:.0f}" for a in accs) + f" | {100 * max(accs):.0f} (L{bl}) | {100 * sh:.0f} |")
            print(lines[-1], flush=True)
        lines.append("")
        # ---- letter level: plaintext letter at cipher / arrow / plain tokens
        if meta["letters"]:
            RL = np.load(ROOT / f"{cond}.letter.npy", mmap_mode="r")
            yl = np.array([m["plain"] for m in meta["letters"]])
            majl = Counter(yl).most_common(1)[0][1] / len(yl)
            ceill = ceiling_acc([[m["cipher"] for m in meta["letters"]], [m["shift"] for m in meta["letters"]]], yl)
            lines += [f"## {cond}: plaintext letter per position (26-way), n={len(yl)} letters, majority {100 * majl:.0f}%, "
                      f"input-ceiling (one-hot cipher letter + shift) {100 * ceill:.0f}%", "",
                      "| token | " + " | ".join(f"L{l}" for l in LAYERS) + " | best | shuffled@best |", "|---|" + "---|" * (len(LAYERS) + 2)]
            for p, pname in enumerate(meta["letter_pos_names"]):
                accs = [cv_acc(np.asarray(RL[:, p, l, :], dtype=np.float32), yl) for l in LAYERS]
                bl = LAYERS[int(np.argmax(accs))]
                sh = cv_acc(np.asarray(RL[:, p, bl, :], dtype=np.float32), rng.permutation(yl))
                lines.append(f"| {pname} | " + " | ".join(f"{100 * a:.0f}" for a in accs) + f" | {100 * max(accs):.0f} (L{bl}) | {100 * sh:.0f} |")
                print(lines[-1], flush=True)
            lines.append("")
    out = "\n".join(lines) + "\n"
    (ROOT / "summary.md").write_text(out)
    print(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["extract", "probe"], required=True)
    ap.add_argument("--conds", default="sym,nl,filler,direct")
    ap.add_argument("--batch", type=int, default=32)
    args = ap.parse_args()
    conds = args.conds.split(",")
    if args.stage == "extract":
        extract(conds, args.batch)
    else:
        probe(conds)


if __name__ == "__main__":
    main()
