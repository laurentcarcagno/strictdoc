"""
Regenerates input.docx for this test. Not run by the test itself.

    PYTHONPATH=. python tests/integration/features/docx/import/<this folder>/generate_input_docx.py

The Word document changed since the SDoc file in this folder was written:
SYS-0001 has a new version and statement, SYS-0002 is gone, SYS-0003 is new.
"""

import os

from tests.unit.strictdoc.backend.docx.docx_builder import (
    cell,
    paragraph,
    row,
    table,
    write_docx,
)


def requirement(uid, title, version, linked, text):
    return table(
        row(cell(paragraph(uid, style="ReqId"))),
        row(cell(paragraph(title, style="ReqTitle"))),
        row(cell(paragraph("Version:")), cell(paragraph(version))),
        row(cell(paragraph("Verified by:")), cell(paragraph("T"))),
        row(cell(paragraph("Linked Req:")), cell(paragraph(linked))),
        row(cell(paragraph(text, style="ReqText"))),
        row(cell(paragraph("Note :"))),
    )


here = os.path.dirname(os.path.abspath(__file__))
write_docx(
    os.path.join(here, "input.docx"),
    [
        paragraph("Requirements", style="Heading1"),
        requirement(
            "SYS-0001", "Power on", "V2", "-", "The system shall power on fast."
        ),
        requirement(
            "SYS-0003", "Shutdown", "V0", "SYS-0001", "The system shall stop."
        ),
    ],
)
