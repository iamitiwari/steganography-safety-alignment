# Hours 10–15 summary (as of 2026-09-11)

Model: Qwen2.5-7B-Instruct bf16, 28 layers, HF transformers on GPU 1 (same weights as the vLLM
server). Probe set: `data/probe_v1.jsonl`, 1000 syseq + 1000 chain items, seed 1, disjoint from
`tasks_v1`. Detailed tables, controls and reproduction commands: `docs/hours_10-15.md`.

Question: the behavioural phase showed filler dots give nothing and the symbolic scratchpad is used
but brittle. Mechanistically: are intermediates *encoded* where the surface tokens look uninformative
(dots; the symbolic scratchpad before a value is written), and does the answer position *use* them?

## Experiments run

1. **Residual extraction** (`stego/extract.py`). All 29 layers at named positions for four
   conditions: `filler` (last question token, every dot, final token), `direct` (question, final),
   and teacher-forced `sym` / `nl` scratchpads (the `=`/`is` token *before* each value, and the
   value's last digit). 18 GB, git-ignored, ~30 s per condition.
2. **Logit lens** (`stego/lens.py`), first-digit variant with cross-example mean subtraction, since
   Qwen tokenizes numbers digit by digit.
3. **Linear probes** (`stego/probe.py`). Scaler → PCA-64 → ridge, 5-fold CV R², per target ×
   position × layer. Controls: shuffled labels, random-64 subspace, and an **input-only ceiling**:
   every intermediate is a simple function of numbers in the prompt, so the reported number is the
   probe's R² on the *nonlinear part* of the target (value minus its linear fit from the prompt's
   numbers), the part only a real multiplication can produce.
4. **Activation patching** (`stego/patch.py`). Counterfactual-twin pairs (chain 442, syseq 574).
   A's residual at the 25 dot positions replaced, per layer and at all layers, by: the twin's dots,
   an unrelated item's dots, the across-item mean, norm-matched random vectors; positive control =
   the twin's operand digits in the question. Readouts at the answer position: first-digit
   logit-difference recovery, operand-probe shift, KL vs clean.
5. **Cipher family** (`stego/cipher_probe.py`, 702 items). 26-way logistic probes for the plaintext
   letter at the ciphertext letter, at the arrow before the letter is written, and for the answer
   letter before it is written; plus dots/final in filler/direct. Input ceiling = classifier on
   one-hot(cipher letter, shift[, position]), i.e. a letter-frequency prior (77% / 84%).

## Results

- **Dots carry the operand, not the computation.** The prompt-given `x` is decodable at the first
  dot at layer 24 (raw R² 0.75) and decays along the run. No computed value is decodable at any dot
  (nonlinear R² ≤ 0.13). The chain product appears only at the answer position, abruptly between
  layers 20 and 24 (0.22 → 0.88), identically with and without the dots. Syseq's two-hop chain is
  barely computed in one pass (≤ 0.27), matching the 0.4% floor on the paper's task.
- **Dots are causally inert.** Transplanting the twin's entire filler region, at any layer or all
  layers, gives recovery 0.00, probe shift 0.00, KL ≤ 0.011 nats; an unrelated item's dots are
  indistinguishable; mean ablation is benign. The paper's KV-transplant test, with the opposite
  outcome. The copy of `x` at the dots is never read.
- **Random vectors disrupt, but by hijacking, not by removing information.** Norm-matched noise at
  the dots raises KL to ~2 nats and drags the metric toward the middle; the clean removal (mean)
  does nothing. Answers the README's "patch a random vector" question.
- **The operand is read from the question in a window that closes at layer 22–24.** Patching the
  twin's operand digits moves the output fully to the twin's answer at layers 0–8, partly at
  16–22, not at all at 24, in both families: the answer position has attended to the operand by
  then, and the product appears there next.
- **Computed approximately, not emitted.** With the product decodable at R² 0.88 at the answer
  position, the model's own greedy first digit is right only 46% of the time (chain, direct) and 45%
  of its guesses are `1`. The residual holds a magnitude estimate, not the exact integer.
- **Symbolic and English scratchpads are internally identical.** Each value is decodable at the
  token right before it is written (chain product 0.95 / 0.95; syseq c1x 0.83 / 0.84), only once its
  operands are on the page (0.00 at the first line), and the signal drops once the digits are
  written (0.95 → 0.79). The symbolic format's lower faithfulness (Hours 4–9: 73% vs 94%) is a
  readout problem, not a representation problem.
- **Cipher: the plaintext letter is present before it is written, in both formats.** 100% at the
  arrow token (95% already at the ciphertext letter's token by layer 4), against a 77% prior
  ceiling; formats identical. Indexing the queried letter resolves late and is the one place
  symbolic lags (91% vs 99% at the token before the answer). With no scratchpad the answer letter
  is at 15–21% at every dot and the final token, below even the linear prior: nothing is decoded
  in one pass, plausibly because the ciphertext is a single token in the question.
- **Logit lens is the wrong instrument here.** Digit tokenization limits it to one digit; most rows
  were majority-digit artefacts; its only genuine signal was the operand at the dots (57% vs 10%
  shuffled). Kept in the notes as "what a token-reading monitor would see".

## Open issues

- Probes find information; they do not prove it is used. Patching settled this for the dots (not
  used) and for the question operand (used). The 0.88-vs-46% gap at the answer position is not
  yet resolved causally: it could be an approximate value the model cannot read out, or a
  correlate it ignores.
- Numeric probes on syseq and chain, letter probes on cipher; parity/order/symop not probed. Layers at stride 2 (numeric) or 4 (cipher), dots at stride 6.
- Teacher-forced canonical scratchpads, not the model's own generations.

## Not done (from the plan and the README)

- **Probe the model's own zero-shot symbolic outputs where it wrote an unevaluated expression**
  (`x = 12 + 19`, no value): is `31` decodable at the end of that line? The most direct test of
  "legible plan, hidden value". Requires re-extracting on the model's generations from
  `results/cond4_qwen2.5-7b-bf16`.
- Parity / order / symop not probed; symop glyph reuse still unfixed. (Cipher now done, §5.)
- Tuned / template lens instead of logit lens (low value given digit tokenization).
- Fine-tuning a model to use a cipher (README angle 2, second half): out of the 20-hour scope.
