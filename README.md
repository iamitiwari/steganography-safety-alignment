# steganography-safety-alignment
Couple of things to test -- does model encode relevant info in non natural language symbolic representation? are these representations genuinly helping the model reason its way through task ? Is there a scope of deception (hiding sensitive/harmful information) in these represenations? Can CoT be judged using these represenatations.


# Core Safety Motivation
Safety monitoring assumes that reading a reasoning model’s Chain-of-Thought (CoT) provides an auditable, legible record of its cognitive process. If an LLM instead develops an internal, obfuscated symbolic shorthand (or steganographic encoding), it can coordinate or reason secretly, evading human or automated monitors while showing a clean surface output.  
# Concrete Project Angle
## Symbolic vs. Natural CoT Faithfulness
 Compare causal reliance across formats. If you force a model (e.g., Qwen 2.5/3.5 or DeepSeek-R1-Distill) to reason via dense symbolic pseudo-code/abstract notation vs. standard English CoT, does its faithfulness decline? Intervene on intermediate reasoning tokens using resampling or thought anchors (swapping or masking intermediate lines) to determine whether the final answer changes or if the model simply corrects around it.
 ##  Decoding Steganographic / Cipher CoT
  Prompt or fine-tune a model to use a cipher or non-natural token grammar to solve a multi-step task it fails in zero-shot. Test whether linear probing or a J-Lens / template lens on residual stream layers can extract the true plaintext intermediate values before the token itself is generated.
  ##  Filler Tokens as a Steganography Benchmark
   As highlighted by Brauer et al. (2026, Reading between the Dots), content-free dots ... act as an extreme limit case of behavioral evasion. Check whether modern models build multi-hop semantic state in their activations across these tokens, and test whether patching a random vector breaks the downstream computation.
#  How to Execute Within 16–20 Hours
## Hours 0–3:
Set up a modern model (e.g., Qwen 2.5 7B or DeepSeek-R1-Distill-7B/8B) on RunPod/Vast.ai. Generate a clean synthetic dataset of 100–200 reasoning tasks (math, logic puzzles, or cipher tasks).
##  Hours 4–9:
 Establish baselines. Run prompt variants: (1) Standard CoT, (2) Non-natural symbolic representation, (3) Filler tokens (...), (4) Zero-shot. Apply causal resampling: corrupt intermediate sentences or symbolic operators and record the downstream logit changes.  
 
## Hours 10–15:
 Run mechanistic probes. Train simple linear probes or use J-Lens on the residual stream at intermediate positions to test if latent semantics exist where surface tokens look uninformative. Always compare against a random baseline direction   
 ## Hours 16–18:
  Sanity-check every headline number yourself; inspect raw prompt completions manually.  
## Hours 19–20 (Distillation):
Write the 1-page executive summary and application questions by hand.  