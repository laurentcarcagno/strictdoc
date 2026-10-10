# Golden set report: golden qwen2.5:3b

8 of 20 cases pass all the rules.

| Case | Result | Seconds | Calls | Output tokens | Problems |
|---|---|---|---|---|---|
| fr-01 | FAIL | 1.9 | 1 | 94 | 1 proposal(s), expected 2 to 4; #1: no 'shall'/'doit' in the statement |
| fr-02 | FAIL | 0.6 | 1 | 81 | #1: no 'shall'/'doit' in the statement |
| fr-03 | FAIL | 0.8 | 1 | 104 | #1: no 'shall'/'doit' in the statement |
| fr-04 | FAIL | 0.8 | 1 | 108 | #1: no 'shall'/'doit' in the statement; #1: number(s) not in the material: 0050, 18 |
| fr-05 | FAIL | 1.4 | 1 | 186 | #1: no 'shall'/'doit' in the statement; #2: no 'shall'/'doit' in the statement |
| fr-06 | FAIL | 0.7 | 1 | 95 | #1: no 'shall'/'doit' in the statement |
| fr-07 | FAIL | 0.9 | 1 | 115 | #1: no 'shall'/'doit' in the statement |
| fr-08 | FAIL | 0.9 | 1 | 124 | #1: no 'shall'/'doit' in the statement |
| fr-09 | FAIL | 0.7 | 1 | 90 | #1: no 'shall'/'doit' in the statement |
| fr-10 | FAIL | 0.6 | 1 | 73 | #1: no 'shall'/'doit' in the statement |
| en-01 | pass | 1.6 | 1 | 215 |  |
| en-02 | pass | 0.6 | 1 | 76 |  |
| en-03 | pass | 0.5 | 1 | 67 |  |
| en-04 | FAIL | 0.7 | 1 | 87 | #1: no 'shall'/'doit' in the statement |
| en-05 | pass | 0.6 | 1 | 76 |  |
| en-06 | FAIL | 0.5 | 1 | 68 | 1 proposal(s), expected 2 to 4 |
| en-07 | pass | 0.6 | 1 | 75 |  |
| en-08 | pass | 0.9 | 1 | 120 |  |
| en-09 | pass | 0.6 | 1 | 73 |  |
| en-10 | pass | 0.4 | 1 | 46 |  |

Total time: 16 s.
