# Filler-token side quest: why filler does not help Qwen2.5-7B when it helped in Brauer et al.

Status: parked. The behavioural null is recorded as a result (`docs/hours_4-9.md` §3, §3b, §3c).
If time permits, design tests that give the filler-token prompt a fairer shot against the normal
prompt (see "What would settle it" below).

## Is it an experimental-design issue? No.

`scripts/paper_varbind_replication.py` imports the paper's own prompt builder from the cloned repo
(`/home/amit/filler-token-reasoning`) and runs their system-of-equations dataset with their system
prompt, their `Filler:`/`Answer:` scaffold and their held-out few-shot pool. The only thing that
differs is the model.

| | no filler | best filler |
|---|---|---|
| DeepSeek V3 (paper) | 31.1% | 61.0% |
| Kimi K2 (paper) | 18.4% | 36.4% |
| Qwen2.5-7B-Instruct (ours, same code and data) | 0.4% | 1.0% |

Our own prompt format (`stego/conditions.py`) was also checked against their code: filler in the
user turn after the question and before `Answer:`, announced in the system prompt, baseline drops
the filler line. Only cosmetic differences remain (fixed vs rotating few-shot, blank lines, bare
assistant turns, count not stated). The paper-matched sweep on our 200 items (5-shot, dots /
counting / alphabet, k = 10–250) gives direct 15% vs filler 14–19%, no condition significant.

Whatever explains the gap lives in the model, not the prompt.

## Why, in order of confidence

1. **Filler adds width, not depth.** With causal attention, a value computed at one filler position
   by layer L is readable by later positions only at layers above L. A multi-step chain therefore
   still has to climb the layer stack: the paper's own analysis places the equation chain at layers
   33 → 38 → 44 → 51 → 60 in a 61-layer model. Filler positions give extra places to park
   intermediate values and a question → filler → answer relay, but they cannot add serial steps.
   Qwen2.5-7B has 28 layers. If the two-hop chain needs more serial depth than that, no number of
   dots helps, which matches the 0.4% floor.

2. **Using filler as a relay is a learned, model-specific behaviour.** The paper reports that
   Qwen3 at 480B, with ample depth, showed almost no uplift. Pfau et al. (2024) found models need
   targeted training to exploit filler. DeepSeek V3 and Kimi K2 happen to have picked it up; a 7B
   instruct model with no such pressure has not. Depth is necessary but not sufficient.

3. **The paper's strongest effects are on retrieval-plus-one-step tasks.** Its largest uplift is
   1-fact addition, 54% → 72%: recall a fact, add a number. Our tasks are pure computation with
   two to four serial steps, and the paper task we replicated is their hardest (the equation
   chain). We never tested a one-step task with headroom, the one place a 7B might plausibly show
   something. This is a gap in our task set, not a flaw in the filler implementation.

4. **A capability floor hides everything else.** On five of seven task types the model is at
   0–20% without reasoning; uplift can only show where partial single-pass ability exists. Parity
   and order are the only types with headroom and they show nothing, but with 20 items each they
   cannot detect a small effect.

## What would settle it (if time permits)

- **Deeper model.** Qwen2.5-32B-Instruct (64 layers) fits on one A100 in bf16. Uplift at 32B and
  not at 7B would confirm the depth story. Qwen2.5-14B-Instruct (48 layers) is a cheaper middle
  point. Both need an HF download; only 7B is on disk in HF format.
- **One-step task with headroom.** E.g. two-digit multiplication (`23 × 47`): single operation,
  direct accuracy well below ceiling. Add as a family in `stego/tasks.py`, rerun the paper-matched
  sweep. Seconds of compute.
- **More items on the headroom tasks.** 1000 parity / order / chain items would make the weak
  long-filler trend (counting_100 p = 0.10, alphabet_250 p = 0.12) either significant or gone.
- **Enhance parity between the filler prompt and the normal prompt.** Ideas: (a) match total prompt
  length by padding the no-filler baseline with an equal number of irrelevant tokens *before* the
  question (the paper's `pre_padding` mode), so any effect is attributable to filler *position*
  rather than prompt length; (b) put the filler in the assistant turn (prefilled) instead of the
  user turn, so it sits after the chat-template boundary; (c) few-shot demos whose filler region
  is the same length as the target's; (d) a scrambled-counting control (their `c-scram`) to
  separate "any tokens" from "structured tokens".
- **The mechanistic question survives the behavioural null.** Even with no uplift, operands may be
  encoded at filler positions and never composed, which is what the paper found in its own
  wrong-answer examples. This is the Hours 10–15 probe on GPU 1, and it does not depend on any of
  the above.

## Recommendation

Keep the null as a result. Add the one-step task as a cheap control. Let the Hours 10–15 probing
decide whether anything is happening under the surface before spending time on larger models.
