# How our project differs from Roger (2025), "Do reasoning models use their scratchpad like we do?"

Source: Fabien Roger, Alignment Forum, 2025-03-11 (linkpost for alignment.anthropic.com),
https://www.alignmentforum.org/posts/ywzLszRuGRDpabjCk/do-reasoning-models-use-their-scratchpad-like-we-do-evidence

The post and our project ask neighbouring questions with different methods, and they are
complementary more than overlapping.

## Comparison by dimension

| | Roger, March 2025 | Our project |
|---|---|---|
| Question | Does an RL-trained reasoning model hide extra reasoning in the *syntax* of a natural-language scratchpad? | Is the scratchpad causally load-bearing, and does that change when the representation is English, symbols, or dots? |
| Method | Training-time: paraphrase 10k correct MATH scratchpads with Claude 3.5 Sonnet, fine-tune the base model on them, compare pass@1 against fine-tuning on the originals | Inference-time: four prompt conditions, plus prefilled scratchpads with one intermediate altered; no training |
| Intervention | Semantics-preserving, syntax-destroying (paraphrase); plus random word dropout at 5% and 20% | Syntax-preserving, semantics-altering at one known step |
| Model | Claude 3.7 Sonnet base (early checkpoint), an RL reasoning model at frontier scale; also XL/L/M/S variants | Qwen2.5-7B-Instruct, dense, no reasoning RL |
| Task | MATH, natural problems, no ground-truth intermediates | 200 synthetic puzzles with named intermediates, canonical English and symbolic derivations, counterfactual twins |
| Filler control | Model trained to count 1 to 3000 before answering; performs poorly | Prompt-level dots / counting / alphabet at k = 10–250, 5-shot, following Brauer et al.; no uplift |
| Mechanistic work | None, behavioural only | Planned (Hours 10–15): linear probes, logit lens, activation patching at filler and symbolic positions |
| Headline result | Paraphrased-scratchpad distillation matches original-scratchpad distillation; 20% word dropout hurts sharply; empty scratchpad and filler perform poorly | Corrupted intermediate changes the answer 94% (English) / 73% (symbolic); 0/400 continuations flag the corruption; filler gives nothing; symbolic is legible but brittle |

## The tests are logical complements

Paraphrasing asks whether meaning alone is enough to reproduce the answer. It cannot see a model
that ignores its scratchpad and computes the answer internally, because such a model would survive
paraphrasing perfectly. Our corruption test targets exactly that case: change one value and see
whether the answer moves.

Roger's 20% word-dropout result, where performance drops sharply, is the closest thing in the post
to our finding that the answer follows a corrupted step 94% of the time. Both say the visible text
is relied upon. Our design is nearer to the "add a mistake to the CoT" test from Lanham et al. 2023
than to the paraphrase test.

## Non-natural scratchpads are our axis, not theirs

Roger studies whether a benign-looking English scratchpad secretly carries bits in its syntax. We
force the scratchpad into symbolic notation and measure legibility, capability and faithfulness,
and separately test whether content-free dots carry computation. Neither is in the post.

Their steganography concern is "looks benign but encodes more". Ours includes "looks uninformative
(symbols, dots) but is it computed and relied upon".

## Filler agrees across both

Roger trained a model to count to 3000 before answering and it performed poorly. Our prompt-level
filler at the paper-matched settings gives nothing on a 7B model, and the model is at floor on
Brauer et al.'s own system-of-equations task with or without filler. Same conclusion, different
mechanism: theirs is a training control, ours is a prompt-format condition.

## Ground truth is our structural advantage

Every puzzle has known intermediates, so we can corrupt a specific step and later probe for a
specific value at a specific position. MATH has no such handle, which is why Roger intervenes on the
whole text at once and interprets the result statistically.

## What they have that we lack

A frontier reasoning model whose scratchpad was shaped by RL, which is the actual setting where
encoded reasoning would arise. Roger's own limitations (math only, unclear where paraphrasing sits
on the bijection-to-full-randomisation spectrum, smaller thinking budgets untested) apply to us
doubly: a 7B instruct model with no reasoning RL has had no training pressure to develop encoded
reasoning, so a null on steganography from our model says little about Claude-class models.

Our contribution is the faithfulness-by-representation measurement and the mechanistic follow-up,
not a verdict on frontier steganography.

## Practical link

Roger's paraphrase-and-distill is a candidate defence. If our Hours 10–15 probing finds
intermediates encoded at symbolic or filler positions, his method is the natural test of whether
such encodings survive paraphrasing.
