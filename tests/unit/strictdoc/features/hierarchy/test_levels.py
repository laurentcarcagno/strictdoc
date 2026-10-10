import pytest

from strictdoc.backend.sdoc.models.document_config import (
    DocumentConfig,
    DocumentCustomMetadata,
    DocumentCustomMetadataKeyValuePair,
)
from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.hierarchy.levels import (
    InputInfo,
    Level,
    document_kind,
    document_metadata,
    input_info,
    is_input_document,
    relation_violation,
    validate_hierarchy,
)
from strictdoc.helpers.exception import StrictDocException

LEVELS = [
    Level("input", label="Applicable documents"),
    Level("system", label="System requirements", parents=["input"]),
    Level("software", parents=["system", "input"]),
    Level("design", parents=["software"]),
    Level("test", parents=["software", "design"]),
]


class _Document:
    """What the helpers read of an SDocDocument."""

    def __init__(self, metadata, version=None, date=None, title="Doc"):
        entries = [
            DocumentCustomMetadataKeyValuePair(key=key, parts=[value])
            for key, value in metadata.items()
        ]
        self.config = DocumentConfig.default_config(None)
        self.config.custom_metadata = DocumentCustomMetadata(entries=entries)
        self.config.version = version
        self.config.date = date
        self.title = title


def _config(tmp_path):
    config = ProjectConfig.default_config()
    config.input_paths = [str(tmp_path)]
    return config


def test_001_levels_are_indexed_by_lower_case_name():
    by_name = validate_hierarchy(
        [Level("Input"), Level("System", parents=["input"])]
    )
    assert list(by_name) == ["input", "system"]


@pytest.mark.parametrize(
    ("levels", "message"),
    [
        ([Level("a"), Level("A")], "declared twice"),
        ([Level("")], "empty name"),
        ([Level("a", parents=["a"])], "its own parent"),
        ([Level("a", parents=["zzz"])], "unknown parent 'zzz'"),
        (
            [
                Level("a", parents=["b"]),
                Level("b", parents=["c"]),
                Level("c", parents=["a"]),
            ],
            "cycle",
        ),
        (["input"], "not a Level"),
    ],
)
def test_002_an_invalid_hierarchy_is_rejected(levels, message):
    with pytest.raises(ValueError, match=message):
        validate_hierarchy(levels)


def test_003_the_kind_comes_from_the_custom_metadata():
    document = _Document({"KIND": "Input", "ISSUER": "ESA"})
    assert document_kind(document) == "input"
    assert is_input_document(document)
    assert document_kind(_Document({"OTHER": "x"})) is None
    assert not is_input_document(_Document({}))


def test_004_metadata_keys_are_upper_case_and_values_trimmed():
    assert document_metadata(_Document({"kind": " input "})) == {
        "KIND": "input"
    }


def test_005_input_info_reads_issuer_reference_revision_version_date():
    document = _Document(
        {
            "KIND": "input",
            "ISSUER": "ESA",
            "REFERENCE": "ECSS-E-ST-70-41C",
            "REVISION": "C",
        },
        version="2.0",
        date="2016-04-15",
        title="PUS standard",
    )
    assert input_info(document) == InputInfo(
        title="PUS standard",
        issuer="ESA",
        reference="ECSS-E-ST-70-41C",
        revision="C",
        version="2.0",
        date="2016-04-15",
    )


@pytest.mark.parametrize(
    ("child", "parent", "ok"),
    [
        ("system", "input", True),
        ("software", "system", True),
        ("software", "input", True),
        ("test", "design", True),
        ("system", "software", False),
        ("design", "input", False),
        ("input", "system", False),
        (None, "system", True),
        ("system", None, True),
        ("unknown", "system", True),
        ("system", "unknown", True),
    ],
)
def test_006_relation_policy_between_kinds(child, parent, ok):
    levels = validate_hierarchy(LEVELS)
    message = relation_violation(levels, child, parent)
    assert (message is None) is ok
    if not ok:
        assert child in message and parent in message


def test_007_the_project_config_validates_the_hierarchy(tmp_path):
    config = _config(tmp_path)
    config.document_hierarchy = [Level("a", parents=["zzz"])]
    with pytest.raises(StrictDocException, match="document_hierarchy"):
        config.validate_and_finalize()


def test_008_a_policy_needs_a_hierarchy_and_a_known_name(tmp_path):
    config = _config(tmp_path)
    config.relation_policy = "strict"
    with pytest.raises(StrictDocException, match="relation_policy"):
        config.validate_and_finalize()
    config = _config(tmp_path)
    config.relation_policy = "enforce"
    with pytest.raises(StrictDocException, match="needs a document_hierarchy"):
        config.validate_and_finalize()
    config = _config(tmp_path)
    config.document_hierarchy = LEVELS
    config.relation_policy = "enforce"
    config.validate_and_finalize()
    assert "system" in config.hierarchy_levels
