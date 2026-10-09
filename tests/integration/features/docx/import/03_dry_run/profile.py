from strictdoc.backend.docx.docx_profile import (
    DocxProfile,
    DocxRequirementTable,
)


def create_profile() -> DocxProfile:
    return DocxProfile(
        requirement_table=DocxRequirementTable(
            id_style="ReqId",
            title_style="ReqTitle",
            meta_rows={
                "Version:": "VERSION",
                "Verified by:": "VERIFIED_BY",
                "Linked Req:": "LINKED_REQ",
            },
            text_style="ReqText",
            note_label="Note",
            relation_fields=["LINKED_REQ"],
        ),
    )
