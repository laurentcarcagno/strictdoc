"""
@relation(SDOC-SRS-1224, scope=file)
"""

import sys
from types import SimpleNamespace
from typing import Dict, List, Optional, Tuple

import pytest

from strictdoc.features.desktop.secret_store import (
    KEYRING_SERVICE_NAME,
    KeyringSecretStore,
    MemorySecretStore,
    SecretStoreError,
)


class FakeKeyringError(Exception):
    pass


class FakePasswordDeleteError(FakeKeyringError):
    pass


class FakeKeyring:
    """Stands for the keyring module. The real keyring is never used."""

    def __init__(self) -> None:
        self.calls: List[Tuple[str, str, str]] = []
        self.passwords: Dict[Tuple[str, str], str] = {}
        # An error that every call raises, to simulate a failing keyring.
        self.failure: Optional[Exception] = None

    def get_password(self, service: str, name: str) -> Optional[str]:
        self.calls.append(("get", service, name))
        self._raise_failure()
        return self.passwords.get((service, name))

    def set_password(self, service: str, name: str, value: str) -> None:
        self.calls.append(("set", service, name))
        self._raise_failure()
        self.passwords[(service, name)] = value

    def delete_password(self, service: str, name: str) -> None:
        self.calls.append(("delete", service, name))
        self._raise_failure()
        if (service, name) not in self.passwords:
            raise FakePasswordDeleteError("no such password")
        del self.passwords[(service, name)]

    def _raise_failure(self) -> None:
        if self.failure is not None:
            raise self.failure


@pytest.fixture(name="fake_keyring")
def fixture_fake_keyring(monkeypatch: pytest.MonkeyPatch) -> FakeKeyring:
    fake_keyring = FakeKeyring()
    keyring_module = SimpleNamespace(
        get_password=fake_keyring.get_password,
        set_password=fake_keyring.set_password,
        delete_password=fake_keyring.delete_password,
    )
    errors_module = SimpleNamespace(
        KeyringError=FakeKeyringError,
        PasswordDeleteError=FakePasswordDeleteError,
    )
    monkeypatch.setitem(sys.modules, "keyring", keyring_module)
    monkeypatch.setitem(sys.modules, "keyring.errors", errors_module)
    return fake_keyring


def test_001_memory_store() -> None:
    store = MemorySecretStore()

    assert store.get("ai/id-1") is None
    store.set("ai/id-1", "secret")
    assert store.get("ai/id-1") == "secret"
    store.delete("ai/id-1")
    store.delete("ai/id-1")
    assert store.get("ai/id-1") is None


def test_002_keyring_store_uses_the_service_of_the_application(
    fake_keyring: FakeKeyring,
) -> None:
    store = KeyringSecretStore()

    store.set("ai/id-1", "secret")
    assert store.get("ai/id-1") == "secret"
    store.delete("ai/id-1")
    assert store.get("ai/id-1") is None

    assert KEYRING_SERVICE_NAME == "strictdoc-desktop"
    assert fake_keyring.calls == [
        ("set", "strictdoc-desktop", "ai/id-1"),
        ("get", "strictdoc-desktop", "ai/id-1"),
        ("delete", "strictdoc-desktop", "ai/id-1"),
        ("get", "strictdoc-desktop", "ai/id-1"),
    ]


def test_003_keyring_store_deletes_a_missing_secret_quietly(
    fake_keyring: FakeKeyring,
) -> None:
    KeyringSecretStore().delete("ai/unknown")

    assert fake_keyring.calls == [("delete", "strictdoc-desktop", "ai/unknown")]


def test_004_failing_keyring_reads_nothing(fake_keyring: FakeKeyring) -> None:
    fake_keyring.failure = FakeKeyringError("no keyring backend")

    assert KeyringSecretStore().get("ai/id-1") is None


def test_005_failing_keyring_raises_an_error_of_the_application(
    fake_keyring: FakeKeyring,
) -> None:
    fake_keyring.failure = FakeKeyringError("keyring is locked")
    store = KeyringSecretStore()

    with pytest.raises(SecretStoreError, match="save.*ai/id-1.*locked"):
        store.set("ai/id-1", "secret")
    with pytest.raises(SecretStoreError, match="delete.*ai/id-1.*locked"):
        store.delete("ai/id-1")
