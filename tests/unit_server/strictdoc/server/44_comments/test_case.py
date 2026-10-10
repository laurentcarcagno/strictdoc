import re
from pathlib import Path
from typing import Dict, Tuple

import pytest
from fastapi.testclient import TestClient

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import (
    ProjectConfig,
    ProjectConfigLoader,
    ProjectFeature,
)
from strictdoc.features.comments.model import parse_comment
from strictdoc.server.app import create_app

PATH_TO_THIS_TEST_FOLDER = Path(__file__).parent
PROXY = ("10.89.2.7", 40000)
R1 = "a5c6b14d5ee443149687fb9be69a7ede"
R2 = "b6d7c25e6ff5541a9798c8af7bf8afef"
TEXT = "7a8e7ed4f4a94e9e8a8d7a0c21d1d001"
ROLE_GROUPS = {
    "administrator": ["t-admins"],
    "author": ["t-authors"],
    "reviewer": ["t-reviewers"],
    "reader": ["t-readers"],
}


def _as(group: str, user: str) -> Dict[str, str]:
    return {
        "X-Forwarded-Preferred-Username": user,
        "X-Forwarded-User": f"id-{user}",
        "X-Forwarded-Groups": group,
    }


REVIEWER = _as("t-reviewers", "rita")
OTHER_REVIEWER = _as("t-reviewers", "remi")
AUTHOR = _as("t-authors", "anna")
READER = _as("t-readers", "ruth")


def _setup(
    root: Path, markup: str = "", feature: bool = True
) -> Tuple[TestClient, Path]:
    input_path = root / "input"
    input_path.mkdir(parents=True)
    text = (PATH_TO_THIS_TEST_FOLDER / "document.sdoc").read_text(
        encoding="utf8"
    )
    if markup:
        text = text.replace(
            "  ENABLE_MID: True\n", f"  ENABLE_MID: True\n  MARKUP: {markup}\n"
        )
    (input_path / "document.sdoc").write_text(text, encoding="utf8")
    server_config = ServerCommandConfig(
        debug=False,
        command="server",
        input_path=str(input_path),
        output_path=str(root / "output"),
        config=None,
        reload=False,
        host="127.0.0.1",
        port=8001,
    )
    config: ProjectConfig = ProjectConfigLoader.load_using_server_config(
        server_config
    )
    if feature:
        config.project_features.append(ProjectFeature.COMMENTS)
    config.auth_mode = "proxy"
    config.trusted_proxies = ["10.89.2.0/24"]
    config.roles = ROLE_GROUPS
    client = TestClient(
        create_app(project_config=config),
        client=PROXY,
        raise_server_exceptions=False,
    )
    return client, input_path / "document.sdoc"


def _add(client, mid, body, headers=REVIEWER):
    return client.post(
        "/actions/comments/add",
        data={"node_mid": mid, "body": body},
        headers=headers,
    )


def _comments(path: Path, uid_fragment: str = "R-1"):
    text = path.read_text(encoding="utf8")
    block = text[text.index(f"UID: {uid_fragment}") :]
    block = block.split("[REQUIREMENT]")[0]
    values = []
    parts = block.split("COMMENT: >>>\n")[1:]
    for part_ in parts:
        values.append(parse_comment(part_.split("<<<")[0]))
    return values


def test_001_the_routes_need_the_feature(tmp_path):
    client, _ = _setup(tmp_path, feature=False)
    assert _add(client, R1, "x").status_code == 412
    assert client.get("/comments", headers=READER).status_code == 412


@pytest.mark.parametrize("markup", ["", "Markdown"])
def test_002_a_reviewer_adds_a_comment_with_author_and_date(tmp_path, markup):
    client, path = _setup(tmp_path, markup)
    response = _add(client, R1, "This is not testable.")
    assert response.status_code == 200
    assert "turbo-stream" in response.text
    assert "This is not testable." in response.text
    (comment,) = _comments(path)
    assert comment.author == "rita"
    assert comment.status == "open" and comment.source == "web"
    assert comment.date.endswith("Z") and len(comment.id) == 8
    assert comment.body == "This is not testable."
    header = path.read_text(encoding="utf8").split("COMMENT: >>>\n")[1]
    assert header.startswith(
        "<!-- sdoc-comment" if markup == "Markdown" else ".. sdoc-comment:"
    )


def test_003_the_author_comes_from_the_server_not_from_the_form(tmp_path):
    client, path = _setup(tmp_path)
    client.post(
        "/actions/comments/add",
        data={"node_mid": R1, "body": "x", "author": "mallory"},
        headers=REVIEWER,
    )
    assert _comments(path)[0].author == "rita"


def test_004_a_reader_cannot_comment_and_an_empty_comment_is_refused(
    tmp_path,
):
    client, path = _setup(tmp_path)
    assert _add(client, R1, "x", READER).status_code == 403
    response = _add(client, R1, "   ")
    assert response.status_code == 422
    assert "cannot be empty" in response.text
    assert _comments(path) == []


def test_005_only_an_author_resolves_and_reopens(tmp_path):
    client, path = _setup(tmp_path)
    _add(client, R1, "Check this.")
    comment_id = _comments(path)[0].id
    data = {"node_mid": R1, "comment_id": comment_id}
    assert (
        client.post(
            "/actions/comments/resolve", data=data, headers=REVIEWER
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/actions/comments/resolve", data=data, headers=AUTHOR
        ).status_code
        == 200
    )
    resolved = _comments(path)[0]
    assert resolved.status == "resolved"
    assert resolved.resolved_by == "anna" and resolved.resolved_on.endswith("Z")
    assert resolved.author == "rita" and resolved.body == "Check this."

    client.post("/actions/comments/reopen", data=data, headers=AUTHOR)
    reopened = _comments(path)[0]
    assert reopened.status == "open" and reopened.resolved_by == ""


def test_006_a_reviewer_changes_only_their_own_comment(tmp_path):
    client, path = _setup(tmp_path)
    _add(client, R1, "Mine.")
    comment_id = _comments(path)[0].id
    data = {"node_mid": R1, "comment_id": comment_id, "body": "Changed."}
    assert (
        client.post(
            "/actions/comments/edit", data=data, headers=OTHER_REVIEWER
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/actions/comments/delete",
            data={"node_mid": R1, "comment_id": comment_id},
            headers=OTHER_REVIEWER,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/actions/comments/edit", data=data, headers=REVIEWER
        ).status_code
        == 200
    )
    assert _comments(path)[0].body == "Changed."
    # An author may change or delete any comment.
    assert (
        client.post(
            "/actions/comments/delete",
            data={"node_mid": R1, "comment_id": comment_id},
            headers=AUTHOR,
        ).status_code
        == 200
    )
    assert _comments(path) == []


def test_007_a_legacy_comment_is_shown_and_can_be_resolved(tmp_path):
    client, path = _setup(tmp_path)
    page = client.get("/input/document.html", headers=READER).text
    assert "An old remark without header." in page
    assert "unknown" in page
    response = client.post(
        "/actions/comments/resolve",
        data={"node_mid": R2, "comment_id": "legacy-0"},
        headers=AUTHOR,
    )
    assert response.status_code == 200
    (comment,) = _comments(path, "R-2")
    assert comment.status == "resolved" and not comment.legacy
    assert comment.body == "An old remark without header."


def test_008_the_page_shows_author_date_and_state(tmp_path):
    client, _ = _setup(tmp_path)
    _add(client, R1, "Needs a number.")
    page = client.get("/input/document.html", headers=READER).text
    assert 'data-testid="comments-panel"' in page
    assert 'data-testid="comment-author">rita<' in page
    assert 'data-testid="comment-status">open<' in page
    assert "Needs a number." in page
    assert 'action="/actions/comments/add"' in page
    # The header of the comment is at most an HTML comment, never visible.
    visible = re.sub(r"<!--.*?-->", "", page, flags=re.S)
    assert "sdoc-comment:" not in visible and "date=" not in visible


def test_009_a_node_without_a_comment_field_and_unknown_nodes(tmp_path):
    client, _ = _setup(tmp_path)
    assert _add(client, "f" * 32, "x").status_code == 404
    # A TEXT node has no COMMENT field in the default grammar.
    response = _add(client, TEXT, "x")
    assert response.status_code == 400
    assert "no COMMENT field" in response.json()["detail"]


def test_010_a_comment_with_the_closing_marker_is_refused(tmp_path):
    client, path = _setup(tmp_path)
    response = _add(client, R1, "line\n<<<\nsecond")
    assert response.status_code == 422
    assert "marks the end of a multiline field" in response.text
    assert _comments(path) == []


def test_011_the_screen_lists_the_comments_with_a_state_filter(tmp_path):
    client, path = _setup(tmp_path)
    _add(client, R1, "First remark.")
    _add(client, R1, "Second remark.", OTHER_REVIEWER)
    first = _comments(path)[0]
    client.post(
        "/actions/comments/resolve",
        data={"node_mid": R1, "comment_id": first.id},
        headers=AUTHOR,
    )
    open_page = client.get("/comments", headers=READER).text
    assert "Second remark." in open_page and "First remark." not in open_page
    assert "An old remark without header." in open_page
    resolved = client.get("/comments?status=resolved", headers=READER).text
    assert "First remark." in resolved and "Second remark." not in resolved
    everything = client.get("/comments?status=all", headers=READER).text
    assert everything.count('data-testid="comments-row"') == 3
    assert "/UID/R-1" in everything


def test_012_the_changes_are_in_the_audit_log(tmp_path):
    client, _ = _setup(tmp_path)
    _add(client, R1, "Logged.")
    lines = (tmp_path / "output" / "audit.jsonl").read_text().splitlines()
    assert any(
        "/actions/comments/add" in line_ and '"rita"' in line_
        for line_ in lines
    )
