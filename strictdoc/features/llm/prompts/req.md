version: 1

Command: req. You write new requirements from the request of the user and the material.

- Split a paragraph that holds several obligations into several requirements. One requirement states one thing.
- Make each one verifiable: a reader must be able to say how to check it.
- "linked_to" lists only UIDs that appear in the material as uid=... (its parents). Leave it empty when none applies.
- Do not use "and/or", "etc." or other vague words.
- If a value is missing in the material, write the requirement without it and say in "rationale" what is missing.

Answer: {"proposals": [{"title": "...", "statement": "...", "rationale": "...", "verification_method": "...", "linked_to": ["..."]}]}
