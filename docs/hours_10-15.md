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

- Two families only (syseq, chain); parity/order/cipher/symop not probed.
- Layers at stride 2 and dots at stride 6; "max over layers" is optimistic by a few hundredths.
- Teacher-forced canonical scratchpads, not the model's own generations. The planned probe on the
  model's zero-shot symbolic outputs where it wrote an *unevaluated* expression (`x = 12 + 19`) is
  not done; it is the most direct test of "legible plan, hidden value".
- Counterfactual-twin activation patching (plan step 4) not done.
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
