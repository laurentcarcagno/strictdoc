version: 1

Command: retranslate. You check that a translation keeps the meaning.

Translate the text into the "Target language", then translate your translation back into the language of the original text, without looking
at the original again. Then compare the original and the back translation sentence by sentence and list every difference of meaning (a
number, a condition, an obligation that became permission, a missing or added element). Ignore differences of style.
Keep UIDs, [LINK: ...], code and units untouched.

Answer: {"translation": "<the translation>", "back": "<the back translation>", "differences": [{"original": "words of the original", "back": "words of the back translation", "message": "what changed"}]}
