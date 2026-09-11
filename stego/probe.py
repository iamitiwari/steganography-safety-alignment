"""Hours 10-15: linear probes on saved residuals, with controls.

For each (target intermediate, position, layer): ridge regression from the residual (D=3584) to the
target's numeric value, 5-fold cross-validated R^2, after StandardScaler + PCA(n_pca) fitted on the
training fold only.  Controls:
  shuffled   same probe on permuted labels          (should be ~0)
  random64   residual projected onto n_pca fixed random directions instead of PCA (README's
             random-direction baseline)
Targets: every intermediate and the answer. In syseq, `x` is literally in the prompt; `c1x`, `y`,
`c2y`, `ans` are computed and never appear in a filler/direct prompt, so decodability of those at
dot positions is "computed but never read out".

Usage:
  python -m stego.probe --cond filler --family syseq [--layers 0,4,8,...] [--positions q_last,dot_0,...]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.model_selection import cross_val_predict
from sklearn.preprocessing import PolynomialFeatures
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler

ALPHAS = np.logspace(0, 5, 11)
# literal numbers present in the prompt, per family (from item["params"], stored as q_<name> in meta labels)
INPUTS = {"syseq": ["lit1", "x", "c0", "s0", "k0", "c1", "s1", "k1", "c3", "s3", "k3", "c2", "s2", "k2"],
          "chain": ["N", "a", "b", "c"]}


def r2(y, pred):
    return 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()


def probe_block(X, Xr, ys: dict[str, np.ndarray], n_pca: int, seed=0):
    """One (position, layer). Returns {name: (r2, r2_shuffled, r2_random)} for every target in ys.
    Scaler+PCA fitted once per fold and shared across targets/controls."""
    kf = KFold(5, shuffle=True, random_state=seed)
    rng = np.random.default_rng(seed)
    shuf = {t: rng.permutation(y) for t, y in ys.items()}
    P = {t: np.zeros(len(ys[t])) for t in ys}
    S = {t: np.zeros(len(ys[t])) for t in ys}
    Q = {t: np.zeros(len(ys[t])) for t in ys}
    for tr, te in kf.split(X):
        sc = StandardScaler().fit(X[tr]); pca = PCA(n_pca, random_state=seed).fit(sc.transform(X[tr]))
        Ztr, Zte = pca.transform(sc.transform(X[tr])), pca.transform(sc.transform(X[te]))
        scr = StandardScaler().fit(Xr[tr]); Rtr, Rte = scr.transform(Xr[tr]), scr.transform(Xr[te])
        for t, y in ys.items():
            P[t][te] = RidgeCV(alphas=ALPHAS).fit(Ztr, y[tr]).predict(Zte)
            S[t][te] = RidgeCV(alphas=ALPHAS).fit(Ztr, shuf[t][tr]).predict(Zte)
            Q[t][te] = RidgeCV(alphas=ALPHAS).fit(Rtr, y[tr]).predict(Rte)
    return {t: (r2(ys[t], P[t]), r2(shuf[t], S[t]), r2(ys[t], Q[t])) for t in ys}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cond", default="filler")
    ap.add_argument("--family", default="syseq")
    ap.add_argument("--root", default="results/probe")
    ap.add_argument("--layers", default="0,2,4,6,8,10,12,14,16,18,20,22,24,26,28")
    ap.add_argument("--positions", default="", help="comma list; default = non-dot positions + dots at stride 6 + last dot")
    ap.add_argument("--targets", default="")
    ap.add_argument("--n_pca", type=int, default=64)
    args = ap.parse_args()

    d = Path(args.root) / args.cond
    meta = json.loads((d / f"{args.family}.meta.json").read_text())
    resid = np.load(d / f"{args.family}.resid.npy", mmap_mode="r")
    N, Pn, L1, D = resid.shape
    names, labels = meta["pos_names"], meta["labels"]
    targets = args.targets.split(",") if args.targets else [k for k in labels[0] if not k.startswith("q_")]
    layers = [int(x) for x in args.layers.split(",")]
    if args.positions:
        positions = args.positions.split(",")
    else:
        dots = [n for n in names if n.startswith("dot_")]
        keep = set(n for n in names if not n.startswith("dot_")) | set(dots[::6]) | ({dots[-1]} if dots else set())
        positions = [n for n in names if n in keep]
    ys = {t: np.array([float(lab[t]) for lab in labels]) for t in targets}
    # --- input-only ceilings and nonlinear-residual targets -------------------------------------
    U = np.array([[float(lab[f"q_{k}"]) for k in INPUTS[args.family]] for lab in labels])
    U2 = PolynomialFeatures(2, include_bias=False).fit_transform(U)
    ceil = {}
    for t in list(targets):
        lin = cross_val_predict(LinearRegression(), U, ys[t], cv=KFold(5, shuffle=True, random_state=0))
        poly = cross_val_predict(LinearRegression(), U2, ys[t], cv=KFold(5, shuffle=True, random_state=0))
        ceil[t] = (r2(ys[t], lin), r2(ys[t], poly))
        ys[f"{t}~nonlin"] = ys[t] - LinearRegression().fit(U, ys[t]).predict(U)   # what a linear readout of inputs cannot give
    print("input-only ceilings (CV R^2 from the prompt's literal numbers): " +
          ", ".join(f"{t}: linear {a:.2f} / degree-2 {b:.2f}" for t, (a, b) in ceil.items()), flush=True)
    R = np.random.default_rng(0).standard_normal((D, args.n_pca)).astype(np.float32) / np.sqrt(D)

    rows, t0 = [], time.time()
    for pname in positions:
        p = names.index(pname)
        for l in layers:
            X = np.asarray(resid[:, p, l, :], dtype=np.float32)
            res = probe_block(X, X @ R, ys, args.n_pca)
            for t, (a, b, c) in res.items():
                rows.append((t, pname, l, a, b, c))
        print(f"  {pname} done ({time.time() - t0:.0f}s)", flush=True)

    out = d / f"{args.family}.probe.csv"
    with open(out, "w") as f:
        f.write("target,position,layer,r2,r2_shuffled,r2_random\n")
        for r in rows:
            f.write(",".join(map(str, r)) + "\n")

    print(f"\nridge probes {args.cond}/{args.family}: n={N}, PCA-{args.n_pca}, 5-fold CV R^2; best layer per (target, position)")
    print("R2 = probe on the raw value; nonlin = probe on the value minus its linear-from-inputs fit (same layer);")
    print("input ceilings: " + ", ".join(f"{t} lin {a:.2f}/poly2 {b:.2f}" for t, (a, b) in ceil.items()))
    print("| target | position | best layer | R2 | shuffled | random | nonlin R2 | nonlin shuffled |")
    print("|---|---|---|---|---|---|---|---|")
    for t in targets:
        for pname in positions:
            best = max((r for r in rows if r[0] == t and r[1] == pname), key=lambda r: r[3])
            nl = next(r for r in rows if r[0] == f"{t}~nonlin" and r[1] == pname and r[2] == best[2])
            print(f"| {t} | {pname} | {best[2]} | {best[3]:.2f} | {best[4]:.2f} | {best[5]:.2f} | {nl[3]:.2f} | {nl[4]:.2f} |")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
