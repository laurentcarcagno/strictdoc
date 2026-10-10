import re

from tests.support.hierarchy_fixture import (
    ADMIN,
    READER,
    SOFTWARE_DOC,
    SW_2,
    save_with_parent,
    setup,
)


def _rows(page: str):
    rows = {}
    for match in re.finditer(
        r'<tr data-testid="hierarchy-level" data-level="(\w+)">(.*?)</tr>',
        page,
        re.S,
    ):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", match.group(2), re.S)
        rows[match.group(1)] = [c.strip() for c in cells]
    return rows


def test_001_the_screen_needs_a_hierarchy(tmp_path):
    without, _ = setup(tmp_path / "without", hierarchy=False)
    assert without.get("/hierarchy", headers=ADMIN).status_code == 412
    with_hierarchy, _ = setup(tmp_path / "with")
    assert with_hierarchy.get("/hierarchy", headers=ADMIN).status_code == 200


def test_002_counts_per_level(tmp_path):
    client, _ = setup(tmp_path)
    page = client.get("/hierarchy", headers=READER).text
    rows = _rows(page)
    assert list(rows) == ["input", "system", "software"]
    # [level, documents, nodes, with parent, coverage, orphans, not answered]
    assert rows["input"][:3] == [
        "Applicable documents",
        "Customer specification",
        "2",
    ]
    assert rows["input"][4] == "100 %"
    assert rows["input"][6] == "1"  # DA-2 is not answered
    assert rows["system"][2:7] == ["2", "1", "50 %", "1", "1"]
    assert rows["software"][2:7] == ["2", "1", "50 %", "1", "0"]


def test_003_orphans_and_unanswered_nodes_are_listed_with_links(tmp_path):
    client, _ = setup(tmp_path)
    page = client.get("/hierarchy", headers=READER).text
    assert re.search(r'href="/UID/SYS-2">SYS-2</a>', page)
    assert re.search(r'href="/UID/SW-2">SW-2</a>', page)
    assert re.search(r'href="/UID/DA-2">DA-2</a>', page)
    orphans = re.search(
        r'data-testid="hierarchy-orphans">(.*?)</ul>', page, re.S
    ).group(1)
    assert "DA-1" not in orphans and "SYS-1" not in orphans


def test_004_a_new_link_changes_the_numbers(tmp_path):
    client, _ = setup(tmp_path)
    response = save_with_parent(client, SW_2, SOFTWARE_DOC, "SYS-2")
    assert response.status_code == 200, response.text
    rows = _rows(client.get("/hierarchy", headers=READER).text)
    assert rows["software"][2:7] == ["2", "2", "100 %", "0", "0"]
    assert rows["system"][6] == "0"


def test_005_the_suspect_column_appears_with_the_option(tmp_path):
    client, _ = setup(tmp_path, suspect=True)
    page = client.get("/hierarchy", headers=READER).text
    assert "<th>Suspect</th>" in page
    client, _ = setup(tmp_path / "off")
    assert (
        "<th>Suspect</th>" not in client.get("/hierarchy", headers=READER).text
    )
