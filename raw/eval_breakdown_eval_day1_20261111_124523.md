# Eval breakdown, eval_day1_20261111_124523 (results.csv + event logs + K's grades)

## Per question across the three settings

| question | type | answerable | 250/6 re-rank | 250/6 no re-rank | 250/3 no re-rank | changed with setting |
|---|---|---|---|---|---|---|
| Q57 | cross-paper (needs two papers) | yes | WRONG (answer, B05) | REF. WRONG (refusal, B28) | REF. WRONG (refusal, B37) | **yes** |
| Q14 | reworded | yes | correct (answer, B45) | correct (answer, B55) | correct (answer, B56) | no |
| Q43 | verbatim | yes | REF. WRONG (refusal, B39) | REF. WRONG (refusal, B53) | REF. WRONG (refusal, B32) | no |
| Q12 | Unanswerable (Number Not Reported) | no | ref. ok (refusal, B46) | ref. ok (refusal, B30) | ref. ok (refusal, B09) | no |
| Q26 | reworded; cross-paper collision | yes | correct (answer, B29) | correct (answer, B08) | correct (answer, B41) | no |
| Q40 | reworded | yes | correct (answer, B48) | correct (answer, B22) | correct (answer, B07) | no |
| Q45 | Unanswerable (Not in papers) | no | ref. ok (refusal, B31) | ref. ok (refusal, B50) | ref. ok (refusal, B34) | no |
| Q49 | Unanswerable (Not in papers) | no | ref. ok (refusal, B20) | ref. ok (refusal, B25) | ref. ok (refusal, B02) | no |
| Q15 | reworded; cross-paper collision | yes | correct (answer, B13) | REF. WRONG (refusal, B36) | REF. WRONG (unverified, B52) | **yes** |
| Q35 | reworded | yes | correct (answer, B43) | correct (answer, B58) | correct (answer, B11) | no |
| Q48 | Unanswerable (Not in papers) | no | ref. ok (refusal, B40) | ref. ok (refusal, B38) | ref. ok (refusal, B24) | no |
| Q32 | Unanswerable (False Premise) | no | WRONG (refusal, B60) | WRONG (refusal, B10) | WRONG (refusal, B21) | no |
| Q7 | reworded | yes | REF. WRONG (refusal, B06) | REF. WRONG (refusal, B54) | REF. WRONG (refusal, B16) | no |
| Q34 | Unanswerable (Comparison Not Made) | no | ref. ok (refusal, B51) | ref. ok (refusal, B19) | ref. ok (refusal, B17) | no |
| Q8 | reworded | yes | correct (answer, B27) | correct (answer, B49) | correct (answer, B42) | no |
| Q47 | Unanswerable (Not in papers); cross-paper collision | no | ref. ok (refusal, B57) | ref. ok (refusal, B04) | ref. ok (refusal, B18) | no |
| Q18 | verbatim | yes | WRONG (answer, B12) | REF. WRONG (unverified, B03) | WRONG (answer, B59) | **yes** |
| Q25 | reworded | yes | correct (answer, B35) | correct (answer, B47) | correct (answer, B01) | no |
| Q4 | reworded | yes | WRONG (answer, B14) | correct (answer, B23) | correct (answer, B44) | **yes** |
| Q9 | verbatim | yes | REF. WRONG (refusal, B15) | WRONG (answer, B26) | WRONG (answer, B33) | **yes** |

Questions whose grade changed with the setting: 5 of 20.

## §8: model check vs K's grade (drafts that passed the code check)

| model check | graded correct | graded wrong |
|---|---|---|
| passed | 21 | 6 |
| rejected | 0 | 0 |

## §8: every code-check rejection

| entry | draft | K's grade of the draft | cause | failing quote | K's note |
|---|---|---|---|---|---|
| B03 | 0 | wrong | not found | 'Maximum Path Length O(logk(n))' | wrong  # missing O(n/k) |
| B03 | 1 | wrong | length | 'O(logk(n))' | wrong  # missing O(n/k) |
| B14 | 0 | wrong | not found | 'During training (blue part, top), we distill non-causal embeddings fro' | wrong  # same claim |
| B27 | 0 | correct | splice | 'SpeechTokenizer 16kHz 50Hz 1.5kbps 3.3% ... 45.1±1.5' | correct  # right claim; failed only on "..." splice |
| B29 | 0 | correct | not found | 'the smoothing module applies an exponential moving average (EMA) with ' | correct  # right claim; quote rewritten in LaTeX, so not verbatim |
| B52 | 0 | wrong | splice | 'h ... 8 4.88 25.5 80 256 32 32' | wrong  # "8" is from the N (layers) rows of Table 3, not h; also a splice |
| B52 | 1 | wrong | length | '8 4.88 25.5' | wrong  # same wrong row; rejected only by the 12-char rule |
| B58 | 0 | correct | splice | 'we compare the default Downsample operation of H-Net ... against three' | correct  # right claim; failed only on "..." splice |

Code-check rejections by grade and cause: correct / not found: 1, correct / splice: 2, wrong / length: 2, wrong / not found: 2, wrong / splice: 1
