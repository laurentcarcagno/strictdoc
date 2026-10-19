import pytest

from strictdoc.helpers.exception import StrictDocException
from tests.support.kb_fixture import make_kb_config


def test_001_the_default_configuration_is_valid():
    make_kb_config().validate()


@pytest.mark.parametrize(
    "url",
    ["http://kb.internal", "https://kb.karka.lan", "http://127.0.0.1:8080"],
)
def test_002_the_address_is_https_or_the_internal_one(url):
    make_kb_config(url=url).validate()


@pytest.mark.parametrize(
    "url", ["http://evil.example", "ftp://kb.internal", "kb.internal", ""]
)
def test_003_any_other_address_is_refused(url):
    with pytest.raises(StrictDocException):
        make_kb_config(url=url).validate()


def test_004_the_token_endpoint_is_https():
    with pytest.raises(StrictDocException):
        make_kb_config(token_url="http://kb.internal/token").validate()


def test_005_only_tools_that_read_are_allowed():
    with pytest.raises(StrictDocException, match="drop_table"):
        make_kb_config(tools=["search", "drop_table"]).validate()
    with pytest.raises(StrictDocException):
        make_kb_config(tools=[]).validate()


@pytest.mark.parametrize("steps", [0, 13])
def test_006_the_rounds_are_bounded(steps):
    with pytest.raises(StrictDocException):
        make_kb_config(max_steps=steps).validate()


def test_007_a_mission_is_needed():
    with pytest.raises(StrictDocException):
        make_kb_config(mission=" ").validate()
