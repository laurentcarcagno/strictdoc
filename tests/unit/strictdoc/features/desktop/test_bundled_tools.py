"""
@relation(SDOC-SRS-1257, scope=file)
@relation(SDOC-SRS-1258, scope=file)
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import git
import pytest

from strictdoc.features.desktop import (
    bundled_tools,
    git_access,
    send_queue,
)
from strictdoc.features.desktop.bundled_tools import (
    TOOLS_DIR_VARIABLE,
    find_bundled_tools,
    get_hidden_window_flags,
    get_library_path_overrides,
    get_system_program_environment,
    get_tools_dir,
    use_bundled_git,
    use_bundled_html2pdf4doc,
)
from strictdoc.features.desktop.local_server import (
    create_desktop_project_config,
)

_SUFFIX = ".exe" if sys.platform == "win32" else ""


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def _make_tools(tools_dir: Path, *, with_git: bool = False) -> None:
    _touch(
        tools_dir / "chrome-headless-shell" / f"chrome-headless-shell{_SUFFIX}"
    )
    _touch(tools_dir / "chromedriver" / f"chromedriver{_SUFFIX}")
    _touch(tools_dir / "html2pdf4doc" / f"html2pdf4doc{_SUFFIX}")
    if with_git:
        _touch(tools_dir / "mingit" / "cmd" / f"git{_SUFFIX}")


def test_no_tools_folder_without_variable_nor_frozen_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(TOOLS_DIR_VARIABLE, raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert get_tools_dir() is None
    assert find_bundled_tools() == bundled_tools.BundledTools(
        None, None, None, None
    )


def test_variable_gives_the_tools_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _make_tools(tmp_path, with_git=True)
    monkeypatch.setenv(TOOLS_DIR_VARIABLE, str(tmp_path))

    tools = find_bundled_tools()

    assert tools.chrome_binary is not None
    assert tools.chrome_binary.name == f"chrome-headless-shell{_SUFFIX}"
    assert tools.chromedriver is not None
    assert tools.chromedriver.name == f"chromedriver{_SUFFIX}"
    assert tools.git is not None
    assert tools.git.parent.name == "cmd"
    assert tools.html2pdf4doc is not None
    assert tools.html2pdf4doc.parent.name == "html2pdf4doc"


def test_frozen_application_uses_the_folder_next_to_the_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = _touch(tmp_path / "application" / "strictdoc")
    _make_tools(tmp_path / "application" / "tools")
    monkeypatch.delenv(TOOLS_DIR_VARIABLE, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    tools = find_bundled_tools()

    assert get_tools_dir() == executable.resolve().parent / "tools"
    assert tools.chrome_binary is not None
    assert tools.chromedriver is not None
    assert tools.git is None


def test_missing_tool_is_not_returned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _touch(tmp_path / "chromedriver" / f"chromedriver{_SUFFIX}")
    monkeypatch.setenv(TOOLS_DIR_VARIABLE, str(tmp_path))

    tools = find_bundled_tools()

    assert tools.chrome_binary is None
    assert tools.chromedriver is not None


def test_use_bundled_git_refreshes_gitpython_and_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    monkeypatch.setattr(git, "refresh", calls.append)
    monkeypatch.setenv("PATH", "/somewhere")
    git_path = tmp_path / "cmd" / "git"

    use_bundled_git(git_path)

    assert calls == [str(git_path)]
    assert os.environ["PATH"] == os.pathsep.join(
        [str(git_path.parent), "/somewhere"]
    )


def test_use_bundled_html2pdf4doc_puts_its_folder_first_in_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "/somewhere")
    program = tmp_path / "html2pdf4doc" / f"html2pdf4doc{_SUFFIX}"

    use_bundled_html2pdf4doc(program)

    assert os.environ["PATH"] == os.pathsep.join(
        [str(program.parent), "/somewhere"]
    )


def test_project_config_uses_the_pdf_tools_of_the_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools_dir = tmp_path / "tools"
    _make_tools(tools_dir)
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv(TOOLS_DIR_VARIABLE, str(tools_dir))

    project_config = create_desktop_project_config(
        input_path=str(project), port=None
    )

    assert project_config.chrome_binary == str(
        tools_dir / "chrome-headless-shell" / f"chrome-headless-shell{_SUFFIX}"
    )
    assert project_config.chromedriver == str(
        tools_dir / "chromedriver" / f"chromedriver{_SUFFIX}"
    )


def test_project_config_keeps_its_pdf_tools_without_a_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.delenv(TOOLS_DIR_VARIABLE, raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)

    project_config = create_desktop_project_config(
        input_path=str(project), port=None
    )

    assert project_config.chrome_binary is None
    assert project_config.chromedriver is None


def test_git_profile_allows_long_paths_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(git_access.sys, "platform", "win32")
    # The simulated platform must not reach the real subprocess of Linux.
    monkeypatch.setattr(git_access, "get_hidden_window_flags", lambda: 0)
    environment = git_access.GitProfile(tmp_path / "profile").get_environment()

    content = Path(environment["GIT_CONFIG_GLOBAL"]).read_text(encoding="utf8")

    assert "longpaths = true" in content


def test_git_profile_has_no_long_paths_setting_elsewhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(git_access.sys, "platform", "linux")
    environment = git_access.GitProfile(tmp_path / "profile").get_environment()

    content = Path(environment["GIT_CONFIG_GLOBAL"]).read_text(encoding="utf8")

    assert "longpaths" not in content


# The Git of the system in a frozen application.


def _freeze(monkeypatch: pytest.MonkeyPatch, platform: str = "linux") -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", platform)


def test_library_path_is_not_touched_outside_a_frozen_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/package")

    assert get_library_path_overrides() == {}
    assert get_system_program_environment()["LD_LIBRARY_PATH"] == "/package"


def test_system_program_gets_the_original_library_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze(monkeypatch)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/package")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/system/lib")

    environment = get_system_program_environment()

    assert environment["LD_LIBRARY_PATH"] == "/system/lib"
    assert get_library_path_overrides() == {"LD_LIBRARY_PATH": "/system/lib"}
    # The environment of the process keeps the path of the package.
    assert os.environ["LD_LIBRARY_PATH"] == "/package"


def test_system_program_has_no_library_path_when_there_was_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze(monkeypatch)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/package")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)

    environment = get_system_program_environment()

    assert "LD_LIBRARY_PATH" not in environment
    assert get_library_path_overrides() == {"LD_LIBRARY_PATH": ""}
    assert os.environ["LD_LIBRARY_PATH"] == "/package"


def test_refresh_git_runs_with_the_system_library_path_then_restores_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze(monkeypatch)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/package")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/system/lib")
    seen = []
    monkeypatch.setattr(
        git, "refresh", lambda: seen.append(os.environ["LD_LIBRARY_PATH"])
    )

    bundled_tools.refresh_git()

    assert seen == ["/system/lib"]
    assert os.environ["LD_LIBRARY_PATH"] == "/package"


def test_refresh_git_without_original_path_runs_with_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze(monkeypatch)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/package")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    seen = []
    monkeypatch.setattr(
        git, "refresh", lambda: seen.append(os.environ.get("LD_LIBRARY_PATH"))
    )

    bundled_tools.refresh_git()

    assert seen == [None]
    assert os.environ["LD_LIBRARY_PATH"] == "/package"


def test_git_environment_carries_the_library_path_for_gitpython(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze(monkeypatch)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/package")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/system/lib")

    environment = git_access.GitAccess().build_environment(is_network=False)

    assert environment["LD_LIBRARY_PATH"] == "/system/lib"


def test_global_configuration_is_read_with_the_system_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze(monkeypatch, "win32")
    captured: Dict[str, Any] = {}

    def fake_run(*_: Any, **keywords: Any) -> Any:
        captured.update(keywords)
        raise OSError("stop")

    monkeypatch.setattr(git_access.subprocess, "run", fake_run)

    git_access._read_global_configuration(tmp_path)

    assert captured["creationflags"] == 0x08000000
    assert "env" in captured


def test_push_runs_without_the_library_path_and_without_a_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _freeze(monkeypatch)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/package")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/system/lib")
    captured: Dict[str, Any] = {}

    def fake_popen(*_: Any, **keywords: Any) -> Any:
        captured.update(keywords)
        raise OSError("stop")

    monkeypatch.setattr(send_queue.subprocess, "Popen", fake_popen)
    queue = send_queue.SendQueue(
        git_access=git_access.GitAccess(),
        get_folders=dict,
        get_user_email=lambda: None,
        get_gitlab_url=lambda: "",
        get_role=lambda _: None,
    )

    queue._run_push(
        str(tmp_path),
        SimpleNamespace(head="abc", branch="main"),
        {},  # type: ignore[arg-type]
    )

    assert captured["env"]["LD_LIBRARY_PATH"] == "/system/lib"
    assert captured["creationflags"] == 0


def test_hidden_window_flags_only_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert get_hidden_window_flags() == 0x08000000

    monkeypatch.setattr(sys, "platform", "linux")
    assert get_hidden_window_flags() == 0
