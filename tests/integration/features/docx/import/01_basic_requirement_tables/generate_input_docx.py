"""
Regenerates input.docx for this test. Not run by the test itself.

    PYTHONPATH=. python tests/integration/features/docx/import/<this folder>/generate_input_docx.py
"""

import os

from tests.unit.strictdoc.backend.docx.docx_builder import (
    cell,
    deleted,
    inserted,
    paragraph,
    row,
    run,
    table,
    write_docx,
)


def requirement(uid, title, version, linked, text, note="Note :"):
    return table(
        row(cell(paragraph(uid, style="ReqId"))),
        row(cell(paragraph(title, style="ReqTitle"))),
        row(cell(paragraph("Version:")), cell(paragraph(version))),
        row(cell(paragraph("Verified by:")), cell(paragraph("T"))),
        row(cell(paragraph("Linked Req:")), cell(paragraph(linked))),
        row(cell(*[paragraph(text_, style="ReqText") for text_ in text])),
        row(cell(paragraph(note))),
    )


here = os.path.dirname(os.path.abspath(__file__))
write_docx(
    os.path.join(here, "input.docx"),
    [
        paragraph("1 Introduction .... 3", style="TOC1"),
        paragraph("Introduction", style="Heading1"),
        paragraph("This document describes the system."),
        paragraph(
            run("It has ") + run("two", bold=True) + run(" requirements.")
        ),
        paragraph("Requirements", style="Heading1"),
        paragraph("Functional", style="Heading2"),
        requirement(
            "SYS-0001",
            "Power on",
            "V1",
            "[DA1] REQ-12",
            ["The system shall power on."],
        ),
        requirement(
            "SYS-0002",
            "Power on delay",
            "V0",
            "SYS-0001, SYS-0099",
            [
                "The power-on delay shall not exceed:",
            ],
        ),
        paragraph("Notes", style="Heading2"),
        paragraph("The delay is measured at the connector."),
        paragraph("first item", list_item=True),
        paragraph("second item", list_item=True),
        table(
            row(cell(paragraph("Mode")), cell(paragraph("Delay"))),
            row(cell(paragraph("Nominal")), cell(paragraph("2 s"))),
        ),
        paragraph(
            run("Kept. ") + inserted(run("Inserted. ")) + deleted("Deleted.")
        ),
    ],
)
