class SDocMarkup:
    HTML = "HTML"
    MARKDOWN = "Markdown"

    ALL = {HTML, MARKDOWN}

    # The markups that StrictDoc read until the Markdown-only change. A
    # document that declares one of them stops with an error that tells what
    # to do (see SDocParsingProcessor).
    REMOVED = {"RST", "Text"}
