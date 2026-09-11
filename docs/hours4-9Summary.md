# Hours 0–9 summary (as of 2026-09-11)

Model: Qwen2.5-7B-Instruct, bf16, served by vLLM on one A100-80GB (label `qwen2.5-7b-instruct-bf16`).
Dataset: 200 synthetic puzzles in five families (system of equations, arithmetic chain, logic
parity/order, Caesar cipher letter/alphabet-index, made-up operators), each with named intermediates,
a canonical English and a canonical symbolic derivation, and a counterfactual twin.
Detailed tables, failure inspections and reproduction commands: `docs/hours_0-3.md`, `docs/hours_4-9.md`.

## Experiments run

1. **Calibration baseline.** All 200 puzzles under direct answering and English CoT. Run first on CPU
   at Q8 (`results/smoke_qwen2.5-7b`), then redone on GPU at bf16 after the hardware change
   (`results/smoke_qwen2.5-7b-bf16`). The CPU results were independently verified: gold answers
   re-derived from question text, summary recounted from raw records, every record mapped to its
   cache file.
2. **Four-condition comparison.** Direct, English CoT, symbolic-only CoT, filler dots; zero-shot
   (`results/cond4_qwen2.5-7b-bf16`) and with 3 same-subtype demonstrations
   (`results/cond4_fs3_k25_qwen2.5-7b-instruct-bf16`).
3. **Filler sweep at the paper's settings.** Dots / counting / alphabet, k = 10, 25, 50, 100, 250,
   5 demonstrations, per-item McNemar against direct (`results/fillersweep/`). The prompt format was
   checked against the paper's released code (`/home/amit/filler-token-reasoning`).
4. **Paper replication.** The paper's own system-of-equations dataset, prompt builder and few-shot
   pool, imported from their repo and run on our model
   (`scripts/paper_varbind_replication.py`, `results/paper_varbind_easy_qwen2.5-7b-instruct-bf16`).
5. **Causal step corruption.** For each puzzle and both scratchpad formats, the correct reasoning is
   prefilled up to the first intermediate, once clean and once with that value altered; the model
   continues and we check whether the answer follows the alteration
   (`stego/corrupt.py`, `results/corrupt_qwen2.5-7b-bf16`).

## Results

- **The tasks require reasoning.** Direct answering is at floor (0–20%) for equations, chains,
  operators and ciphers; English CoT reaches 92%. Parity and order are the exception (direct near
  chance), so they are weaker evidence.
- **Filler tokens give this model nothing.** Direct 13–16% vs filler 10–19% across every type and
  length; no condition significant (best p = 0.10). On the paper's own task the model scores 0.4%
  with or without filler (paper: DeepSeek V3 31 → 61%, Kimi K2 18 → 36%). That is a capability
  floor; the informative null is parity/order, where direct has headroom (50–65%) and filler still
  adds nothing.
- **Symbolic reasoning is fully compliant but weaker.** 0 English lines in 200 completions, yet 48%
  zero-shot because the model writes unevaluated expressions. 3 demonstrations lift it to 81%.
- **Both scratchpads are causally used.** A corrupted intermediate changes the answer 94% of the time
  in English (n = 185) and 73% in symbolic notation (n = 139), among items whose clean control was
  correct.
- **Symbolic is less faithful through brittleness, not correction.** Its non-following cases are
  downstream slips after accepting the wrong value, or (parity) skipping the scratchpad entirely.
  Genuine silent corrections are ≈2% in both formats.
- **The model never flags a corrupted step.** 0 of 400 corrupted continuations contain any
  self-correction language.
- **Reasoning-distilled model (added 2026-09-11, `docs/hours_4-9.md` §4b).** DeepSeek-R1-Distill-Qwen-7B
  with the corrupted step inside its think block: follows 40% (English) / 63% (symbolic) vs 94/73 for
  the instruct model. Not self-correction: the think block follows the corruption in 176/192 cases
  and notice-words stay at 4/192. Instead the model exits the think block after ~13 words and writes
  a fresh step-by-step solution in the answer, reverting to the true value where it re-derives
  (arithmetic families) and copying the think block's wrong conclusion where it does not (cipher).
  Reasoning shown and answer given diverge silently in half the English cases.

## Open issues

- Order scores 60% under English CoT at bf16, below the 80% bar; most misses read the wrong
  position out of a correctly derived order. Accept, or enlarge the subtype to 40 items.
- The symop family reuses operator glyphs across items with different definitions, which poisons
  its few-shot runs (symbolic 30%, English drops 100 → 85). Fix before probing.
- A weak long-filler trend at k = 100–250 is not significant at 200 items; a 1000-item run would
  settle it.

## Not yet done

- Hours 10–15: linear probes and logit lens at filler and symbolic positions (GPU 1, HF bf16
  weights identical to the server), with a random-direction control; counterfactual-twin patching.
- `scripts/serve.sh` and `scripts/hf_smoke.py` still target CPU.
- Uncommitted: `stego/corrupt.py`, `stego/smoke.py` (few-shot flag, label/model per record),
  `scripts/paper_varbind_replication.py`, `docs/hours_4-9.md`, this file, and the new `results/` dirs.
