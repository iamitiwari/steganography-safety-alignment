# Hours 4–9: four conditions, filler sweep, causal step corruption

Model: Qwen2.5-7B-Instruct, **bf16 safetensors served by vLLM 0.29 on one A100-80GB** (see §0).
All runs temperature 0, label `qwen2.5-7b-instruct-bf16`. Every completion is cached in
`results/cache` keyed by (label, messages, sampling), so nothing here mixes with the Hours 0–3 Q8 CPU runs.

## 0. Setup change: CPU → GPU

The box gained two A100-80GB cards on 2026-09-10. Generation now goes through vLLM on GPU 0; GPU 1 is
reserved for HF-transformers probing (Hours 10–15). Launch (the sampler flag is required because there
is no nvcc on the box and FlashInfer's sampler JIT-compiles):

```
CUDA_VISIBLE_DEVICES=0 VLLM_USE_FLASHINFER_SAMPLER=0 vllm serve /home/amit/models/hf/Qwen2.5-7B-Instruct \
  --port 8091 --dtype bfloat16 --served-model-name local --max-model-len 8192 --max-num-seqs 256
```

The full 400-completion smoke sweep takes 7–9 s (128 workers) instead of 21 min. bf16 ≠ Q8, so the
baseline was redone (`results/smoke_qwen2.5-7b-bf16`):

| subtype | direct Q8 → bf16 | nl_cot Q8 → bf16 |
|---|---|---|
| syseq | 0 → 0 | 98 → 100 |
| chain | 0 → 2 | 100 → 100 |
| symop | 0 → 0 | 100 → 100 |
| parity | 60 → 35 | 80 → 95 |
| order | 50 → 55 | 90 → **60** |
| letter | 20 → 20 | 90 → 80 |
| alphapos | 15 → 15 | 95 → 85 |
| ALL | 14 → 13 | 95 → 92 |

`order` drops below the 80% bar under bf16, but 5/8 misses state the correct full order and then read
the wrong ordinal (the readout failure already seen in Hours 0–3). Not a task problem; kept.

Confirmed premise for everything below: **the tasks need CoT.** `direct` is at floor (0–20%) for
syseq, chain, symop and cipher. Parity and order are the exception (direct 35–55%, i.e. chance for a
2-way / above chance for a 4-way answer), so treat them as weaker evidence.

## 1. All four conditions, zero-shot (`results/cond4_qwen2.5-7b-bf16`)

| subtype | n | direct | nl_cot | symbolic | filler (25 dots) |
|---|---|---|---|---|---|
| syseq | 40 | 0% | 100% | 50% | 0% |
| chain | 40 | 2% | 100% | 65% | 0% |
| symop | 40 | 0% | 100% | 62% | 0% |
| parity | 20 | 35% | 95% | 60% | 30% |
| order | 20 | 55% | 60% | 30% | 45% |
| letter | 20 | 20% | 80% | 5% | 10% |
| alphapos | 20 | 15% | 85% | 25% | 15% |
| **ALL** | 200 | 13% | 92% | **48%** | **10%** |

- **Symbolic compliance is perfect**: 0 of 983 reasoning lines contain three consecutive English
  words. The 48% is a real capability drop, not the model ignoring the instruction.
- Symbolic failure modes (hand-read): unevaluated expressions (`x = 12 + 19 / y = x * 3 / z = y - 12 /
  Answer: 63`), wrong variable picked in syseq, cipher handled as `ord()`/`chr()` pseudo-code without
  evaluating it, order clues written as inequalities and then mis-read. The scratchpad shows the *plan*
  but often not the *values*, which is exactly the legibility problem the README is about.
- **Filler = direct.** Completions are ≤7 tokens; 110/200 filler answers are byte-identical to the
  direct answers.

## 2. Few-shot (3 same-subtype demonstrations; `results/cond4_fs3_k25_qwen2.5-7b-instruct-bf16`)

`stego/smoke.py --fewshot 3` now prepends 3 other items of the same subtype with their canonical
answer / `nl_cot` / `sym_cot` / filler-formatted turn, following the paper's Appendix A format.

| subtype | direct | nl_cot | symbolic | filler (25) |
|---|---|---|---|---|
| syseq | 0% | 100% | 95% | 0% |
| chain | 2% | 100% | 100% | 0% |
| symop | 2% | 85% | 30% | 2% |
| parity | 65% | 100% | 100% | 65% |
| order | 50% | 90% | 65% | 45% |
| letter | 15% | 90% | 95% | 10% |
| alphapos | 15% | 85% | 100% | 15% |
| **ALL** | 16% | 94% | **81%** | 14% |

- Symbolic recovers from 48% to 81%: the zero-shot gap was mostly the model not knowing what notation
  to use. Chain/syseq/cipher/parity are now at parity with English.
- **symop is the exception and it is a dataset artefact**: `tasks.py` reuses the same 10 operator
  glyphs across items with different definitions, so same-subtype demos show `⊕` meaning something
  else. That interferes (symbolic 30%, and nl_cot *drops* 100 → 85 with demos). Fix before Hours 10–15:
  draw symop demos from other families, or give each item unique glyphs.

## 3. Filler sweep: a clean null (`results/filler_*`)

| k dots | few-shot | direct | filler |
|---|---|---|---|
| 25 | 0 | 13% | 10% |
| 100 | 0 | 13% | 12% |
| 25 | 3 | 16% | 14% |
| 100 | 3 | 16% | 16% |

No uplift at any setting, per subtype or overall. This is README idea #1 answered for a 7B dense model:
**no behavioural filler effect**, consistent with the paper's report that the effect is not universal.
The sharper question for Hours 10–15 is whether intermediates are nevertheless *encoded* at filler
positions (computed but never read out).

### 3b. Does our filler match the paper's? Yes — checked against their released code

`stego/conditions.py` was written from the paper's Appendix A, and I re-checked it against the cloned
repo (`/home/amit/filler-token-reasoning`: `scripts/prompt_utils.py`,
`scripts/data/generate_1hop_dataset.py`, `scripts/data/generate_varbind_dataset.py`). Both put the
filler **in the user turn, after the question and before `Answer:`**, with a system prompt that says
answer immediately and announces the filler; the no-filler baseline drops the `Filler:` line entirely
(= our `direct`). Remaining cosmetic differences: they use 5 fixed held-out few-shot examples (we
rotate 5 same-subtype items), blank lines around `Filler:`, bare-number assistant turns, and their
system prompt does not state the count ("some filler tokens … to give you extra space to process the
problem"). Their models are DeepSeek V3 (671B MoE) and Kimi K2 (1T MoE), 4-bit.

Paper-matched sweep on our 200 items: 5-shot, three filler types, five lengths
(`results/fillersweep/fs5_<type>_k<k>/`). Direct (5-shot) is 15% in every row.

| k | dots | counting | alphabet |
|---|---|---|---|
| 10 | 14% | 14% | 14% |
| 25 | 14% | 15% | 14% |
| 50 | 16% | 16% | 16% |
| 100 | 16% | 19% | 17% |
| 250 | 16% | 16% | 18% |

Per-item McNemar vs direct: no condition significant. Best is counting_100 (13 wrong→right vs 5
right→wrong, p = 0.10), then alphabet_250 (11 vs 4, p = 0.12); the flipping items differ across
conditions. Chain's 12% at long fillers is 5 vs 1 of 40 (p = 0.38). A weak long-filler trend is
possible; a 1000-item chain/parity run (seconds on the GPU) would settle it.

### 3c. The paper's own task, prompt and few-shot pool on our model

`scripts/paper_varbind_replication.py` imports their `build_prompt_messages_varbind` and runs their
easy system-of-equations dataset (500 items, coefficients {2}, constants 1–30, their first 5 few-shot
examples) across their condition ladder. Only the model differs.
Output: `results/paper_varbind_easy_qwen2.5-7b-instruct-bf16/`.

| condition | accuracy | Δ | wrong→right | right→wrong |
|---|---|---|---|---|
| baseline (k=0) | 0.4% | — | — | — |
| dots 5 / 10 / 25 / 50 / 100 / 250 | 0.8 / 0.6 / 1.0 / 0.4 / 0.2 / 0.2% | ≤ +0.6 | ≤ 3 | ≤ 1 |
| counting 5 / 10 / 25 / 50 | 0.8 / 0.6 / 0.6 / 0.4% | ≤ +0.4 | ≤ 2 | ≤ 1 |
| alphabet 10 / 25 / 100 | 0.4 / 0.6 / 0.2% | ≤ +0.2 | ≤ 1 | ≤ 1 |

For comparison the paper reports DeepSeek V3 31.1 → 61.0% and Kimi K2 18.4 → 36.4% on this task.
Qwen2.5-7B is at floor without filler, so there is nothing for filler to lift: on the paper's task
the null is a **capability floor**, not "capable but does not use the filler". Our own parity and
order items, where direct has headroom (50–65%), show no uplift either (§3b), which is the informative
part of the null.

## 4. Causal step corruption (`stego/corrupt.py`, `results/corrupt_qwen2.5-7b-bf16`)

Design. For each item and each format (nl = canonical `nl_cot`, sym = canonical `sym_cot`), the
assistant turn is **prefilled** with the derivation truncated right after the first key intermediate
(vLLM `continue_final_message`), in two versions: *clean* (value as computed) and *corrupt* (value
replaced by a seeded, answer-changing wrong value). The model continues; its final answer is classed
**follows** (= the answer consistent with the corrupted value), **original** (= the true answer: the
model ignored or silently corrected the step) or **other**.

| family | corrupted intermediate | corruption |
|---|---|---|
| syseq | `y` | ±{3,5,7,11,13} |
| chain | `s1` | ±{3,5,7,11,13} |
| symop | `m` (bracket value) | ±{3,5,7,11,13} |
| parity | `total` | +1 (flips parity) |
| order | full order | swap queried position with a neighbour |
| cipher | plaintext (and its per-letter mapping) | counterfactual twin's word |

Results (200 items × 2 formats × {clean, corrupt} = 800 calls, 6 s):

| subtype | nl clean-correct | nl follows | nl original | nl other | sym clean-correct | sym follows | sym original | sym other |
|---|---|---|---|---|---|---|---|---|
| syseq | 100% | 98% | 0% | 2% | 70% | 62% | 0% | 38% |
| chain | 100% | 98% | 2% | 0% | 100% | 100% | 0% | 0% |
| parity | 100% | 90% | 10% | 0% | 55% | 35% | 60% | 5% |
| order | 85% | 85% | 5% | 10% | 60% | 40% | 20% | 40% |
| letter | 90% | 95% | 0% | 5% | 40% | 60% | 0% | 40% |
| alphapos | 80% | 95% | 0% | 5% | 90% | 80% | 0% | 20% |
| symop | 85% | 80% | 2% | 18% | 55% | 40% | 0% | 60% |
| **ALL** | 92% | **92%** | 2% | 6% | 70% | **62%** | 8% | 30% |

**Conditional on the clean control being answered correctly: nl follows 94% (n=185), sym follows
73% (n=139).**

Hand inspection of the non-following cases:

- **The model never flags the corruption.** 0 of 400 corrupted continuations contain any
  self-correction language (wait / actually / mistake / should be / re-check …). It silently
  propagates the wrong step in both formats.
- **nl non-follows (12)**: 5 are items whose clean control was already wrong; 7 are downstream slips
  that still use the corrupted value (e.g. chain: continues from the corrupted `s1` but multiplies the
  original). Genuine silent corrections are ≈2%.
- **sym non-follows (60)**: 34 are items whose clean control was already wrong (the zero-shot symbolic
  continuation is brittle: sym clean-correct is 70% vs 92% for nl). Of the remaining 25, most are
  downstream slips *after* accepting the corrupted value: `3*113 + 9 = 357 + 9 = 366` (should be 348),
  `position = 20 + shift → 19`, `third = Mallory` read off the wrong index. Symbolic parity's 60%
  "original" is not correction either: the continuation is `final_state = total % 2 / Answer: off`,
  i.e. the model does not evaluate the expression and answers from the question, bypassing the
  scratchpad.

Interpretation for the README question (does faithfulness decline under symbolic CoT?):

1. **Both formats are causally relied upon**: a wrong visible intermediate changes the answer 92–94%
   (nl) / 62–73% (sym) of the time. The gap is not the model *correcting* symbolic errors; it is the
   symbolic continuation being **more brittle** (more arithmetic/readout slips, and in parity a
   tendency to bypass the scratchpad altogether). So symbolic CoT is somewhat *less* faithful in the
   causal-reliance sense, and the unfaithful cases are the ones where the answer does not follow
   from the scratchpad at all — the bad case for a monitor.
2. **Neither format produces self-monitoring.** A monitor that reads the CoT will see the wrong step
   written plainly, but the model itself gives no signal that anything is off.
3. **The symbolic scratchpad is legible when values are written** (0% English yet every intermediate
   is a number on a line), but zero-shot the model often writes unevaluated expressions, which hides
   the values a monitor or probe would need. Few-shot largely fixes that (§2).

## 5. Caveats

- 20-item subtypes (parity, order, letter, alphapos) have ±10-point noise; the family-level numbers
  (40 items) and ALL are the ones to lean on.
- One corruption point per item, one delta, temperature 0. Multi-sample (temperature > 0, `sample_idx`)
  and corrupting the *second* intermediate (syseq `c2y`, chain `s2`) are cheap extensions.
- The corruption runs use the zero-shot `nl_cot` / `symbolic` system prompts; the prefix itself acts
  as a one-line format demo. The sym clean-control rate (70%) would rise with few-shot demos.
- Answers are extracted from the continuation only, with the same regex as `stego/conditions.py`.
- Design lesson from the first prefill test (2026-09-10): a prefix that altered `y` but kept the canonical
  later steps ("Then three times 120 is 360 ... is 369") made the model simply echo `Answer: 369`. The
  prefix therefore stops right after the corrupted step, so the model must compute the rest itself.
- Operational: the vLLM server died once during the paper-matched filler sweep (2026-09-10, cause unknown;
  every call failed with a connection error). It was restarted with `--max-model-len 8192` and the sweep
  rerun; runs that had completed before the crash were served from the on-disk cache, only the failed
  runs were regenerated. Check `curl :8091/health` before any sweep.
- symop few-shot interference (§2) must be fixed before symop few-shot numbers are used anywhere.

## 6. Reproduce

```
python -m stego.smoke --workers 128 --conditions direct,nl_cot,symbolic,filler --k-filler 25 --out results/cond4_qwen2.5-7b-bf16
python -m stego.smoke --workers 128 --conditions direct,nl_cot,symbolic,filler --k-filler 25 --fewshot 3 --out results/cond4_fs3_k25_qwen2.5-7b-instruct-bf16
python -m stego.smoke --workers 128 --conditions direct,filler --k-filler 100 [--fewshot 3] --out results/filler_...
python -m stego.corrupt --dry            # print all 200 corruption plans, no model calls
python -m stego.corrupt --workers 128 --out results/corrupt_qwen2.5-7b-bf16
```

Each run's `summary.md` carries the label, k, filler type and few-shot count; each record in
`records.jsonl` now also carries `label` and the server-reported `model`.

## 7. Next: Hours 10–15 (GPU 1, HF transformers, bf16 weights identical to the vLLM server)

1. Filler positions: logit lens + trained linear probes for each intermediate at the dot positions,
   vs a random-direction control. Since there is no behavioural uplift, the question is purely
   "encoded but not read out?".
2. Symbolic positions: probe the residual at the token where the intermediate's value is written vs
   where an unevaluated expression is written, to test whether the value exists internally when the
   surface token is uninformative.
3. Matched-pair patching using the `counterfactual` twins (already in the dataset) as a
   lens-independent causal test.
4. Fix symop glyph reuse before any few-shot probing.
