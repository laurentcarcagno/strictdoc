"""
The publication of a version of the project, the menus of the application,
and the words of the pages.

@relation(SDOC-SRS-1248, scope=file)
@relation(SDOC-SRS-1249, scope=file)
@relation(SDOC-SRS-1250, scope=file)
"""

import re
from pathlib import Path
from typing import Any, List

import pytest
from git import Actor, Repo
from starlette.applications import Starlette
from starlette.testclient import TestClient

from strictdoc.features.desktop.git_access import (
    DesktopGitService,
    GitAccess,
    get_business_subject,
)
from strictdoc.features.desktop.local_server import (
    create_desktop_project_config,
    create_project_application,
)
from strictdoc.features.desktop.project_gate import ProjectGate
from strictdoc.features.desktop.project_publish import (
    plan_publication,
    send_version,
)
from strictdoc.features.desktop.project_runtime import (
    ProjectRuntime,
    get_project_runtime,
)
from strictdoc.features.desktop.wording import APPLICATION_TEXTS
from strictdoc.features.git_config.git_service import Author
from strictdoc.features.i18n import i18n
from strictdoc.features.i18n.i18n import _template_gettext
from strictdoc.features.roles.principal import Principal

SEED = Actor("Seed", "seed@example.org")
COLLEAGUE = Actor("Colleague", "colleague@example.org")
AUTHOR = Author("Jeanne Dupont", "jeanne@example.org")
DOCUMENT = (
    "[DOCUMENT]\nMID: 1d6c2b5f8a9e4e1fb7c3a0d4e5f60a11\nTITLE: Doc\n"
    "OPTIONS:\n  ENABLE_MID: True\n\n"
    "[REQUIREMENT]\nMID: 2e7d3c6a9b0f4f2ac8d4b1e5f6a70b22\nUID: REQ-1\n"
    "STATEMENT: The system shall brake.\n"
)
BANNED_WORDS = re.compile(
    r"\b(git|gitlab|commit|commits|committed|push|pushed|pull|pulled|branch|"
    r"merge|merged|rebase|fatal|remote|origin|repository|fetch|tag|tags|sha)\b",
    re.IGNORECASE,
)


@pytest.fixture(name="restore_language", autouse=True)
def fixture_restore_language() -> Any:
    yield
    i18n.set_language(i18n.DEFAULT_LANGUAGE)


class Clone:
    """A clone of the server, with the exclusion and the runtime of its own."""

    def __init__(self, bare: Path, folder: Path) -> None:
        Repo.clone_from(str(bare), str(folder)).close()
        self.bare = bare
        self.folder = folder
        self.gate = ProjectGate()
        self.runtime = ProjectRuntime()

    def plan(self, kind: str = "") -> Any:
        return plan_publication(
            str(self.folder),
            git_access=GitAccess(),
            gate=self.gate,
            runtime=self.runtime,
            kind=kind,
            author=AUTHOR,
        )

    def publish(self, kind: str = "draft") -> str:
        """Create and send a version. It returns its name, "" if refused."""
        found, name = self.plan(kind)
        if name == "":
            return ""
        is_sent, _ = send_version(
            str(self.folder), name, git_access=GitAccess()
        )
        return name if is_sent else ""

    def get_local_tags(self) -> List[str]:
        repo = Repo(self.folder)
        try:
            return sorted(tag_.name for tag_ in repo.tags)
        finally:
            repo.close()

    def get_server_tags(self) -> List[str]:
        repo = Repo(self.bare)
        try:
            return sorted(tag_.name for tag_ in repo.tags)
        finally:
            repo.close()

    def commit_here(self, text: str) -> None:
        document = self.folder / "doc.sdoc"
        document.write_text(
            document.read_text(encoding="utf-8").replace(
                "shall brake", f"shall brake {text}"
            ),
            encoding="utf-8",
        )
        repo = Repo(self.folder)
        repo.index.add(["doc.sdoc"])
        repo.index.commit("Save", author=COLLEAGUE, committer=COLLEAGUE)
        repo.git.push("origin", "main")
        repo.close()


@pytest.fixture(name="clone")
def fixture_clone(tmp_path: Path) -> Clone:
    work = tmp_path / "work"
    work.mkdir()
    (work / "doc.sdoc").write_text(DOCUMENT, encoding="utf-8")
    repo = Repo.init(work, initial_branch="main")
    repo.index.add(["doc.sdoc"])
    repo.index.commit("Seed", author=SEED, committer=SEED)
    repo.close()
    bare = tmp_path / "remote.git"
    Repo.clone_from(str(work), str(bare), bare=True).close()
    return Clone(bare, tmp_path / "project")


# The next versions.


def test_001_the_names_follow_the_versions_of_the_server(clone: Clone) -> None:
    found, _ = clone.plan()
    assert (found.refusal, found.latest) == ("", "")
    assert (found.next_draft, found.next_major) == ("A1", "")

    assert clone.publish("draft") == "A1"
    found, _ = clone.plan()
    assert (found.latest, found.next_draft, found.next_major) == (
        "A1",
        "A2",
        "A",
    )

    assert clone.publish("major") == "A"
    found, _ = clone.plan()
    assert (found.latest, found.next_draft, found.next_major) == (
        "A",
        "B1",
        "",
    )
    assert clone.get_local_tags() == clone.get_server_tags() == ["A", "A1"]


def test_002_a_version_that_another_clone_published_is_read_first(
    clone: Clone, tmp_path: Path
) -> None:
    other = Clone(clone.bare, tmp_path / "other")
    assert other.publish("draft") == "A1"

    found, name = clone.plan("draft")

    # The tags of the server were read: the next draft is A2, not A1.
    assert (name, found.latest) == ("A2", "A1")
    assert clone.get_local_tags() == ["A1", "A2"]


def test_003_an_unreadable_name_of_the_server_is_not_a_version(
    clone: Clone,
) -> None:
    repo = Repo(clone.folder)
    repo.create_tag("release-candidate")
    repo.git.push("origin", "release-candidate")
    repo.close()

    found, _ = clone.plan()

    assert found.next_draft == "A1"


# The refusals: each one a text, and no version on the computer.


def _assert_refused(clone: Clone, expected: str) -> None:
    found, name = clone.plan("draft")
    assert name == ""
    assert expected in found.refusal
    assert BANNED_WORDS.findall(found.refusal) == []
    assert clone.get_local_tags() == []


def test_004_offline_nothing_is_published(clone: Clone) -> None:
    Repo(clone.folder).git.remote("set-url", "origin", "/nowhere/at/all")

    _assert_refused(clone, "only when the server answers")


def test_005_a_merge_that_waits_refuses(clone: Clone) -> None:
    repo = Repo(clone.folder)
    head = repo.head.commit.hexsha
    (Path(repo.git_dir) / "MERGE_HEAD").write_text(head + "\n")
    repo.close()

    _assert_refused(clone, "Choose which version to keep")


def test_006_a_change_that_waits_to_be_sent_refuses(clone: Clone) -> None:
    document = clone.folder / "doc.sdoc"
    document.write_text(DOCUMENT.replace("brake", "brake hard"))
    repo = Repo(clone.folder)
    repo.index.add(["doc.sdoc"])
    repo.index.commit("Save", author=COLLEAGUE, committer=COLLEAGUE)
    repo.close()

    _assert_refused(clone, "not shared yet")


def test_007_a_project_that_is_late_on_the_server_refuses(
    clone: Clone, tmp_path: Path
) -> None:
    Clone(clone.bare, tmp_path / "other").commit_here("hard")

    _assert_refused(clone, "Update the project first")


def test_008_a_change_that_is_not_saved_refuses(clone: Clone) -> None:
    (clone.folder / "doc.sdoc").write_text(DOCUMENT.replace("brake", "stop"))

    _assert_refused(clone, "not saved yet")


def test_009_an_index_that_is_late_refuses(clone: Clone) -> None:
    clone.runtime.mark_files_changed()

    _assert_refused(clone, "cannot be read")


def test_010_a_major_version_needs_a_draft_first(clone: Clone) -> None:
    found, name = clone.plan("major")

    assert name == ""
    assert "draft version is needed" in found.refusal
    assert clone.get_local_tags() == []


# The sending: the tag alone, and no orphan.


def test_011_two_clones_that_publish_the_same_version_leave_no_orphan(
    clone: Clone, tmp_path: Path
) -> None:
    other = Clone(clone.bare, tmp_path / "other")
    # Both prepare A1 before either sends it.
    _, name_here = clone.plan("draft")
    _, name_there = other.plan("draft")
    assert (name_here, name_there) == ("A1", "A1")

    here_sent, here_message = send_version(
        str(clone.folder), "A1", git_access=GitAccess()
    )
    there_sent, there_message = send_version(
        str(other.folder), "A1", git_access=GitAccess()
    )

    assert (here_sent, here_message) == (True, "")
    assert there_sent is False
    assert "Another administrator has just published" in there_message
    assert BANNED_WORDS.findall(there_message) == []
    assert clone.get_server_tags() == ["A1"]
    assert clone.get_local_tags() == ["A1"]
    # The loser has no version of the computer that the server lacks.
    assert other.get_local_tags() == []


def test_012_a_version_that_cannot_be_sent_is_removed_from_the_computer(
    clone: Clone,
) -> None:
    _, name = clone.plan("draft")
    assert name == "A1"
    Repo(clone.folder).git.remote("set-url", "origin", "/nowhere/at/all")

    is_sent, message = send_version(
        str(clone.folder), name, git_access=GitAccess()
    )

    assert is_sent is False
    assert "not published" in message
    assert BANNED_WORDS.findall(message) == []
    assert clone.get_local_tags() == []
    assert clone.get_server_tags() == []


def test_013_only_the_version_goes_to_the_server(clone: Clone) -> None:
    head = Repo(clone.bare).commit("main").hexsha

    assert clone.publish("draft") == "A1"

    repo = Repo(clone.bare)
    assert repo.commit("main").hexsha == head
    assert [ref_.name for ref_ in repo.heads] == ["main"]
    assert repo.tags["A1"].commit.hexsha == head
    repo.close()


# The routes, the menus.


def _create_application(clone: Clone, role: str) -> Starlette:
    config = create_desktop_project_config(
        input_path=str(clone.folder),
        port=None,
        principal_provider=lambda: Principal(user="jdupont", role=role),
    )
    return create_project_application(config, lambda: AUTHOR, GitAccess())


def test_014_an_administrator_publishes_and_the_others_do_not(
    clone: Clone,
) -> None:
    administrator = TestClient(_create_application(clone, "administrator"))
    author = TestClient(_create_application(clone, "author"))
    reader = TestClient(_create_application(clone, "reader"))

    for client_ in (author, reader):
        assert client_.get("/actions/git/version_document").status_code == 403
        answer = client_.post(
            "/actions/git/version_document", data={"kind": "draft"}
        )
        assert answer.status_code == 403
    dialog = administrator.get("/actions/git/version_document").text
    assert 'data-testid="publish-next-draft">A1<' in dialog
    assert 'data-testid="publish-major"' in dialog
    visible = _get_visible_text(dialog)
    assert "Publish a version" in visible
    assert BANNED_WORDS.findall(visible) == []

    answer = administrator.post(
        "/actions/git/version_document", data={"kind": "draft"}
    )

    assert answer.status_code == 200
    assert "Version A1 is published." in _get_visible_text(answer.text)
    assert clone.get_server_tags() == ["A1"]
    assert clone.get_local_tags() == ["A1"]
    get_project_runtime(str(clone.folder)).leases.close()


def test_015_the_refusal_is_in_the_window_in_french(clone: Clone) -> None:
    client = TestClient(_create_application(clone, "administrator"))
    Repo(clone.folder).git.remote("set-url", "origin", "/nowhere/at/all")
    i18n.set_language("fr")

    dialog = client.get("/actions/git/version_document").text

    visible = _get_visible_text(dialog)
    assert (
        "Une version ne peut être publiée que si le serveur répond" in visible
    )
    assert 'data-testid="publish-draft"' not in dialog
    assert BANNED_WORDS.findall(visible) == []
    assert clone.get_local_tags() == []


def _get_visible_text(page: str) -> str:
    without_scripts = re.sub(r"<script.*?</script>", " ", page, flags=re.DOTALL)
    return re.sub(r"<[^>]+>", " ", without_scripts)


def _get_environment(application: Starlette) -> Any:
    context = application.state.project_context
    return context.html_templates.jinja_environment().environment


def test_016_the_menus_have_no_git_and_the_web_server_keeps_its_own(
    clone: Clone, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = _create_application(clone, "administrator")
    client = TestClient(application)

    tree = client.get("/fragments/project_tree").text
    page = client.get("/git").text

    for name_ in (
        "tree-git-action",
        "tree-sync-action",
        "tree-version-document-action",
    ):
        assert name_ not in tree, name_
    assert 'data-testid="tree-update-action"' in tree
    assert 'data-testid="tree-publish-action"' in tree
    assert 'data-requires-role="administrator"' in tree
    assert 'data-testid="nav-git"' not in page
    assert 'href="/git"' not in page
    assert "/actions/git/overview" not in tree

    environment = _get_environment(application)
    monkeypatch.delitem(environment.globals, "desktop_application")
    monkeypatch.delitem(environment.globals, "desktop_indicator")
    web_tree = client.get("/fragments/project_tree").text
    web_page = client.get("/git").text

    for name_ in (
        "tree-git-action",
        "tree-sync-action",
        "tree-version-document-action",
    ):
        assert name_ in web_tree, name_
    assert "tree-update-action" not in web_tree
    assert "tree-publish-action" not in web_tree
    assert 'data-testid="nav-git"' in web_page
    assert 'href="/git"' in web_page
    # The same separators and spaces as before around the entries.
    assert (
        '<hr class="sdoc-tree-menu__separator"/>\n    <a\n  '
        'class="sdoc-tree-menu__item"' in web_tree
    )
    get_project_runtime(str(clone.folder)).leases.close()


def test_017_the_routes_and_pages_of_git_are_still_served(
    clone: Clone,
) -> None:
    client = TestClient(_create_application(clone, "administrator"))

    assert client.get("/git").status_code == 200
    assert client.get("/actions/git/overview").status_code == 200


# The words.


def test_018_a_shared_text_is_said_in_words_of_work_in_the_application(
    clone: Clone, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = _create_application(clone, "administrator")
    environment = _get_environment(application)
    template = environment.from_string(
        '{{ _("No commit changed this item yet.") }}|'
        '{{ _("Export to PDF without revision marks") }}|'
        '{{ _("Version %(tag)s", tag="A1") }}'
    )

    english = template.render()
    i18n.set_language("fr")
    french = template.render()
    monkeypatch.setitem(environment.globals, "gettext", _template_gettext)
    i18n.set_language("en")
    web = template.render()

    assert english == (
        "No change has been saved for this item yet.|"
        "Export to PDF without change marks|Version A1"
    )
    assert "Aucune modification n'a encore été enregistrée" in french
    assert "sans les marques de modification" in french
    assert BANNED_WORDS.findall(french) == []
    # The web server keeps the text of the template.
    assert web == (
        "No commit changed this item yet.|"
        "Export to PDF without revision marks|Version A1"
    )


def test_019_every_text_of_the_table_has_a_french_translation() -> None:
    i18n.set_language("fr")

    for replacement_ in APPLICATION_TEXTS.values():
        assert i18n.gettext(replacement_) != replacement_, replacement_
        assert BANNED_WORDS.findall(replacement_) == []


def test_020_the_history_of_an_item_has_no_identifier_and_no_header_of_git(
    clone: Clone,
) -> None:
    service = DesktopGitService(str(clone.folder), GitAccess())
    path = str(clone.folder / "doc.sdoc")

    revisions = service.history_of_lines(path, 8, 11)

    assert len(revisions) > 0
    for revision_ in revisions:
        assert revision_.commit == ""
        assert "diff --git" not in revision_.patch
    assert revisions[0].patch != ""


def test_021_the_message_of_a_merge_is_said_in_words_of_work() -> None:
    assert get_business_subject("Merge origin/main") == (
        "Changes of colleagues combined with yours"
    )
    assert get_business_subject("chore: save doc.sdoc") == (
        "chore: save doc.sdoc"
    )


def test_022_the_versions_of_a_document_say_what_changed_in_words_of_work(
    clone: Clone,
) -> None:
    clone.publish("draft")
    service = DesktopGitService(str(clone.folder), GitAccess())

    tags = service.version_tags_of(str(clone.folder / "doc.sdoc"))

    assert [tag_.name for tag_ in tags] == ["A1"]
