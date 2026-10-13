version: 1

Command: consistency. You look for inconsistencies between the requirements of the material.

Report only real ones, at most 8, the most serious first: a contradiction (two requirements that cannot both be true), a duplicate (the same
requirement twice), a term used with two meanings or two terms for one thing, a number or unit that differs for the same quantity. For each: a
severity (error for a contradiction, warning otherwise), the UIDs concerned in the message, and a one-line suggestion. The "quote" is
always empty. If there is none, return an empty list.

Answer: {"verdict": "pass|warn|fail", "findings": [{"severity": "error|warning|info", "rule": "R-CONSISTENCY", "quote": "", "message": "REQ-1 and REQ-7 give different boot times (2 s, 5 s).", "suggestion": "..."}]}
