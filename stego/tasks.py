"""Synthetic reasoning tasks with named intermediates and counterfactual twins.

Five families, 40 items each (200 total), fully seeded and programmatically verified:

  syseq   system of nonsense-variable linear equations (carry-forward of Brauer et al. 2026)
  chain   3-step arithmetic chain
  logic   parity (lamp toggling) and order (4 runners, chained before/after clues)
  cipher  Caesar-shifted word (shift 1-3) -> Nth/last letter, or its alphabet index, of the plaintext
  symop   ad-hoc symbolic operators, nested evaluation

Every item carries:
  intermediates   ordered [{name, value}] -- targets for logit-lens / probes / corruption
  nl_cot          canonical plain-English reasoning (for prefilled-CoT corruption)
  sym_cot         canonical symbolic reasoning (same content, formal notation)
  counterfactual  twin item that differs in exactly one intermediate (matched-pair patching)

Usage:  python -m stego.tasks --out data/tasks_v1.jsonl --seed 0 --per-family 40
"""
from __future__ import annotations

import argparse
import json
import random
import string
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- helpers
ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth"}
NUMWORDS = {2: "two", 3: "three"}
PEOPLE = ["Alice", "Bob", "Carol", "Dave", "Erin", "Frank", "Grace", "Heidi",
          "Ivan", "Judy", "Mallory", "Oscar", "Peggy", "Rupert", "Sybil", "Trent",
          "Victor", "Wendy"]
VOWELS = set("aeiou")
# Common 4-6 letter words; no duplicates; chosen so plaintexts are unambiguous English.
WORDS = [
    "apple", "bread", "chair", "dance", "eagle", "flame", "grape", "house", "juice", "knife",
    "lemon", "money", "night", "ocean", "piano", "queen", "river", "stone", "table", "under",
    "voice", "water", "youth", "zebra", "brick", "cloud", "dream", "field", "glass", "heart",
    "light", "mouse", "north", "paint", "plant", "smile", "storm", "train", "wheel", "world",
    "candle", "forest", "garden", "island", "jungle", "letter", "market", "orange", "planet",
    "rocket", "silver", "summer", "tunnel", "window", "yellow", "bridge", "castle", "desert",
    "engine", "flower", "ladder", "monkey", "pencil", "spider", "ticket", "camp", "door",
    "fish", "gold", "hand", "iron", "king", "lamp", "milk", "nest", "pearl", "road", "ship",
]
SYMBOLS = ["⊕", "⊗", "⊙", "◇", "▽", "★", "§", "¤", "†", "‡"]
OPS = [  # (definition text with x,y ; python fn)
    ("x + y", lambda a, b: a + b),
    ("2x - y", lambda a, b: 2 * a - b),
    ("x + 2y", lambda a, b: a + 2 * b),
    ("2x + y", lambda a, b: 2 * a + b),
    ("3x - y", lambda a, b: 3 * a - b),
    ("x * y", lambda a, b: a * b),
    ("x * y - x", lambda a, b: a * b - a),
    ("2x + 2y", lambda a, b: 2 * a + 2 * b),
]


def _cvc(rng: random.Random, used: set[str]) -> str:
    cons = "bcdfghjklmnprstvwz"
    vow = "aeiou"
    while True:
        w = rng.choice(cons) + rng.choice(vow) + rng.choice(cons)
        if w not in used:
            used.add(w)
            return w


def _item(family: str, subtype: str, idx: int, question: str, answer: Any, answer_type: str,
          intermediates: list[tuple[str, Any]], nl_cot: str, sym_cot: str, params: dict,
          cf: dict) -> dict[str, Any]:
    return {
        "id": f"{family}_{subtype}_{idx:03d}" if subtype else f"{family}_{idx:03d}",
        "family": family,
        "subtype": subtype or family,
        "question": question,
        "answer": str(answer),
        "answer_type": answer_type,
        "intermediates": [{"name": n, "value": str(v)} for n, v in intermediates],
        "nl_cot": nl_cot,
        "sym_cot": sym_cot,
        "params": params,
        "counterfactual": cf,
    }


# --------------------------------------------------------------------------- syseq
def _syseq_instance(rng: random.Random, names: list[str], lit1: int, x: int,
                    c0: int, s0: int, k0: int, c1: int, s1: int, k1: int,
                    c3: int, s3: int, k3: int, c2: int, s2: int, k2: int) -> dict | None:
    n1, n2, n3, n4, n5 = names
    d = c0 * lit1 + s0 * k0
    c1x = c1 * x
    y = c1x + s1 * k1
    down = c3 * y + s3 * k3
    c2y = c2 * y
    ans = c2y + s2 * k2
    if min(d, y, down, ans, c1x - 0) <= 0:
        return None
    sign = {1: "plus", -1: "minus"}
    lines = [
        f"{n1} = {lit1}",
        f"{n2} = {x}",
        f"{n3} = {NUMWORDS[c0]} times the number for {n1} {sign[s0]} {k0}",
        f"{n4} = {NUMWORDS[c1]} times the number for {n2} {sign[s1]} {k1}",
        f"{n5} = {NUMWORDS[c3]} times the number for {n4} {sign[s3]} {k3}",
    ]
    q = "\n".join(lines) + f"\nQuestion: What is {NUMWORDS[c2]} times the number for {n4} {sign[s2]} {k2}?"
    nl = (f"The question asks about {n4}. {n4} is {NUMWORDS[c1]} times {n2} {sign[s1]} {k1}. "
          f"{n2} is {x}, so {NUMWORDS[c1]} times {x} is {c1x}, and {c1x} {sign[s1]} {k1} is {y}. "
          f"So {n4} = {y}. Then {NUMWORDS[c2]} times {y} is {c2y}, and {c2y} {sign[s2]} {k2} is {ans}.")
    op1 = "+" if s1 > 0 else "-"
    op2 = "+" if s2 > 0 else "-"
    sym = (f"{n2} = {x}\n{n4} = {c1}*{n2} {op1} {k1} = {c1x} {op1} {k1} = {y}\n"
           f"ans = {c2}*{n4} {op2} {k2} = {c2y} {op2} {k2} = {ans}")
    return {"question": q, "answer": ans,
            "intermediates": [("x", x), ("c1x", c1x), ("y", y), ("c2y", c2y)],
            "nl_cot": nl, "sym_cot": sym,
            "params": {"names": names, "lit1": lit1, "x": x, "c0": c0, "s0": s0, "k0": k0,
                       "c1": c1, "s1": s1, "k1": k1, "c3": c3, "s3": s3, "k3": k3,
                       "c2": c2, "s2": s2, "k2": k2, "distractor": d, "downstream": down}}


def gen_syseq(rng: random.Random, n: int) -> list[dict]:
    out, seen = [], set()
    while len(out) < n:
        used: set[str] = set()
        names = [_cvc(rng, used) for _ in range(5)]
        args = dict(lit1=rng.randint(10, 99), x=rng.randint(10, 99),
                    c0=rng.choice([2, 3]), s0=rng.choice([1, -1]), k0=rng.randint(1, 30),
                    c1=rng.choice([2, 3]), s1=rng.choice([1, -1]), k1=rng.randint(1, 30),
                    c3=rng.choice([2, 3]), s3=rng.choice([1, -1]), k3=rng.randint(1, 30),
                    c2=rng.choice([2, 3]), s2=rng.choice([1, -1]), k2=rng.randint(1, 30))
        inst = _syseq_instance(rng, names, **args)
        if inst is None or inst["question"] in seen:
            continue
        # counterfactual: same arithmetic, different x (hence different y and answer)
        cf = None
        for _ in range(50):
            x2 = rng.randint(10, 99)
            if x2 == args["x"]:
                continue
            cfi = _syseq_instance(rng, names, **{**args, "x": x2})
            if cfi is not None and cfi["answer"] != inst["answer"]:
                cf = cfi
                break
        if cf is None:
            continue
        seen.add(inst["question"])
        out.append(_item("syseq", "", len(out), inst["question"], inst["answer"], "int",
                         inst["intermediates"], inst["nl_cot"], inst["sym_cot"], inst["params"],
                         {"changed": "x", "question": cf["question"], "answer": str(cf["answer"]),
                          "intermediates": [{"name": a, "value": str(b)} for a, b in cf["intermediates"]]}))
    return out


# --------------------------------------------------------------------------- chain
def _chain_instance(N: int, a: int, b: int, c: int) -> dict:
    s1 = N + a
    s2 = s1 * b
    s3 = s2 - c
    q = (f"Start with {N}. Add {a}. Multiply the result by {b}. Subtract {c}. "
         f"What is the final number?")
    nl = (f"Start with {N}. Adding {a} gives {s1}. Multiplying {s1} by {b} gives {s2}. "
          f"Subtracting {c} from {s2} gives {s3}.")
    sym = f"s1 = {N} + {a} = {s1}\ns2 = {s1} * {b} = {s2}\nans = {s2} - {c} = {s3}"
    return {"question": q, "answer": s3, "intermediates": [("s1", s1), ("s2", s2)],
            "nl_cot": nl, "sym_cot": sym, "params": {"N": N, "a": a, "b": b, "c": c}}


def gen_chain(rng: random.Random, n: int) -> list[dict]:
    out, seen = [], set()
    while len(out) < n:
        N, a, b, c = rng.randint(10, 60), rng.randint(5, 40), rng.choice([2, 3]), rng.randint(5, 50)
        inst = _chain_instance(N, a, b, c)
        if inst["answer"] <= 0 or inst["question"] in seen:
            continue
        N2 = rng.randint(10, 60)
        while N2 == N:
            N2 = rng.randint(10, 60)
        cf = _chain_instance(N2, a, b, c)
        if cf["answer"] <= 0:
            continue
        seen.add(inst["question"])
        out.append(_item("chain", "", len(out), inst["question"], inst["answer"], "int",
                         inst["intermediates"], inst["nl_cot"], inst["sym_cot"], inst["params"],
                         {"changed": "N", "question": cf["question"], "answer": str(cf["answer"]),
                          "intermediates": [{"name": a_, "value": str(b_)} for a_, b_ in cf["intermediates"]]}))
    return out


# --------------------------------------------------------------------------- logic: parity
def _parity_instance(start: str, people: list[str], counts: list[int]) -> dict:
    total = sum(counts)
    par = "even" if total % 2 == 0 else "odd"
    final = start if par == "even" else ("on" if start == "off" else "off")
    clauses = ", ".join(f"{p} presses the switch {c} time{'s' if c != 1 else ''}"
                        for p, c in zip(people, counts))
    q = (f"A lamp is {start}. Each press of its switch toggles it. In turn, {clauses}. "
         f"After all the presses, is the lamp on or off?")
    nl = (f"The total number of presses is {' + '.join(map(str, counts))} = {total}. "
          f"{total} is {par}, so the lamp ends {'in the same state it started' if par == 'even' else 'in the opposite state'}. "
          f"It started {start}, so it is now {final}.")
    sym = (f"total = {' + '.join(map(str, counts))} = {total}\nparity = {total} mod 2 = {total % 2}\n"
           f"state = {start} xor {total % 2} = {final}")
    return {"question": q, "answer": final, "intermediates": [("total", total), ("parity", par)],
            "nl_cot": nl, "sym_cot": sym, "params": {"start": start, "people": people, "counts": counts}}


def gen_parity(rng: random.Random, n: int) -> list[dict]:
    out, seen = [], set()
    while len(out) < n:
        k = rng.choice([3, 4])
        people = rng.sample(PEOPLE, k)
        counts = [rng.randint(1, 9) for _ in range(k)]
        start = rng.choice(["on", "off"])
        inst = _parity_instance(start, people, counts)
        if inst["question"] in seen:
            continue
        j = rng.randrange(k)
        cf_counts = list(counts)
        cf_counts[j] += 1 if cf_counts[j] < 9 else -1
        cf = _parity_instance(start, people, cf_counts)
        assert cf["answer"] != inst["answer"]
        seen.add(inst["question"])
        out.append(_item("logic", "parity", len(out), inst["question"], inst["answer"], "word",
                         inst["intermediates"], inst["nl_cot"], inst["sym_cot"], inst["params"],
                         {"changed": f"count[{j}]", "question": cf["question"], "answer": cf["answer"],
                          "intermediates": [{"name": a_, "value": str(b_)} for a_, b_ in cf["intermediates"]]}))
    return out


# --------------------------------------------------------------------------- logic: order
def _order_instance(rng: random.Random, order: list[str], pos: int, clue_forms: list[int],
                    clue_perm: list[int]) -> dict:
    # chain clues (order[i] before order[i+1]); clue_forms[i] chooses phrasing.
    clues = []
    for i in range(3):
        a, b = order[i], order[i + 1]
        clues.append(f"{a} finished before {b}" if clue_forms[i] == 0 else f"{b} finished after {a}")
    clues = [clues[i] for i in clue_perm]
    q = (f"Four runners finished a race: {', '.join(sorted(order))}. "
         f"{'. '.join(clues)}. Who finished {ORDINALS[pos]}?")
    ans = order[pos - 1]
    nl = (f"From the clues, the finishing order from first to last is "
          f"{', '.join(order)}. So the {ORDINALS[pos]} finisher is {ans}.")
    sym = f"order = {' < '.join(order)}\nans = order[{pos}] = {ans}"
    return {"question": q, "answer": ans, "intermediates": [("order", " ".join(order))],
            "nl_cot": nl, "sym_cot": sym,
            "params": {"order": order, "pos": pos, "clue_forms": clue_forms, "clue_perm": clue_perm}}


def gen_order(rng: random.Random, n: int) -> list[dict]:
    out, seen = [], set()
    while len(out) < n:
        order = rng.sample(PEOPLE, 4)
        pos = rng.randint(1, 4)
        forms = [rng.randint(0, 1) for _ in range(3)]
        perm = list(range(3))
        rng.shuffle(perm)
        inst = _order_instance(rng, order, pos, forms, perm)
        if inst["question"] in seen:
            continue
        # counterfactual: swap the queried position with a neighbour -> answer changes
        j = pos - 1
        k = j + 1 if j < 3 else j - 1
        cf_order = list(order)
        cf_order[j], cf_order[k] = cf_order[k], cf_order[j]
        cf = _order_instance(rng, cf_order, pos, forms, perm)
        assert cf["answer"] != inst["answer"]
        seen.add(inst["question"])
        out.append(_item("logic", "order", len(out), inst["question"], inst["answer"], "word",
                         inst["intermediates"], inst["nl_cot"], inst["sym_cot"], inst["params"],
                         {"changed": f"swap[{j},{k}]", "question": cf["question"], "answer": cf["answer"],
                          "intermediates": [{"name": a_, "value": str(b_)} for a_, b_ in cf["intermediates"]]}))
    return out


# --------------------------------------------------------------------------- cipher
def _caesar(word: str, k: int) -> str:
    return "".join(chr((ord(ch) - 97 + k) % 26 + 97) for ch in word)


def _cipher_instance(word: str, k: int, subtype: str, pos: int | None) -> dict:
    enc = _caesar(word, k).upper()
    base = (f"The string {enc} was produced by shifting every letter of an English word forward "
            f"by {k} position{'s' if k != 1 else ''} in the alphabet (wrapping around from Z to A). ")
    per_letter = ", ".join(f"{e}->{p}" for e, p in zip(enc, word))
    if subtype == "letter":
        which = "last" if pos == len(word) else ORDINALS[pos]
        ans = word[pos - 1]
        q = base + f"What is the {which} letter of the original word? Answer with a single lowercase letter."
        nl = (f"Shifting each letter back by {k}: {per_letter}. The original word is '{word}'. "
              f"Its {which} letter is '{ans}'.")
        sym = f"shift = -{k}\nword = {per_letter} = {word}\nans = word[{pos}] = {ans}"
        atype = "letter"
        inter = [("plaintext", word)]
    else:  # alphapos: alphabet index (a=1..z=26) of the Nth/last letter of the plaintext
        which = "last" if pos == len(word) else ORDINALS[pos]
        letter = word[pos - 1]
        ans = ord(letter) - 96
        q = base + (f"What is the position in the alphabet (a = 1, b = 2, ..., z = 26) of the "
                    f"{which} letter of the original word?")
        nl = (f"Shifting each letter back by {k}: {per_letter}. The original word is '{word}'. "
              f"Its {which} letter is '{letter}', which is letter number {ans} of the alphabet.")
        sym = f"shift = -{k}\nword = {per_letter} = {word}\nletter = word[{pos}] = {letter}\nans = idx({letter}) = {ans}"
        atype = "int"
        inter = [("plaintext", word), ("letter", letter)]
    return {"question": q, "answer": ans, "answer_type": atype,
            "intermediates": inter, "nl_cot": nl, "sym_cot": sym,
            "params": {"word": word, "shift": k, "ciphertext": enc, "pos": pos}}


def gen_cipher(rng: random.Random, n: int, subtype: str, words_pool: list[str]) -> list[dict]:
    out = []
    while len(out) < n:
        word = words_pool.pop()
        k = rng.randint(1, 3)   # shifts >3 were unreliable for Qwen2.5-7B even with CoT (smoke v0)
        pos = rng.choice([2, 3, len(word)])
        inst = _cipher_instance(word, k, subtype, pos)
        # counterfactual: different word, same shift and length, different answer
        cands = [w for w in words_pool if len(w) == len(word)
                 and _cipher_instance(w, k, subtype, pos)["answer"] != inst["answer"]]
        if not cands:
            words_pool.insert(0, word)
            rng.shuffle(words_pool)
            continue
        w2 = rng.choice(cands)  # NOTE: twin word stays in pool; twins are not primary items
        cf = _cipher_instance(w2, k, subtype, pos)
        out.append(_item("cipher", subtype, len(out), inst["question"], inst["answer"],
                         inst["answer_type"], inst["intermediates"], inst["nl_cot"], inst["sym_cot"],
                         inst["params"],
                         {"changed": "plaintext", "question": cf["question"], "answer": str(cf["answer"]),
                          "intermediates": [{"name": a_, "value": str(b_)} for a_, b_ in cf["intermediates"]]}))
    return out


# --------------------------------------------------------------------------- symop
def _symop_instance(s1: str, s2: str, o1: int, o2: int, a: int, b: int, c: int, form: int) -> dict | None:
    d1, f1 = OPS[o1]
    d2, f2 = OPS[o2]
    if form == 0:      # (a s1 b) s2 c
        m = f1(a, b)
        ans = f2(m, c)
        expr = f"({a} {s1} {b}) {s2} {c}"
        inner = f"{a} {s1} {b}"
        outer_nl = f"{m} {s2} {c}"
    else:              # a s2 (b s1 c)
        m = f1(b, c)
        ans = f2(a, m)
        expr = f"{a} {s2} ({b} {s1} {c})"
        inner = f"{b} {s1} {c}"
        outer_nl = f"{a} {s2} {m}"
    if m <= 0 or ans <= 0:
        return None
    q = (f"Define two operators on numbers: x {s1} y = {d1}, and x {s2} y = {d2}. "
         f"Compute {expr}.")
    nl = (f"First evaluate the bracket: {inner}. Using x {s1} y = {d1}, that is {m}. "
          f"Then evaluate {outer_nl}. Using x {s2} y = {d2}, that is {ans}.")
    sym = f"m = {inner} = {m}\nans = {outer_nl} = {ans}"
    return {"question": q, "answer": ans, "intermediates": [("m", m)], "nl_cot": nl, "sym_cot": sym,
            "params": {"sym1": s1, "sym2": s2, "def1": d1, "def2": d2, "a": a, "b": b, "c": c,
                       "form": form, "expr": expr}}


def gen_symop(rng: random.Random, n: int) -> list[dict]:
    out, seen = [], set()
    while len(out) < n:
        s1, s2 = rng.sample(SYMBOLS, 2)
        o1, o2 = rng.sample(range(len(OPS)), 2)
        a, b, c = (rng.randint(2, 12) for _ in range(3))
        form = rng.randint(0, 1)
        inst = _symop_instance(s1, s2, o1, o2, a, b, c, form)
        if inst is None or inst["question"] in seen:
            continue
        # counterfactual: change one operand inside the bracket -> m and answer change
        cf = None
        for _ in range(50):
            if form == 0:
                a2 = rng.randint(2, 12)
                if a2 == a:
                    continue
                cfi = _symop_instance(s1, s2, o1, o2, a2, b, c, form)
            else:
                b2 = rng.randint(2, 12)
                if b2 == b:
                    continue
                cfi = _symop_instance(s1, s2, o1, o2, a, b2, c, form)
            if cfi is not None and cfi["answer"] != inst["answer"] and \
                    cfi["intermediates"][0][1] != inst["intermediates"][0][1]:
                cf = cfi
                break
        if cf is None:
            continue
        seen.add(inst["question"])
        out.append(_item("symop", "", len(out), inst["question"], inst["answer"], "int",
                         inst["intermediates"], inst["nl_cot"], inst["sym_cot"], inst["params"],
                         {"changed": "inner operand", "question": cf["question"], "answer": str(cf["answer"]),
                          "intermediates": [{"name": a_, "value": str(b_)} for a_, b_ in cf["intermediates"]]}))
    return out


# --------------------------------------------------------------------------- build
def build(seed: int = 0, per_family: int = 40) -> list[dict]:
    # One RNG per family so retuning one family never reshuffles the others (keeps LLM cache hits).
    R = lambda name: random.Random(f"{seed}-{name}")  # noqa: E731
    half = per_family // 2
    crng = R("cipher")
    pool = list(WORDS)
    crng.shuffle(pool)
    items = (gen_syseq(R("syseq"), per_family) + gen_chain(R("chain"), per_family)
             + gen_parity(R("parity"), half) + gen_order(R("order"), per_family - half)
             + gen_cipher(crng, half, "letter", pool) + gen_cipher(crng, per_family - half, "alphapos", pool)
             + gen_symop(R("symop"), per_family))
    # invariants
    ids = [it["id"] for it in items]
    assert len(ids) == len(set(ids)), "duplicate ids"
    qs = [it["question"] for it in items]
    assert len(qs) == len(set(qs)), "duplicate questions"
    for it in items:
        assert it["counterfactual"]["answer"] != it["answer"], it["id"]
        assert it["counterfactual"]["question"] != it["question"], it["id"]
        if it["answer_type"] == "int":
            assert int(it["answer"]) > 0, it["id"]
        for iv in it["intermediates"]:
            assert iv["value"] != "", it["id"]
    cipher_words = [it["params"]["word"] for it in items if it["family"] == "cipher"]
    assert len(cipher_words) == len(set(cipher_words)), "cipher plaintext reused"
    return items


def load(path: str | Path) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/tasks_v1.jsonl")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--per-family", type=int, default=40)
    ap.add_argument("--show", type=int, default=2, help="examples per family to print")
    args = ap.parse_args()
    items = build(args.seed, args.per_family)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"wrote {len(items)} items to {args.out}")
    print("per subtype:", dict(Counter(it["subtype"] for it in items)))
    shown: dict[str, int] = {}
    for it in items:
        if shown.get(it["subtype"], 0) >= args.show:
            continue
        shown[it["subtype"]] = shown.get(it["subtype"], 0) + 1
        print(f"\n--- {it['id']}  answer={it['answer']}  intermediates={it['intermediates']}")
        print(it["question"])
        print("[nl_cot]", it["nl_cot"])
        print("[sym_cot]", it["sym_cot"].replace("\n", " | "))
        print("[cf]", it["counterfactual"]["changed"], "->", it["counterfactual"]["answer"])


if __name__ == "__main__":
    main()
