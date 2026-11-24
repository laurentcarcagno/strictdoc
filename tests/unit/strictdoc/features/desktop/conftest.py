"""
The tests of the desktop application never touch the folders of the user.

The application writes in the folders of the user (settings, caches, data, the
profile of Git) and reads the Git setup of the computer. Every test gets other
folders, empty, and a Git setup that holds nothing: the real home folder keeps
what it had.

@relation(SDOC-SRS-1239, scope=file)
@relation(SDOC-SRS-1241, scope=file)
"""

from typing import Iterator

import pytest

from strictdoc.features.desktop import application_language
from strictdoc.features.desktop.ai_policy import configure_policy_paths
from strictdoc.features.i18n.languages import DEFAULT_LANGUAGE, set_language


@pytest.fixture(autouse=True)
def isolate_the_computer(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    machine = tmp_path_factory.mktemp("machine")
    home = machine / "home"
    home.mkdir()
    git_configuration = home / ".gitconfig"
    git_configuration.write_text("")
    folders = {
        "HOME": home,
        "USERPROFILE": home,
        "XDG_CONFIG_HOME": machine / "config",
        "XDG_CACHE_HOME": machine / "cache",
        "XDG_DATA_HOME": machine / "data",
        "XDG_STATE_HOME": machine / "state",
        "APPDATA": machine / "config",
        "LOCALAPPDATA": machine / "data",
    }
    for name_, folder_ in folders.items():
        folder_.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv(name_, str(folder_))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(git_configuration))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    # The application publishes its language in this variable and keeps what
    # it found: a test starts with neither, and leaves neither.
    monkeypatch.setenv("STRICTDOC_LANGUAGE", "")
    monkeypatch.setattr(application_language, "_default_language", None)
    monkeypatch.setattr(application_language, "_published_language", None)
    # The rules of the external AI servers are the ones of a deployment, which
    # this computer may have: a test has none unless it gives a file.
    configure_policy_paths([machine / "ai_policy.json"])
    yield
    configure_policy_paths(None)
    set_language(DEFAULT_LANGUAGE)
