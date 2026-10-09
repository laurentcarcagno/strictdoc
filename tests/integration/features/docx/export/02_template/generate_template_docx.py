"""
Regenerates input/template.docx for this test. Not run by the test itself.

    python tests/integration/features/docx/export/02_template/generate_template_docx.py
"""

import os
import zipfile

BODY = (
    '<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>COVER PAGE</w:t></w:r></w:p>'
    "<w:p><w:r>"
    '<w:fldChar w:fldCharType="begin"/></w:r><w:r>'
    '<w:instrText xml:space="preserve"> TOC \\o "1-3" </w:instrText></w:r><w:r>'
    '<w:fldChar w:fldCharType="end"/></w:r></w:p>'
    '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Template chapter</w:t></w:r></w:p>'
    "<w:tbl><w:tblPr/><w:tblGrid/>"
    '<w:tr><w:tc><w:p><w:pPr><w:pStyle w:val="ReqId"/><w:shd w:val="clear" w:fill="D9E2F3"/></w:pPr>'
    "<w:r><w:t>ID</w:t></w:r></w:p></w:tc></w:tr>"
    '<w:tr><w:tc><w:p><w:pPr><w:pStyle w:val="ReqTitle"/></w:pPr><w:r><w:t>T</w:t></w:r></w:p></w:tc></w:tr>'
    "<w:tr><w:tc><w:p><w:r><w:t>Version:</w:t></w:r></w:p></w:tc><w:tc><w:p/></w:tc></w:tr>"
    "<w:tr><w:tc><w:p><w:r><w:t>Verified by:</w:t></w:r></w:p></w:tc><w:tc><w:p/></w:tc></w:tr>"
    "<w:tr><w:tc><w:p><w:r><w:t>Linked Req:</w:t></w:r></w:p></w:tc><w:tc><w:p/></w:tc></w:tr>"
    '<w:tr><w:tc><w:p><w:pPr><w:pStyle w:val="ReqText"/></w:pPr><w:r><w:t>S</w:t></w:r></w:p></w:tc></w:tr>'
    "<w:tr><w:tc><w:p><w:r><w:t>Note :</w:t></w:r></w:p></w:tc></w:tr>"
    "</w:tbl>"
    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>'
)
DOCUMENT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
    f'2006/main"><w:body>{BODY}</w:body></w:document>'
)
SETTINGS = (
    '<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
    '2006/main"><w:zoom w:percent="100"/><w:compat/></w:settings>'
)
here = os.path.dirname(os.path.abspath(__file__))
with zipfile.ZipFile(
    os.path.join(here, "input", "template.docx"), "w"
) as package:
    package.writestr("word/document.xml", DOCUMENT)
    package.writestr("word/settings.xml", SETTINGS)
