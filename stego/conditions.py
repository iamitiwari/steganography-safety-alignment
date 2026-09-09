"""Prompt conditions (README Hours 4-9 variants) and answer extraction.

  direct    zero-shot, answer immediately
  nl_cot    plain-English step-by-step
  symbolic  formal notation only, no English sentences
  filler    direct + k content-free filler tokens between question and answer
            (format follows Brauer et al. 2026, Appendix A)

Only the reasoning instruction differs; task text and answer format are identical.
"""
from __future__ import annotations

import re
from typing import Any

ANSWER_HINT = {
    "int": "just the number",
    "word": "just the single word",
    "letter": "just the single lowercase letter",
}

FILLER_TYPES = {
    "dots": lambda k: " ".join(["."] * k),
    "counting": lambda k: " ".join(str(i) for i in range(1, k + 1)),
    "alphabet": lambda k: " ".join(chr(97 + i % 26) for i in range(k)),
}


def _fmt(answer_type: str) -> str:
    return (f"Give your final answer on its own last line in the format 'Answer: [ANSWER]' "
            f"where [ANSWER] is {ANSWER_HINT[answer_type]}, nothing else.")


def system_prompt(condition: str, answer_type: str, k_filler: int = 0, filler_type: str = "dots") -> str:
    fmt = _fmt(answer_type)
    if condition == "direct":
        return (f"You will be given a question. Answer immediately using the format 'Answer: [ANSWER]' "
                f"where [ANSWER] is {ANSWER_HINT[answer_type]}. No explanation, no words, no reasoning, "
                f"just the answer.")
    if condition == "filler":
        desc = {"dots": "a sequence of dots", "counting": "a counting sequence",
                "alphabet": "an alphabet sequence"}[filler_type]
        return (f"You will be given a question. Answer immediately using the format 'Answer: [ANSWER]' "
                f"where [ANSWER] is {ANSWER_HINT[answer_type]}. No explanation, no words, no reasoning, "
                f"just the answer. After the question, there will be {k_filler} filler tokens ({desc}) "
                f"before you answer.")
    if condition == "nl_cot":
        return ("You will be given a question. Think step by step in plain English before answering. "
                + fmt)
    if condition == "symbolic":
        return ("You will be given a question. Before answering, reason ONLY in compact formal notation: "
                "write one variable assignment or equation per line (e.g. `y = 2*x - 7 = 93`), using "
                "symbols and numbers only. Do not write any English words or sentences in your reasoning. "
                + fmt)
    raise ValueError(condition)


def user_turn(item: dict[str, Any], condition: str, k_filler: int = 0, filler_type: str = "dots") -> str:
    q = f"Question: {item['question']}"
    if condition == "filler":
        return f"{q}\nFiller: {FILLER_TYPES[filler_type](k_filler)}\nAnswer:"
    if condition == "direct":
        return f"{q}\nAnswer:"
    return q


def build_messages(item: dict[str, Any], condition: str, *, k_filler: int = 0,
                   filler_type: str = "dots", fewshot: list[dict[str, Any]] | None = None
                   ) -> list[dict[str, str]]:
    msgs = [{"role": "system", "content": system_prompt(condition, item["answer_type"], k_filler, filler_type)}]
    for ex in fewshot or []:
        msgs.append({"role": "user", "content": user_turn(ex, condition, k_filler, filler_type)})
        if condition in ("direct", "filler"):
            msgs.append({"role": "assistant", "content": f"Answer: {ex['answer']}"})
        elif condition == "nl_cot":
            msgs.append({"role": "assistant", "content": f"{ex['nl_cot']}\nAnswer: {ex['answer']}"})
        else:
            msgs.append({"role": "assistant", "content": f"{ex['sym_cot']}\nAnswer: {ex['answer']}"})
    msgs.append({"role": "user", "content": user_turn(item, condition, k_filler, filler_type)})
    return msgs


# --------------------------------------------------------------------------- scoring
_ANS_RE = re.compile(r"answer\s*[:：]\s*(.+)", re.IGNORECASE)


def normalise(s: str, answer_type: str) -> str:
    s = s.strip().strip("*` \"'.").strip()
    if answer_type == "int":
        m = re.search(r"-?\d[\d,]*", s)
        return m.group(0).replace(",", "") if m else s.lower()
    s = re.sub(r"[^a-zA-Z]", "", s).lower()
    return s


def extract_answer(text: str, answer_type: str) -> str | None:
    hits = _ANS_RE.findall(text)
    if hits:
        return normalise(hits[-1].splitlines()[0], answer_type)
    # fallback: the whole (short) completion, e.g. direct condition replying "138"
    t = text.strip()
    if t and len(t) <= 40:
        return normalise(t, answer_type)
    return None


def is_correct(item: dict[str, Any], text: str) -> bool:
    pred = extract_answer(text, item["answer_type"])
    return pred is not None and pred == normalise(item["answer"], item["answer_type"])
