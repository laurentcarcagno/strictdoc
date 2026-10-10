import pytest

from strictdoc.cli.base_command import CLIValidationError
from strictdoc.commands.server_config import ServerCommandConfig


def _config(**kwargs) -> ServerCommandConfig:
    return ServerCommandConfig(
        **{
            "debug": False,
            "command": "server",
            "output_path": None,
            "config": None,
            "reload": False,
            "host": None,
            "port": None,
            **kwargs,
        }
    )


def test_001_a_registry_needs_a_root_host(tmp_path):
    registry = tmp_path / "projects.py"
    registry.write_text("", encoding="utf8")
    with pytest.raises(CLIValidationError, match="--root-host"):
        _config(projects=str(registry)).validate()
    _config(projects=str(registry), root_host="strictdoc.test").validate()


def test_002_a_registry_and_an_input_path_exclude_each_other(tmp_path):
    registry = tmp_path / "projects.py"
    registry.write_text("", encoding="utf8")
    with pytest.raises(CLIValidationError, match="not both"):
        _config(
            input_path=str(tmp_path),
            projects=str(registry),
            root_host="h.test",
        ).validate()


def test_003_a_missing_registry_or_data_root_is_reported(tmp_path):
    with pytest.raises(CLIValidationError, match="registry does not exist"):
        _config(
            projects=str(tmp_path / "none.py"), root_host="h.test"
        ).validate()
    registry = tmp_path / "projects.py"
    registry.write_text("", encoding="utf8")
    with pytest.raises(CLIValidationError, match="data root"):
        _config(
            projects=str(registry),
            root_host="h.test",
            data_root=str(tmp_path / "none"),
        ).validate()


def test_004_without_a_registry_an_input_path_is_needed(tmp_path):
    with pytest.raises(CLIValidationError, match="input path or --projects"):
        _config().validate()
    _config(input_path=str(tmp_path)).validate()
