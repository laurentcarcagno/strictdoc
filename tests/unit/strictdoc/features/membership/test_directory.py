import pytest

from strictdoc.features.projects.directory import (
    DirectoryError,
    KeycloakDirectory,
    directory_from_environment,
)
from tests.support.fake_keycloak import SECRET, FakeKeycloak

USERS = [
    {
        "username": "Bob",
        "firstName": "Bob",
        "lastName": "Martin",
        "email": "bob@example.org",
        "enabled": True,
    },
    {"username": "ann", "firstName": "Ann", "lastName": "", "enabled": True},
    {"username": "gone", "enabled": False},
    {"username": "", "enabled": True},
]


def _directory(url, secret=SECRET, ttl=300.0):
    return KeycloakDirectory(
        base_url=url,
        realm="infra",
        client_id="strictdoc-directory",
        client_secret=secret,
        ttl=ttl,
    )


def test_001_it_lists_the_enabled_users_sorted_and_cached():
    with FakeKeycloak(USERS) as keycloak:
        directory = _directory(keycloak.url)
        users = directory.users()
        assert [u.username for u in users] == ["ann", "bob"]
        assert users[1].name == "Bob Martin"
        assert users[1].email == "bob@example.org"
        assert directory.has(" BOB ") and not directory.has("gone")
        directory.users()
        assert keycloak.user_requests == 1 and keycloak.tokens_issued == 1


def test_002_it_reads_every_page():
    many = [{"username": f"user{n:04d}", "enabled": True} for n in range(450)]
    with FakeKeycloak(many) as keycloak:
        assert len(_directory(keycloak.url).users()) == 450
        assert keycloak.user_requests == 3


def test_003_a_wrong_secret_or_a_down_server_is_an_error():
    with FakeKeycloak(USERS) as keycloak:
        with pytest.raises(DirectoryError):
            _directory(keycloak.url, secret="wrong").users()
        keycloak.down = True
        with pytest.raises(DirectoryError):
            _directory(keycloak.url).users()
    with pytest.raises(DirectoryError):
        _directory("http://127.0.0.1:9").users()


def test_004_the_environment_configures_it(monkeypatch):
    monkeypatch.delenv("STRICTDOC_KEYCLOAK_URL", raising=False)
    assert directory_from_environment() is None
    monkeypatch.setenv("STRICTDOC_KEYCLOAK_URL", "http://kc:8080")
    assert directory_from_environment() is None  # no secret
    monkeypatch.setenv("STRICTDOC_KEYCLOAK_CLIENT_SECRET", "x")
    assert directory_from_environment() is not None
