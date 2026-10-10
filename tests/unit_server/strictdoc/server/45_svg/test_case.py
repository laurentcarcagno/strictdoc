import shutil
from pathlib import Path
from typing import Tuple

from fastapi.testclient import TestClient

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfigLoader
from strictdoc.server.app import create_app

PATH_TO_THIS_TEST_FOLDER = Path(__file__).parent
DOCUMENT_MID = "398e37d756ea406f87ca83ec8e29c178"
REQUIREMENT_MID = "a5c6b14d5ee443149687fb9be69a7ede"
HOSTILE = (
    b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">'
    b"<script>alert(2)</script>"
    b'<rect width="10" height="10"/></svg>'
)


def _client(tmp_path: Path) -> Tuple[TestClient, Path]:
    input_path = tmp_path / "input"
    input_path.mkdir()
    shutil.copyfile(
        PATH_TO_THIS_TEST_FOLDER / "document.sdoc",
        input_path / "document.sdoc",
    )
    server_config = ServerCommandConfig(
        debug=False,
        command="server",
        input_path=str(input_path),
        output_path=str(tmp_path / "output"),
        config=None,
        reload=False,
        host="127.0.0.1",
        port=8001,
    )
    project_config = ProjectConfigLoader.load_using_server_config(server_config)
    return TestClient(create_app(project_config=project_config)), input_path


def _upload(client: TestClient, name: str, data: bytes):
    return client.post(
        "/actions/document/upload_asset"
        f"?document_mid={DOCUMENT_MID}&requirement_mid={REQUIREMENT_MID}",
        files=[("uploaded_files", (name, data, "image/svg+xml"))],
    )


def test_001_an_uploaded_svg_is_stored_clean(tmp_path: Path) -> None:
    client, input_path = _client(tmp_path)
    response = _upload(client, "evil.svg", HOSTILE)
    assert response.status_code == 200
    stored = (
        input_path / "_assets" / REQUIREMENT_MID / "evil.svg"
    ).read_bytes()
    assert b"script" not in stored and b"onload" not in stored
    assert b"<rect" in stored


def test_002_an_svg_that_cannot_be_made_safe_is_refused(
    tmp_path: Path,
) -> None:
    client, input_path = _client(tmp_path)
    bomb = (
        b'<!DOCTYPE svg [<!ENTITY a "x">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg"><text>&a;</text></svg>'
    )
    response = _upload(client, "bomb.svg", bomb)
    assert response.status_code == 400
    assert "bomb.svg" in response.json()["detail"]
    assert not (input_path / "_assets" / REQUIREMENT_MID / "bomb.svg").exists()


def test_003_a_served_svg_carries_the_safe_headers(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    assert _upload(client, "ok.svg", HOSTILE).status_code == 200
    response = client.get(f"/input/_assets/{REQUIREMENT_MID}/ok.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "sandbox" in response.headers["content-security-policy"]
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_004_other_responses_are_unchanged(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    response = client.get("/")
    assert "content-security-policy" not in response.headers
