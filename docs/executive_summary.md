# Does a scratchpad stay legible when it is not English? Filler dots, symbolic notation and causal reliance in a 7B model

Code, data, per-item results: <https://github.com/iamitiwari/steganography-filler-tokens-MATS-application>. Interactive overview: <https://molab.marimo.io/notebooks/nb_YcxWCMsnUEvy1NvYxpqKFQ>.

## Problem

Brauer et al. (2026) show frontier mixture-of-experts models computing across content-free filler tokens: task-relevant work where a monitor sees nothing. Between filler and plain English sits a symbolic scratchpad, legible only to those who know the notation. I ask a small open model: does it compute in filler at all; is its scratchpad causally load-bearing, and does that change when it is symbolic; and is a value present internally before it is written, equally in both formats?

## Setup

200 puzzles in five families: the paper's equation chains, arithmetic chains, parity, ordering, Caesar ciphers, made-up operators. Each has named intermediates, matched English and symbolic derivations, and a one-change counterfactual twin. Direct answering scores 13%, English chain of thought 92%, so the tasks need the scratchpad. Model: Qwen2.5-7B-Instruct throughout; DeepSeek-R1-Distill-Qwen-7B for one replication.

## Findings

**1. Filler is a clean null (Fig. 1).** At the paper's exact settings, filler never beats direct. On the paper's own dataset and prompt code, this model scores 0.4% with or without filler, where they report 31% to 61%. Parity and ordering have headroom and gain nothing.

**2. Both scratchpads are load-bearing, and neither is checked (Fig. 2).** Alter the first intermediate in a prefilled derivation: the answer follows the wrong value 94% of the time in English, 73% in symbolic. Zero of 400 continuations remark on the error. The symbolic gap is brittleness, not correction.

**3. Symbolic hides nothing internally.** Probes find each value at the token before it is written, equally in both formats: 0.95 and 0.95 for the chain product, 0.83 and 0.84 for the equation product. Cipher plaintext letters are 100% decodable before they appear, against a 77% frequency ceiling.

**4. Dots carry the operand, not the computation, and are causally inert (Fig. 3).** Probing the nonlinear part of each value, what a linear readout of the prompt cannot give, finds at most 0.13 at any dot. The product appears only at the answer token, between layers 20 and 24, identically with the dots removed. Transplanting a twin's dot region moves the answer by 0.00 at every layer; transplanting its operand digits moves it fully until layer 24.

**5. A reasoning-distilled model diverges from its own trace (Fig. 2, orange).** With the corruption inside its think block, DeepSeek-R1-Distill follows it only 40% of the time, but not by noticing: the think block follows it in 176 of 192 cases; the visible answer re-derives from scratch and silently overrides. For a monitor, that is the worse case.

## Inconclusive

The chain product is decodable at R² 0.88 at the answer token while the model's own first digit is right 46% of the time; unresolved causally. A long-filler trend, p = 0.10, needs a larger run. Ordering scores 60% from readout slips on a correct order. The R1 effect is partly a property of the prefill design.

## Sanity checks

All 200 gold answers re-derived from question text with independent code; summaries recounted from raw records, catching one omitted miss. Hand-read cipher completions: 21 of 37 correct answers had the wrong decoded word. The input-only ceiling was essential: a linear readout of the prompt gives R² 0.97 for the chain product, so without it probe results are fake. A patching positive control caught a localisation bug.

## Limitations and future work

One 7B instruct model with no reasoning RL, so the null says little about frontier models. Two numeric families probed plus cipher; teacher-forced scratchpads; single seed; 20-item subtypes. Next: corrupt a step the reasoning model wrote itself and patch its think region; probe the instruct model's own unevaluated symbolic lines; test filler on a 64-layer model.

---

*Fig. 1: filler accuracy against token count, three filler types, with direct and English-scratchpad references. Fig. 2: follows-rate under a corrupted intermediate, by format and model. Fig. 3: left, probe R² for the nonlinear part of the answer by layer, answer token versus first dot; right, patching recovery by layer, twin's dots versus twin's operand digits.*
