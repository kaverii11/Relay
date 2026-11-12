# Code check vs model check vs K's grade, eval_day1_20261111_124523

Drafts with a check: 35 (code OK 27, code FAIL 8; of the code-OK ones, model OK 27, model FAIL 0).
(1) Wrong answers let through: code + model (real run) 6; code-only would have sent 6 wrong, 21 correct, 0 ungraded (rejected drafts K did not grade).
    Model check rejections: 0 graded wrong (caught), 0 graded correct (false rejections), 0 ungraded.
(2) Correct drafts the code check rejected: 3 (of 8 code rejections; 5 graded wrong, 0 ungraded).

| question x setting | round | code check | model check | sent | grade of this draft | code-only sends it |
|---|---|---|---|---|---|---|
| Q57 x medium_rerank | 0 | OK | OK | yes | wrong | yes |
| Q14 x medium_rerank | 0 | OK | OK | yes | correct | yes |
| Q26 x medium_rerank | 0 | FAIL | not run | no | correct | no |
| Q26 x medium_rerank | 1 | OK | OK | yes | correct | yes |
| Q40 x medium_rerank | 0 | OK | OK | yes | correct | yes |
| Q15 x medium_rerank | 0 | OK | OK | yes | correct | yes |
| Q35 x medium_rerank | 0 | OK | OK | yes | correct | yes |
| Q8 x medium_rerank | 0 | FAIL | not run | no | correct | no |
| Q8 x medium_rerank | 1 | OK | OK | yes | correct | yes |
| Q18 x medium_rerank | 0 | OK | OK | yes | wrong | yes |
| Q25 x medium_rerank | 0 | OK | OK | yes | correct | yes |
| Q4 x medium_rerank | 0 | FAIL | not run | no | wrong | no |
| Q4 x medium_rerank | 1 | OK | OK | yes | wrong | yes |
| Q14 x medium_norerank | 0 | OK | OK | yes | correct | yes |
| Q26 x medium_norerank | 0 | OK | OK | yes | correct | yes |
| Q40 x medium_norerank | 0 | OK | OK | yes | correct | yes |
| Q35 x medium_norerank | 0 | FAIL | not run | no | correct | no |
| Q35 x medium_norerank | 1 | OK | OK | yes | correct | yes |
| Q8 x medium_norerank | 0 | OK | OK | yes | correct | yes |
| Q18 x medium_norerank | 0 | FAIL | not run | no | wrong | no |
| Q18 x medium_norerank | 1 | FAIL | not run | no | wrong | no |
| Q25 x medium_norerank | 0 | OK | OK | yes | correct | yes |
| Q4 x medium_norerank | 0 | OK | OK | yes | correct | yes |
| Q9 x medium_norerank | 0 | OK | OK | yes | wrong | yes |
| Q14 x medium_k3_norerank | 0 | OK | OK | yes | correct | yes |
| Q26 x medium_k3_norerank | 0 | OK | OK | yes | correct | yes |
| Q40 x medium_k3_norerank | 0 | OK | OK | yes | correct | yes |
| Q15 x medium_k3_norerank | 0 | FAIL | not run | no | wrong | no |
| Q15 x medium_k3_norerank | 1 | FAIL | not run | no | wrong | no |
| Q35 x medium_k3_norerank | 0 | OK | OK | yes | correct | yes |
| Q8 x medium_k3_norerank | 0 | OK | OK | yes | correct | yes |
| Q18 x medium_k3_norerank | 0 | OK | OK | yes | wrong | yes |
| Q25 x medium_k3_norerank | 0 | OK | OK | yes | correct | yes |
| Q4 x medium_k3_norerank | 0 | OK | OK | yes | correct | yes |
| Q9 x medium_k3_norerank | 0 | OK | OK | yes | wrong | yes |
