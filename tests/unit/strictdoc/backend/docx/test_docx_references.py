import os

from strictdoc.backend.docx.import_.docx_reader import (
    DocxReader,
    TrackedChangesMode,
)
from strictdoc.backend.docx.import_.docx_to_sdoc_converter import (
    DocxToSDocConverter,
)
from strictdoc.features.hierarchy.references import (
    DictSource,
    ReferenceResolver,
)
from tests.unit.strictdoc.backend.docx.docx_builder import write_docx
from tests.unit.strictdoc.backend.docx.test_docx_to_sdoc_converter import (
    _nodes,
    _requirement,
    _requirement_table_profile,
)

SOURCE = DictSource(
    uids={
        "DA1": ["ISIS-PUS-REQ-1420"],
        "DA2": ["ISIS-OBCPB-E70-01-REQ-106005", "ISIS-OBCPB-E70-01-REQ-106006"],
    },
    sections={"DA1": {"5.14.1": "SEC-5-14-1"}},
)


def _import(tmp_path, blocks, resolver=None):
    path = os.path.join(str(tmp_path), "input.docx")
    write_docx(path, blocks)
    docx_blocks = DocxReader.read(path, TrackedChangesMode.ACCEPT)
    text, report = DocxToSDocConverter.build_sdoc_text(
        docx_blocks,
        _requirement_table_profile(),
        "My title",
        None,
        resolver,
    )
    return text, DocxToSDocConverter.parse(text), report


def _parents(node):
    return [r.ref_uid for r in node.relations]


def test_001_references_to_applicable_documents_become_parent_relations(
    tmp_path,
):
    resolver = ReferenceResolver(SOURCE).resolve
    text, document, report = _import(
        tmp_path,
        [
            _requirement(
                "REQ-0001",
                linked="[DA1] §5.14.1 ; [DA2] REQ-106005, REQ-106006",
            )
        ],
        resolver,
    )
    assert _parents(_nodes(document)[0]) == [
        "SEC-5-14-1",
        "ISIS-OBCPB-E70-01-REQ-106005",
        "ISIS-OBCPB-E70-01-REQ-106006",
    ]
    assert report.references_resolved == 3
    assert "Links to applicable documents: 3" in report.format()
    # The text of the column is kept as it was.
    assert "LINKED_REQ: [DA1] §5.14.1 ; [DA2] REQ-106005, REQ-106006" in text


def test_002_what_cannot_be_resolved_is_reported_and_kept_in_the_text(tmp_path):
    resolver = ReferenceResolver(SOURCE).resolve
    text, document, report = _import(
        tmp_path,
        [_requirement("REQ-0001", linked="[DA2] REQ-1 ; [DA9] REQ-2")],
        resolver,
    )
    assert _parents(_nodes(document)[0]) == []
    assert len(report.unresolved_links) == 2
    assert report.unresolved_links[0][0] == "REQ-0001"
    assert "no such requirement in DA2" in report.unresolved_links[0][1]
    assert "LINKED_REQ: [DA2] REQ-1 ; [DA9] REQ-2" in text


def test_003_links_inside_the_document_still_work_with_a_resolver(tmp_path):
    resolver = ReferenceResolver(SOURCE).resolve
    _, document, report = _import(
        tmp_path,
        [
            _requirement("REQ-0001"),
            _requirement(
                "REQ-0002", linked="REQ-0001 ; [DA1] ISIS-PUS-REQ-1420"
            ),
        ],
        resolver,
    )
    assert _parents(_nodes(document)[1]) == ["REQ-0001", "ISIS-PUS-REQ-1420"]


def test_004_without_a_resolver_the_import_is_unchanged(tmp_path):
    _, document, report = _import(
        tmp_path,
        [_requirement("REQ-0001", linked="[DA1] ISIS-PUS-REQ-1420")],
    )
    assert _parents(_nodes(document)[0]) == []
    assert report.references_resolved == 0
    assert report.unresolved_links == []
