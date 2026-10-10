import json
import os

import pytest

from strictdoc.features.hierarchy.suspect import (
    Baseline,
    BaselineError,
    SuspectLink,
    impact_of,
    link_key,
    load_cached,
)


def test_001_the_file_has_sorted_keys_and_one_line_per_link(tmp_path):
    baseline = Baseline({"B < A": "2" * 40, "A < Z": "1" * 40})
    path = tmp_path / "trace_baseline.json"
    baseline.save(str(path))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "{" and lines[-1] == "}"
    assert lines[1].startswith('"A < Z"') and lines[2].startswith('"B < A"')
    assert lines[1].endswith(",") and not lines[2].endswith(",")
    assert json.loads(path.read_text(encoding="utf-8")) == baseline.entries


def test_002_an_empty_baseline_is_valid_json(tmp_path):
    path = tmp_path / "b.json"
    Baseline().save(str(path))
    assert Baseline.load(str(path)).entries == {}


def test_003_save_then_load_round_trips_and_is_stable(tmp_path):
    path = tmp_path / "b.json"
    baseline = Baseline({"SW-1 < SYS-1": "a" * 40})
    baseline.save(str(path))
    first = path.read_text(encoding="utf-8")
    Baseline.load(str(path)).save(str(path))
    assert path.read_text(encoding="utf-8") == first


def test_004_a_missing_file_is_an_empty_baseline(tmp_path):
    assert Baseline.load(str(tmp_path / "none.json")).entries == {}


@pytest.mark.parametrize("content", ["not json", "[1]", '{"a": 1}'])
def test_005_a_broken_file_is_reported(tmp_path, content):
    path = tmp_path / "b.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(BaselineError):
        Baseline.load(str(path))


def test_006_a_uid_that_would_break_the_key_is_refused():
    with pytest.raises(BaselineError):
        link_key("A < B", "C")


def test_007_the_cache_reads_again_when_the_file_changes(tmp_path):
    path = tmp_path / "b.json"
    Baseline({"A < B": "1" * 40}).save(str(path))
    assert load_cached(str(path)).entries == {"A < B": "1" * 40}
    Baseline({"A < B": "2" * 40}).save(str(path))
    os.utime(path, (1, 1))
    assert load_cached(str(path)).entries == {"A < B": "2" * 40}


class _Node:
    def __init__(self, uid):
        self.reserved_uid = uid


def test_008_the_impact_lists_the_children_of_the_changed_parents():
    suspects = [
        SuspectLink(child=_Node("C2"), parent=_Node("P1")),
        SuspectLink(child=_Node("C1"), parent=_Node("P1")),
        SuspectLink(child=_Node("C3"), parent=_Node("P2")),
    ]
    assert impact_of(suspects, ["P1"]) == {"P1": ["C1", "C2"]}
    assert impact_of(suspects, ["P9"]) == {}
