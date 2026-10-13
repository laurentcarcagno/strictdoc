version: 1

Command: translate (a whole document, one batch). You translate the texts of the nodes of a document into the "Target language".

The nodes are given as a JSON list between BEGIN nodes and END: each has a "ref" and its "fields" (field name to text). Answer with the same
refs and the same field names, each text translated. Never change a ref or a field name.

Keep exactly as they are: UIDs (such as REQ-12 or DA1), links like [LINK: ...] and anchors like [ANCHOR: ...], code in backticks, numbers, units,
identifiers, acronyms and the Markdown or reStructuredText structure (lists, tables, emphasis, directives). Write the verb of obligation of
the target language: exactly "shall" in English, "doit" or "doivent" in French. If a technical term has an established translation, use it; otherwise keep the
original term. Translate every sentence; add and omit nothing.

Answer: {"nodes": [{"ref": "n3", "fields": {"TITLE": "...", "STATEMENT": "..."}}]}
