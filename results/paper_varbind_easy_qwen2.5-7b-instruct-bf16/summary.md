Paper varbind (easy) on qwen2.5-7b-instruct-bf16; n=500; 5 few-shot (paper's held-out pool); temp 0

| condition | accuracy | Δ vs baseline | wrong→right | right→wrong | max prompt tokens |
|---|---|---|---|---|---|
| baseline | 0.4% | +0.0 | 0 | 0 | 596 |
| dots_5 | 0.8% | +0.4 | 3 | 1 | 672 |
| dots_10 | 0.6% | +0.2 | 2 | 1 | 702 |
| dots_25 | 1.0% | +0.6 | 3 | 0 | 792 |
| dots_50 | 0.4% | +0.0 | 1 | 1 | 942 |
| dots_100 | 0.2% | -0.2 | 0 | 1 | 1242 |
| dots_250 | 0.2% | -0.2 | 0 | 1 | 2142 |
| counting_5 | 0.8% | +0.4 | 2 | 0 | 709 |
| counting_10 | 0.6% | +0.2 | 1 | 0 | 775 |
| counting_25 | 0.6% | +0.2 | 2 | 1 | 1045 |
| counting_50 | 0.4% | +0.0 | 1 | 1 | 1495 |
| alphabet_10 | 0.4% | +0.0 | 1 | 1 | 713 |
| alphabet_25 | 0.6% | +0.2 | 1 | 0 | 803 |
| alphabet_100 | 0.2% | -0.2 | 0 | 1 | 1253 |

unparsed: {}
wall-clock: 69s
