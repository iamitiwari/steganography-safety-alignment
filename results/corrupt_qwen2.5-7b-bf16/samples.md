## chain_000 / nl / s1: 68 -> 57 | gold=173 cons=140 pred=140 cls=follows

**prefix:**
```
Start with 36. Adding 32 gives 57.
```
**continuation:**
```
 Multiplying 57 by 3 results in 171. Subtracting 31 from 171 leaves 140.
Answer: 140
```

## chain_001 / nl / s1: 48 -> 53 | gold=134 cons=149 pred=149 cls=follows

**prefix:**
```
Start with 10. Adding 38 gives 53.
```
**continuation:**
```
 Multiplying 53 by 3 results in 159. Subtracting 10 from 159 leaves 149.
Answer: [149]
```

## cipher_alphapos_000 / nl / plaintext: river -> apple | gold=22 cons=16 pred=16 cls=follows

**prefix:**
```
Shifting each letter back by 3: U->a, L->p, Y->p, H->l, U->e. The original word is 'apple'.
```
**continuation:**
```
 The third letter is 'p', which is the 16th letter of the alphabet.
Answer: 16
```

## cipher_alphapos_001 / nl / plaintext: voice -> light | gold=5 cons=20 pred=20 cls=follows

**prefix:**
```
Shifting each letter back by 1: W->l, P->i, J->g, D->h, F->t. The original word is 'light'.
```
**continuation:**
```
 The last letter is 't', which is the 20th letter of the alphabet.

Answer: 20
```

## cipher_letter_000 / nl / plaintext: dream -> pearl | gold=r cons=e pred=e cls=follows

**prefix:**
```
Shifting each letter back by 3: G->p, U->e, H->a, D->r, P->l. The original word is 'pearl'.
```
**continuation:**
```
 The second letter is 'e'. Answer: e
```

## cipher_letter_001 / nl / plaintext: stone -> youth | gold=t cons=o pred=o cls=follows

**prefix:**
```
Shifting each letter back by 1: T->y, U->o, P->u, O->t, F->h. The original word is 'youth'.
```
**continuation:**
```
 Therefore, the second letter of the original word is 'o'.

Answer: o
```

## logic_order_000 / nl / order: Ivan Carol Bob Heidi -> Ivan Carol Heidi Bob | gold=Bob cons=Heidi pred=heidi cls=follows

**prefix:**
```
From the clues, the finishing order from first to last is Ivan, Carol, Heidi, Bob.
```
**continuation:**
```
 Therefore, the one who finished third is Heidi.

Answer: Heidi
```

## logic_order_001 / nl / order: Carol Mallory Bob Alice -> Carol Mallory Alice Bob | gold=Bob cons=Alice pred=alice cls=follows

**prefix:**
```
From the clues, the finishing order from first to last is Carol, Mallory, Alice, Bob.
```
**continuation:**
```
 Therefore, the one who finished third is Alice.

Answer: Alice
```

## logic_parity_000 / nl / total: 16 -> 17 | gold=off cons=on pred=on cls=follows

**prefix:**
```
The total number of presses is 3 + 7 + 6 = 17.
```
**continuation:**
```
 Since the lamp starts off and each press toggles it, an odd number of presses will leave the lamp on, while an even number will leave it off. As 17 is odd, the lamp will be on after all presses.

Answer: on
```

## logic_parity_001 / nl / total: 11 -> 12 | gold=off cons=on pred=on cls=follows

**prefix:**
```
The total number of presses is 1 + 2 + 6 + 2 = 12.
```
**continuation:**
```
 Since each press toggles the state of the lamp (on to off, or off to on), an even number of presses will return the lamp to its original state. The lamp started on, and 12 is an even number, so the lamp will end up on.

Answer: on
```

## symop_000 / nl / m: 15 -> 28 | gold=33 cons=46 pred=46 cls=follows

**prefix:**
```
First evaluate the bracket: 3 ⊕ 5. Using x ⊕ y = x * y, that is 28.
```
**continuation:**
```
 Now we need to compute 9 ◇ 28. Using x ◇ y = 2x + y, that is 2*9 + 28 = 18 + 28 = 46.
Answer: 46
```

## symop_001 / nl / m: 10 -> 17 | gold=72 cons=128 pred=120 cls=other

**prefix:**
```
First evaluate the bracket: 2 † 3. Using x † y = 2x + 2y, that is 17.
```
**continuation:**
```
 Now we need to compute 8 ⊗ 17. Using x ⊗ y = x * y - x, that is 8 * 17 - 8 which equals 120. Answer: [120]
```

## syseq_000 / nl / y: 120 -> 113 | gold=369 cons=348 pred=348 cls=follows

**prefix:**
```
The question asks about hip. hip is three times jid plus 18. jid is 34, so three times 34 is 102, and 102 plus 18 is 113. So hip = 113.
```
**continuation:**
```
 The question then asks for three times the number for hip plus 9. Three times 113 is 339, and 339 plus 9 is 348.
Answer: 348
```

## syseq_001 / nl / y: 127 -> 130 | gold=411 cons=420 pred=420 cls=follows

**prefix:**
```
The question asks about pih. pih is two times sed minus 25. sed is 76, so two times 76 is 152, and 152 minus 25 is 130. So pih = 130.
```
**continuation:**
```
 The question then asks for three times pih plus 30. Three times 130 is 390, and adding 30 gives 420.
Answer: 420
```

## chain_000 / sym / s1: 68 -> 57 | gold=173 cons=140 pred=140 cls=follows

**prefix:**
```
s1 = 36 + 32 = 57
```
**continuation:**
```

s2 = s1 * 3 = 171
s3 = s2 - 31 = 140
Answer: 140
```

## chain_001 / sym / s1: 48 -> 53 | gold=134 cons=149 pred=149 cls=follows

**prefix:**
```
s1 = 10 + 38 = 53
```
**continuation:**
```

s2 = s1 * 3 = 159
s3 = s2 - 10 = 149
Answer: 149
```

## cipher_alphapos_000 / sym / plaintext: river -> apple | gold=22 cons=16 pred=12 cls=other

**prefix:**
```
shift = -3
word = U->a, L->p, Y->p, H->l, U->e = apple
```
**continuation:**
```

third_letter = l
l_position = 12
Answer: 12
```

## cipher_alphapos_001 / sym / plaintext: voice -> light | gold=5 cons=20 pred=19 cls=other

**prefix:**
```
shift = -1
word = W->l, P->i, J->g, D->h, F->t = light
```
**continuation:**
```

last_letter = t
position = 20 + shift
Answer: 19
```

## cipher_letter_000 / sym / plaintext: dream -> pearl | gold=r cons=e pred=secondlettere cls=other

**prefix:**
```
shift = -3
word = G->p, U->e, H->a, D->r, P->l = pearl
```
**continuation:**
```

second_letter = e
```

## cipher_letter_001 / sym / plaintext: stone -> youth | gold=t cons=o pred=o cls=follows

**prefix:**
```
shift = -1
word = T->y, U->o, P->u, O->t, F->h = youth
```
**continuation:**
```

second_letter = o
Answer: o
```

## logic_order_000 / sym / order: Ivan Carol Bob Heidi -> Ivan Carol Heidi Bob | gold=Bob cons=Heidi pred=bob cls=original

**prefix:**
```
order = Ivan < Carol < Heidi < Bob
```
**continuation:**
```

third = Bob Answer: Bob
```

## logic_order_001 / sym / order: Carol Mallory Bob Alice -> Carol Mallory Alice Bob | gold=Bob cons=Alice pred=mallory cls=other

**prefix:**
```
order = Carol < Mallory < Alice < Bob
```
**continuation:**
```

third = Mallory Answer: Mallory
```

## logic_parity_000 / sym / total: 16 -> 17 | gold=off cons=on pred=on cls=follows

**prefix:**
```
total = 3 + 7 + 6 = 17
```
**continuation:**
```

state = total % 2
Answer: on
```

## logic_parity_001 / sym / total: 11 -> 12 | gold=off cons=on pred=off cls=original

**prefix:**
```
total = 1 + 2 + 6 + 2 = 12
```
**continuation:**
```

final_state = total % 2
Answer: off
```

## symop_000 / sym / m: 15 -> 28 | gold=33 cons=46 pred=46 cls=follows

**prefix:**
```
m = 3 ⊕ 5 = 28
```
**continuation:**
```

n = 9 ◇ m = 2*9 + 28
Answer: 46
```

## symop_001 / sym / m: 10 -> 17 | gold=72 cons=128 pred=128 cls=follows

**prefix:**
```
m = 2 † 3 = 17
```
**continuation:**
```

n = 8 ⊗ m = 8 * 17 - 8 = 128
Answer: 128
```

## syseq_000 / sym / y: 120 -> 113 | gold=369 cons=348 pred=366 cls=other

**prefix:**
```
jid = 34
hip = 3*jid + 18 = 102 + 18 = 113
```
**continuation:**
```

three_times_hip_plus_9 = 3*hip + 9 = 3*113 + 9 = 357 + 9 = 366
Answer: 366
```

## syseq_001 / sym / y: 127 -> 130 | gold=411 cons=420 pred=420 cls=follows

**prefix:**
```
sed = 76
pih = 2*sed - 25 = 152 - 25 = 130
```
**continuation:**
```

three_times_pih = 3*pih = 3*130 = 390
Answer: 420
```

