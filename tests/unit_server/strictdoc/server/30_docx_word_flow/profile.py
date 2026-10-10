from strictdoc.backend.docx.docx_profile import (
    DocxProfile,
    DocxRequirementTable,
)


def create_profile() -> DocxProfile:
    return DocxProfile(
        heading_styles={"Heading1": 1},
        requirement_table=DocxRequirementTable(
            id_style="ReqId",
            title_style="ReqTitle",
            meta_rows={"Version:": "VERSION"},
            text_style="ReqText",
            note_label="Note",
        ),
    )
