from pathlib import Path

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfigLoader
from strictdoc.features.hierarchy.references import ReferenceResolver
from strictdoc.features.hierarchy.source import (
    IndexReferenceSource,
    build_reference_resolver,
)
from strictdoc.server.project_context import ProjectContext
from tests.support.hierarchy_fixture import write_project

CUSTOMER = """[DOCUMENT]
MID: 4444444444444444444444444444444d
TITLE: Customer specification
UID: CUSTOMER
OPTIONS:
  ENABLE_MID: True
METADATA:
  KIND: input

[[SECTION]]
MID: 5555555555555555555555555555555d
UID: SEC-SCOPE
TITLE: Scope

[REQUIREMENT]
MID: 6666666666666666666666666666666d
UID: ISIS-OBCPB-E70-01-REQ-106005
TITLE: Memory
STATEMENT: >>>
The customer wants memory.
<<<

[[/SECTION]]

[[SECTION]]
MID: 7777777777777777777777777777777d
TITLE: Interfaces (no UID)

[REQUIREMENT]
MID: 8888888888888888888888888888888d
UID: ISIS-OBCPB-E70-01-REQ-106006
TITLE: Bus
STATEMENT: >>>
The customer wants a bus.
<<<

[[/SECTION]]
"""


def _index(root: Path):
    input_path = root / "input"
    write_project(input_path)
    (input_path / "inputs").mkdir()
    (input_path / "inputs" / "customer.sdoc").write_text(
        CUSTOMER, encoding="utf8"
    )
    config = ProjectConfigLoader.load_using_server_config(
        ServerCommandConfig(
            debug=False,
            command="server",
            input_path=str(input_path),
            output_path=str(root / "output"),
            config=None,
            reload=False,
            host="127.0.0.1",
            port=8001,
        )
    )
    return ProjectContext.create(config).export_action.traceability_index


MAPPING = {"DA1": "inputs/customer", "DA2": "da.sdoc", "DA3": "CUSTOMER"}


def test_001_the_source_finds_documents_by_path_and_by_uid(tmp_path):
    source = IndexReferenceSource(_index(tmp_path), MAPPING)
    assert source.has_document("DA1")
    assert source.has_document("DA2")
    assert source.has_document("DA3")
    assert not source.has_document("DA9")
    assert sorted(source.uids_of("DA1")) == sorted(source.uids_of("DA3"))
    assert "DA-1" in source.uids_of("DA2")


def test_002_a_missing_document_is_not_found(tmp_path):
    source = IndexReferenceSource(_index(tmp_path), {"DA1": "inputs/none"})
    assert not source.has_document("DA1")


def test_003_sections_are_found_by_number_and_may_have_no_uid(tmp_path):
    source = IndexReferenceSource(_index(tmp_path), MAPPING)
    assert source.section_exists("DA1", "1")
    assert source.section_uid("DA1", "1") == "SEC-SCOPE"
    assert source.section_exists("DA1", "2")
    assert source.section_uid("DA1", "2") is None
    assert not source.section_exists("DA1", "3")


def test_004_the_resolver_works_on_the_real_index(tmp_path):
    resolver = ReferenceResolver(
        IndexReferenceSource(_index(tmp_path), MAPPING)
    )
    result = resolver.resolve(
        "[DA1] §1, REQ-106005, REQ-106006 ; §2 ; [DA2] DA-2, DA-9"
    )
    assert result.uids == [
        "SEC-SCOPE",
        "ISIS-OBCPB-E70-01-REQ-106005",
        "ISIS-OBCPB-E70-01-REQ-106006",
        "DA-2",
    ]
    assert any("has no UID" in m for m in result.unresolved)
    assert any("DA-9" in m for m in result.unresolved)


def test_005_no_applicable_documents_means_no_resolver(tmp_path):
    index = _index(tmp_path)
    assert build_reference_resolver({}, index) is None
    assert build_reference_resolver(MAPPING, index) is not None
