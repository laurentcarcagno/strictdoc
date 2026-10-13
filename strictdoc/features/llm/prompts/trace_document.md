version: 1

Command: trace (a whole document). You propose the parents of each requirement of the batch among the candidate requirements.

The batch is the requirements between BEGIN requirement uid=... and END in the "Requirements to link" part; the candidates are the ones in the
"Material" part, and only their UIDs may be proposed. Propose a link only when the requirement answers or refines the candidate: same subject, same
need. At most 3 links per requirement, the surest first. Skip a requirement with no candidate.

Answer: {"links": [{"node": "FSW-3", "uid": "DA-12", "reason": "one sentence"}]}
