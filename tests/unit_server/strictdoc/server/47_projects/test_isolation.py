import hashlib
import json
import os
from pathlib import Path
from typing import Dict

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from tests.support.hierarchy_fixture import form_values
from tests.support.projects_fixture import (
    ALPHA_DOC,
    ALPHA_REQ,
    BETA_DOC,
    BETA_REQ,
    ROOT,
    as_user,
    client_for,
    clients,
    make_dispatcher,
)

ALPHA_ADMIN = as_user("alpha-admins", user="ann")
BETA_ADMIN = as_user("beta-admins", user="ben")


def _snapshot(folder: Path) -> Dict[str, str]:
    result = {}
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            result[str(path.relative_to(folder))] = hashlib.sha1(
                path.read_bytes()
            ).hexdigest()
    return result


class _FakeWatcher:
    def __init__(self) -> None:
        self.events = []

    def start(self) -> None:
        self.events.append("start")

    def stop(self) -> None:
        self.events.append("stop")


def test_001_the_lifespan_of_every_project_starts_and_stops(
    tmp_path, monkeypatch
):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    watchers = {}
    for slug, app in dispatcher.projects.items():
        watchers[slug] = app.state.document_watcher = _FakeWatcher()
    with TestClient(dispatcher):
        assert {s: w.events for s, w in watchers.items()} == {
            "alpha": ["start"],
            "beta": ["start"],
        }
    assert {s: w.events for s, w in watchers.items()} == {
        "alpha": ["start", "stop"],
        "beta": ["start", "stop"],
    }


def test_002_each_project_has_its_own_output_and_cache(tmp_path, monkeypatch):
    make_dispatcher(tmp_path, monkeypatch)
    out = tmp_path / "output"
    assert (out / "alpha").is_dir() and (out / "beta").is_dir()
    # The cache of a project holds its own documents and no other.
    alpha_files = [str(p) for p in (out / "alpha").rglob("*")]
    beta_files = [str(p) for p in (out / "beta").rglob("*")]
    assert any("alpha_doc" in name for name in alpha_files)
    assert not any("beta_doc" in name for name in alpha_files)
    assert any("beta_doc" in name for name in beta_files)
    assert not any("alpha_doc" in name for name in beta_files)


def test_003_a_change_in_alpha_leaves_beta_untouched(tmp_path, monkeypatch):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    _, alpha, beta = clients(dispatcher)
    beta_data = tmp_path / "data" / "beta"
    beta_out = tmp_path / "output" / "beta"
    beta_page = beta.get("/beta/beta_doc.html", headers=BETA_ADMIN).text
    before = (_snapshot(beta_data), _snapshot(beta_out))

    values = form_values(_form(alpha, ALPHA_REQ, ALPHA_DOC, ALPHA_ADMIN))
    name = next(
        k.replace("[name]", "[value]")
        for k, v in values.items()
        if k.endswith("[name]") and v == "STATEMENT"
    )
    values[name] = "The Alpha spec shall work differently."
    response = alpha.post(
        "/actions/document/update_requirement",
        data=values,
        headers=ALPHA_ADMIN,
    )
    assert response.status_code == 200, response.text
    assert "differently" in (tmp_path / "data/alpha/alpha_doc.sdoc").read_text()

    assert (_snapshot(beta_data), _snapshot(beta_out)) == before
    assert beta.get("/beta/beta_doc.html", headers=BETA_ADMIN).text == beta_page


def _form(client, node_mid, document_mid, headers):
    response = client.get(
        "/actions/document/edit_requirement",
        params={"node_id": node_mid, "context_document_mid": document_mid},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return BeautifulSoup(response.text, "html.parser")


def test_004_a_node_of_beta_cannot_be_edited_through_alpha(
    tmp_path, monkeypatch
):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    _, alpha, _ = clients(dispatcher)
    both_admin = as_user("alpha-admins", "beta-admins", user="root")
    beta_file = tmp_path / "data/beta/beta_doc.sdoc"
    before = beta_file.read_bytes()
    response = alpha.get(
        "/actions/document/edit_requirement",
        params={"node_id": BETA_REQ, "context_document_mid": BETA_DOC},
        headers=both_admin,
    )
    assert response.status_code in (404, 500)
    response = alpha.post(
        "/actions/document/update_requirement",
        data={"requirement_mid": BETA_REQ, "document_mid": BETA_DOC},
        headers=both_admin,
    )
    assert response.status_code != 200
    assert beta_file.read_bytes() == before


def test_005_audit_logs_are_one_per_project(tmp_path, monkeypatch):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    _, alpha, beta = clients(dispatcher)
    alpha.get("/alpha/alpha_doc.html", headers=ALPHA_ADMIN)
    alpha.post("/actions/document/upload_asset", data={}, headers=ALPHA_ADMIN)
    beta.post("/actions/document/upload_asset", data={}, headers=BETA_ADMIN)
    a_log = tmp_path / "audit" / "alpha" / "audit.jsonl"
    b_log = tmp_path / "audit" / "beta" / "audit.jsonl"
    assert a_log.is_file() and b_log.is_file()
    a_users = {
        json.loads(line)["user"] for line in a_log.read_text().splitlines()
    }
    b_users = {
        json.loads(line)["user"] for line in b_log.read_text().splitlines()
    }
    assert a_users == {"ann"} and b_users == {"ben"}


def test_006_a_refusal_in_one_project_is_audited_in_that_project_only(
    tmp_path, monkeypatch
):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    _, alpha, beta = clients(dispatcher)
    # A beta administrator tries to write in alpha: refused, audited in alpha.
    response = alpha.post(
        "/actions/document/upload_asset", data={}, headers=BETA_ADMIN
    )
    assert response.status_code == 403
    a_lines = (tmp_path / "audit/alpha/audit.jsonl").read_text().splitlines()
    assert any(json.loads(line)["user"] == "ben" for line in a_lines)
    assert not (tmp_path / "audit/beta/audit.jsonl").exists() or all(
        json.loads(line)["user"] != "ben"
        for line in (tmp_path / "audit/beta/audit.jsonl")
        .read_text()
        .splitlines()
    )


def test_007_the_environment_of_the_process_is_not_changed(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("STRICTDOC_ROLES", raising=False)
    make_dispatcher(tmp_path, monkeypatch)
    assert "STRICTDOC_ROLES" not in os.environ


def test_008_two_clients_on_two_hosts_do_not_share_state(tmp_path, monkeypatch):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    one = client_for(dispatcher, f"alpha.{ROOT}")
    two = client_for(dispatcher, f"beta.{ROOT}")
    one.cookies.set("session", "x")
    assert two.cookies.get("session") is None
