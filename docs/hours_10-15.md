# Hours 10–15: probes and logit lens on the residual stream

Model: Qwen2.5-7B-Instruct bf16 (28 layers, d=3584), HF transformers on GPU 1, the same weights the
vLLM server uses. Probe set: `data/probe_v1.jsonl`, 1000 syseq + 1000 chain items, seed 1, disjoint
from `tasks_v1`. Residuals at every layer (embeddings + 28) at named positions:
`results/probe/<cond>/<family>.resid.npy` (18 GB total, git-ignored), extracted by `stego/extract.py`
in ~30 s per condition. Analysis: `stego/lens.py` (logit lens), `stego/probe.py` (ridge probes).

## 0. Question and design

The behavioural results (Hours 4–9) say filler dots give this model nothing and the symbolic
scratchpad is causally used but brittle. The mechanistic questions are:

1. **Filler:** are intermediates *encoded* at dot positions even though they are never read out?
2. **Symbolic vs English:** is the value present in the residual stream *before* it is written,
   and is it equally decodable in the two formats?

Conditions and positions:

| condition | prompt | positions |
|---|---|---|
| `filler` | zero-shot, 25 dots | `q_last` (the `?`), `dot_0..dot_24`, `final` (last prompt token) |
| `direct` | zero-shot, no filler | `q_last`, `final` |
| `sym` | canonical `sym_cot` prefilled as the assistant turn | per intermediate: `pre_<v>` = the `=` before the value, `val_<v>` = last digit of the value |
| `nl` | canonical `nl_cot` prefilled | same, marker `is` (syseq) / `gives` (chain) |

Probe: StandardScaler → PCA-64 → RidgeCV, 5-fold CV R², fitted per fold. Layers 0,2,…,28; dots at
stride 6. Controls: **shuffled labels** (≈0 everywhere), **random-64 subspace** instead of PCA, and
the control that turned out to matter most:

**Input-only ceiling and the nonlinear-part target.** Every intermediate is a simple function of
numbers that appear in the prompt (chain: s1 = N + a, s2 = s1·b, ans = s2 − c). A linear probe that
merely reads the prompt's numbers "decodes" s1 perfectly and s2 with R² 0.97. So for each target we
(a) report the CV R² of a linear model from the prompt's literal numbers alone (the ceiling a trivial
readout can reach) and (b) probe for the **residual of the target after that linear fit**, i.e. the
part only a genuine multiplication/composition can produce ("nonlin R²"). Targets that are exactly
linear in the inputs (`x`, `s1`) have no meaningful nonlinear part; ignore those rows.

Qwen tokenizes numbers one digit per token, so the paper's logit lens can only test one digit per
position. We ran it on the first digit (`*.lens.csv`): the only signal is the prompt operand `x` at
dot positions (57% top-1 vs 10% shuffled, layers 24–26); nothing computed shows up, and many rows are
majority-digit artefacts. The probes below are the real instrument.

## 1. Filler positions carry the operand, not the computation

Nonlinear-part R², max over layers (shuffled control ≈ 0 in every cell):

| family / target | `q_last` | best dot | `final` (filler) | `final` (direct) |
|---|---|---|---|---|
| chain s2 = (N+a)·b | 0.05 | 0.13 | **0.88** (L24) | **0.89** (L28) |
| chain answer | 0.05 | 0.13 | **0.88** | **0.89** |
| syseq c1x | 0.00 | 0.01 | 0.14 | 0.21 |
| syseq y | 0.00 | 0.00 | 0.10 | 0.14 |
| syseq c2y | 0.00 | 0.00 | 0.23 | 0.26 |
| syseq answer | 0.00 | 0.00 | 0.23 | 0.27 |

- **Dots are inert.** No computed value is decodable at any dot position. The final position
  reaches the same R² with and without the 25 dots in front of it.
- **The operand is relayed.** The prompt-given `x` is decodable at `dot_0` at layer 24 with raw
  R² 0.75 (vs 0.22 at `q_last`), decaying along the dots (0.36, 0.47, 0.29, 0.14 at dots 6/12/18/24).
  This is the paper's "operands present, composition absent" pattern, here for a model with no
  behavioural uplift at all.
- **The chain product is computed late and at the answer position only.** At `final`, nonlin R² for
  s2 goes 0.02 (L16) → 0.22 (L20) → 0.88 (L24), then flat. For syseq the two-hop chain is barely
  computed (≤ 0.27 at L26), matching the 0.4% floor on the paper's task.
- **Computed approximately, not emitted.** With the product decodable at R² 0.88, the model's own
  greedy first digit at that position is right only 46% of the time (direct/chain, n=1000), and
  45% of its guesses are the digit `1` whatever the answer. R² 0.88 leaves ~35% of the std as error;
  the residual holds a magnitude estimate, not the exact integer.

## 2. Symbolic and English scratchpads are internally identical

Nonlinear-part R² at the position *before* the value is written (`pre_`) and at the value's last
digit (`val_`), max over layers; shuffled ≈ 0 throughout:

| family / target | `pre_` symbolic | `pre_` English | `val_` symbolic | `val_` English |
|---|---|---|---|---|
| chain s2 | **0.95** (L26) | **0.95** (L28) | 0.79 | 0.78 |
| syseq c1x = c1·x | **0.83** (L28) | **0.84** (L26) | 0.60 | 0.64 |
| syseq y | 0.55 | 0.52 | 0.38 | 0.38 |
| syseq c2y | 0.47 | 0.39 | 0.41 | 0.34 |
| syseq answer (at `pre_c2y`) | 0.46 | 0.38 | 0.40 | 0.34 |

- **The value exists before it is written, equally in both formats.** At the `=` (symbolic) or `is`
  (English) token that precedes the product, the product is decodable at 0.95 / 0.95 (chain) and
  0.83 / 0.84 (syseq c1x). A monitor that could read the residual would see the value at the same
  moment in either format.
- **It is computed only once its operands are in context.** Nothing is decodable at `pre_x` /
  `val_x` (0.00–0.02): the model does not pre-compute the chain when it sees the question; it does
  one multiplication per scratchpad line, at that line.
- **Writing the value changes the representation.** At the value's own digit token the nonlinear R²
  *drops* (0.95 → 0.79, 0.83 → 0.60): once the digits are in context, the residual at the digit
  represents the token being copied, not the quantity being computed.
- **Symbolic hides nothing extra.** The Hours 4–9 finding that symbolic CoT is less faithful
  (73% vs 94% follows-rate) is therefore not because the values are less available internally; the
  brittleness is in the readout/continuation, not in the representation.

## 2b. Activation patching: the filler region is causally inert; the operand is read from the question by layer 22–24

`stego/patch.py`, `results/patch/{chain,syseq}.summary.md` (per-pair rows in `.jsonl`). Matched pairs
= item A and its counterfactual twin B (same prompt except the operand, `N` for chain / `x` for
syseq, hence a different answer); pairs kept only if token layouts are identical and the answers'
first digits differ (chain 442 pairs, syseq 574). A is run with the output of decoder layer L (or of
every layer, "all" = transplanting the region's whole computation, the paper's KV-cache transplant)
replaced at chosen positions, and three things are read at the final position:

- **recovery** = (m_patched − m_A)/(m_B − m_A), m = logit(first digit of B's answer) − logit(first
  digit of A's answer); 0 = no effect, 1 = output moved fully to B's (pairs with |m_B − m_A| > 0.5)
- **probe shift** = (probe(x)_patched − probe(x)_clean)/(x_B − x_A), a ridge probe for the operand at
  the final position, layer 24, fitted on the clean runs (fit R² chain 0.98, syseq 0.61)
- **KL**(patched ‖ clean A) of the next-token distribution, nats

| source written into A | chain recovery (L0 / L16 / L22 / L24 / all) | chain probe shift | chain KL | syseq recovery (L0 / L16 / L22 / L24 / all) | syseq KL |
|---|---|---|---|---|---|
| twin's dots (25 positions) | 0.00 / 0.00 / 0.00 / 0.00 / 0.01 | 0.00 | ≤ 0.011 | 0.01 / 0.00 / 0.01 / 0.00 / 0.01 | ≤ 0.011 |
| unrelated item's dots | 0.00 everywhere | 0.00 | ≤ 0.013 | 0.01 everywhere | ≤ 0.019 |
| across-item mean at dots | 0.00 / −0.01 / 0.00 / 0.01 / −0.01 | 0.00 | 0.03–0.66 | 0.08 / 0.03 / 0.04 / 0.02 / 0.05 | 0.06–0.89 |
| random vectors at dots (norm-matched) | 0.08 / 0.25 / 0.02 / 0.08 / 0.26 | ≤ 0.24 | 0.3–2.2 | −0.01 / 0.31 / 0.19 / 0.09 / 0.21 | 0.1–1.8 |
| **twin's operand digits in the question** (positive control) | **1.00 / 0.89 / 0.72 / 0.00 / 1.00** | 0.97 → 0.61 → 0.00 | 4.7 → 2.6 → 0.001 | **1.00 / 0.59 / 0.42 / 0.01 / 1.00** | 0.32 → 0.11 → 0.001 |

- **Dots are causally inert.** Swapping in the twin's entire filler region, at any single layer or
  at all layers, changes nothing the answer position does: recovery 0, probe shift 0, KL ≈ 0.01. An
  unrelated item's dots are indistinguishable from the twin's. This is the paper's KV-transplant
  test with the opposite outcome, on a model with no behavioural uplift. It also settles the
  probe/behaviour gap of §1 for the *dots*: the operand that is decodable at `dot_0` is a copy the
  answer position never reads.
- **Mean ablation is benign; random vectors disrupt.** Replacing the dots by their across-item mean
  leaves recovery at 0 and KL small. Replacing them by norm-matched Gaussian noise perturbs the
  output (KL up to 2.2 nats) and drags the logit-difference metric toward the middle (recovery up
  to 0.31, an artefact of the perturbation, not movement toward B). So the README's "patch a random
  vector" does break downstream computation, but by injecting out-of-distribution keys/values that
  hijack attention, not by removing information: the same removal done cleanly (mean) is harmless.
- **The operand is read straight from the question, in a window that closes at layer 22–24.**
  Patching the twin's operand digits moves the output fully to B's when done at layers 0–8, partly at
  16–22 (chain 0.89 → 0.72, syseq 0.59 → 0.42), and not at all at layer 24: by then the answer
  position has already attended to the operand, and the product appears there between layers 20 and
  24 (§1). The probe-shift column tracks the same window. syseq's KL under the operand patch is small
  (0.32) because its output distribution is dominated by the ` Answer`/`1` prior either way; the
  logit-difference still moves fully.

## 2c. Cipher family: the plaintext letter is present before it is written; not at all in one pass

`stego/cipher_probe.py`, `results/probe/cipher/summary.md`. 702 items (every word x shift 1–3 x
queried position) of the `letter` subtype. Targets are letters, so the probe is scaler → PCA-64 →
multinomial logistic regression, 5-fold stratified CV accuracy, 26-way. Controls: shuffled labels,
majority class, and an **input ceiling** = the same classifier on one-hot(cipher letter) +
one-hot(shift) [+ one-hot(queried position)]: because the word pool is small and English letter
frequencies are skewed, "pick the likeliest of the three candidate letters" already reaches 77%
(per letter) / 84% (answer letter). A probe has to beat that to show the modular subtraction was done.

Letter level (3627 letters, majority 14%, ceiling 77%), accuracy at the best layer:

| token | symbolic | English |
|---|---|---|
| the ciphertext letter (` U`), before the arrow | 98% (L16; 95% already at L4) | 99% (L16) |
| the arrow (`->`), plaintext not yet written | **100%** (L24) | **100%** (L24) |
| the plaintext letter itself (sanity) | 100% (L0) | 100% (L0) |

Answer letter (702 items, majority 15%, ceiling 84%):

| position | symbolic | English | filler (best of dots/final) | direct (final) |
|---|---|---|---|---|
| token before the answer letter (`=` / `'`) | 91% (L28; 67% L20, 88% L24) | **99%** (L28; 85% L20) | — | — |
| token before / at the decoded word | 34% / 40% | 34% / 43% | — | — |
| dots / final | — | — | 18% / 21% | 19% |

- **README angle 2, answered: yes.** In a scratchpad the plaintext letter is fully decodable at the
  arrow, before the model emits it, and already at the ciphertext letter's own token by layer 4:
  the shift-back is a cheap lookup done as soon as the letter and the shift are both in context.
  Well above the 77% frequency-prior ceiling, so it is computed, not guessed.
- **Formats identical for the decode, English slightly ahead for the indexing.** Letter-level
  numbers match to the point. Picking the queried letter out of the decoded word resolves late
  (L20–28) and is the one place symbolic lags: 91% vs 99% at the token before the answer. That
  matches the behavioural gap on cipher (Hours 4–9: symbolic 95–100% vs English 85–90% with
  demos, but zero-shot symbolic wrote `ord()`/`chr()` pseudo-code it never evaluated).
- **In one forward pass nothing is decoded.** With no scratchpad the answer letter is at 15–21% at
  every dot and at the final token: barely the majority class, far below the 84% a linear prior
  could reach. A plausible reason is tokenization: in the question the ciphertext is one token
  (`ULYHU`), so the model would first have to split it into letters; the scratchpad hands it one
  letter per token. This is the cleanest case in the project of "CoT necessary because the
  surface form hides the operands", and the dots do not help with it.

## 3. Controls

- Shuffled labels: −0.03 to +0.01 in every cell of every table.
- Random-64 subspace: consistently below the PCA probe on the raw target (e.g. chain final 0.95 vs
  0.97; syseq dot_0 answer 0.25 vs 0.63), i.e. the signal is concentrated, not diffuse.
- Input-only linear ceilings: chain answer 0.97, s2 0.97, s1 1.00; syseq answer 0.93, c1x 0.97,
  y 0.96, c2y 0.93 (degree-2 polynomial: 1.00 for all). Raw R² above these would be meaningless;
  the nonlinear-part probe is what carries the result.
- Ambiguous items (a value string colliding with an earlier one) skipped: 4–7 per teacher-forced
  condition.

## 4. Caveats

- Numeric probes on syseq and chain, letter probes on cipher; parity/order/symop not probed.
- Layers at stride 2 and dots at stride 6; "max over layers" is optimistic by a few hundredths.
- Teacher-forced canonical scratchpads, not the model's own generations. The planned probe on the
  model's zero-shot symbolic outputs where it wrote an *unevaluated* expression (`x = 12 + 19`) is
  not done; it is the most direct test of "legible plan, hidden value".
- Patching (§2b) uses the first-digit logit difference as its behavioural metric because the model's
  exact answers are almost all wrong; pairs whose twins share a first digit are dropped, and pairs
  with |m_B − m_A| ≤ 0.5 are excluded from the recovery mean. Single-layer patches replace one
  layer's output at the dot positions and let it propagate; "all" replaces every layer's output.
- In the filler condition the `final` token is the assistant header; the model's top token there
  is often ` Answer` (it wants to write the label first), so it is not exactly the emit position.
  The direct condition, where it is, gives the same probe numbers.

## 5. Reproduce

```
CUDA_VISIBLE_DEVICES=1 python -m stego.extract --conditions filler,direct,sym,nl --k 25   # ~2 min, 18 GB
CUDA_VISIBLE_DEVICES=1 python -m stego.lens  --cond filler --family syseq
python -m stego.probe --cond filler --family syseq      # ~4 min per (cond, family); 8 runs
```
Per-(target, position, layer) numbers: `results/probe/<cond>/<family>.probe.csv` and `.lens.csv`.

## 6. Headline for the write-up

Filler dots carry the prompt's operand but no computed value; the computation that does happen
occurs at the answer position, late (L20–24), approximately, and is not emitted as the right digits.
Symbolic and English scratchpads are internally indistinguishable: each intermediate is decodable
at the token right before it is written, only once its operands are on the page, and equally in both
formats. The symbolic format's lower faithfulness is a readout problem, not a representation problem.
