version: 1

Command: test. You propose how to verify the requirement.

Choose the verification method among the ones given in the "verification_method" line when there is one (A analysis, I inspection, R review,
T test, or the project's own); otherwise say it in words. Then write at most 5 acceptance cases that a test engineer can run: each has a
name, the initial condition (given), the stimulus (when) and the expected result with its value and unit (then). Cases cover the nominal
behaviour, the limits stated in the text, and one failure case when the text implies one. Use only values and conditions of the text and the
material; write TBD for what is missing.

Answer: {"verification_method": "T", "cases": [{"name": "...", "given": "...", "when": "...", "then": "..."}]}
